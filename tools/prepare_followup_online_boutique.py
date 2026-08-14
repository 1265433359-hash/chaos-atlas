"""Build a fresh, offline-only Online Boutique experiment manifest.

This preparation step deliberately does not call kubectl, Docker, a registry,
or a model. It creates a namespace-isolated copy of the existing lab profile,
records input/output hashes, and keeps runtime authorization separate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
TARGET_NAMESPACE = "chaosatlas-online-boutique"
SOURCE_NAMESPACE = "online-boutique-lab"
DEFAULT_SOURCE_COMMIT = "9a4616e77f0f9cbcbecaf27d711c38890dda1404"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def pin_manifest_images(
    manifest_yaml: str,
    image_map: dict[str, str],
) -> tuple[str, list[dict[str, str]]]:
    """Replace every Kubernetes image field with a recorded immutable image."""
    records: list[dict[str, str]] = []
    pattern = re.compile(r"^(\s*image:\s*)(\S+)(\s*)$", re.MULTILINE)

    def replace(match: re.Match[str]) -> str:
        source = match.group(2)
        pinned = image_map.get(source)
        if not pinned or "@sha256:" not in pinned:
            raise ValueError(f"missing immutable digest for image: {source}")
        records.append({"source": source, "pinned": pinned})
        return f"{match.group(1)}{pinned}{match.group(3)}"

    pinned_yaml = pattern.sub(replace, manifest_yaml)
    if not records:
        raise ValueError("manifest contains no image fields")
    return pinned_yaml, records


def _load_documents(source_path: Path) -> list[dict[str, Any]]:
    try:
        documents = list(yaml.safe_load_all(source_path.read_text(encoding="utf-8-sig")))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot load Kubernetes manifest: {exc}") from exc
    documents = [doc for doc in documents if doc is not None]
    if not documents or any(not isinstance(doc, dict) for doc in documents):
        raise ValueError("source manifest must contain only non-empty mapping documents")
    return documents


def _metadata(doc: dict[str, Any]) -> dict[str, Any]:
    value = doc.get("metadata")
    return value if isinstance(value, dict) else {}


def _is_loadgenerator(doc: dict[str, Any]) -> bool:
    metadata = _metadata(doc)
    name = str(metadata.get("name", "")).lower()
    labels = metadata.get("labels") or {}
    app = str(labels.get("app", "")).lower() if isinstance(labels, dict) else ""
    return name == "loadgenerator" or app == "loadgenerator"


def _deployment_names(documents: list[dict[str, Any]]) -> set[str]:
    return {
        str(_metadata(doc).get("name"))
        for doc in documents
        if doc.get("kind") == "Deployment"
    }


def _service_names(documents: list[dict[str, Any]]) -> set[str]:
    return {
        str(_metadata(doc).get("name"))
        for doc in documents
        if doc.get("kind") == "Service"
    }


def _frontend_probe_path(documents: list[dict[str, Any]]) -> str | None:
    for doc in documents:
        if doc.get("kind") != "Deployment" or _metadata(doc).get("name") != "frontend":
            continue
        containers = (
            doc.get("spec", {})
            .get("template", {})
            .get("spec", {})
            .get("containers", [])
        )
        for container in containers:
            for probe_name in ("readinessProbe", "livenessProbe"):
                probe = container.get(probe_name) or {}
                http_get = probe.get("httpGet") or {}
                if http_get.get("path"):
                    return str(http_get["path"])
    return None


def _rewrite_namespace(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rewritten: list[dict[str, Any]] = []
    for original in documents:
        doc = json.loads(json.dumps(original))
        metadata = doc.setdefault("metadata", {})
        if doc.get("kind") == "Namespace":
            metadata["name"] = TARGET_NAMESPACE
            metadata.pop("namespace", None)
        else:
            metadata["namespace"] = TARGET_NAMESPACE
        rewritten.append(doc)
    return rewritten


def build_fresh_manifest(
    source_path: Path,
    *,
    source_commit: str = DEFAULT_SOURCE_COMMIT,
) -> dict[str, Any]:
    source_path = Path(source_path)
    source_bytes = source_path.read_bytes()
    documents = _load_documents(source_path)
    blocked: list[str] = []

    source_namespaces = sorted(
        {
            str(_metadata(doc).get("namespace"))
            for doc in documents
            if doc.get("kind") != "Namespace" and _metadata(doc).get("namespace")
        }
    )
    if source_namespaces != [SOURCE_NAMESPACE]:
        blocked.append("unexpected_source_namespace")
    if any(_is_loadgenerator(doc) for doc in documents):
        blocked.append("loadgenerator_present")

    deployments = _deployment_names(documents)
    services = _service_names(documents)
    if "frontend" not in deployments or "frontend" not in services:
        blocked.append("frontend_resource_missing")
    if "checkoutservice" not in deployments:
        blocked.append("checkoutservice_deployment_missing")

    frontend_path = _frontend_probe_path(documents) or "/_healthz"
    rewritten = _rewrite_namespace(documents)
    manifest_yaml = yaml.safe_dump_all(
        rewritten,
        sort_keys=False,
        explicit_start=False,
        allow_unicode=False,
    )
    manifest_bytes = manifest_yaml.encode("utf-8")

    result: dict[str, Any] = {
        "schema_version": "chaosatlas-followup-online-boutique-v1",
        "project_id": "online-boutique",
        "source_commit": source_commit,
        "input": {
            "source_path": str(source_path.resolve()),
            "source_namespace": source_namespaces[0] if source_namespaces else None,
            "target_namespace": TARGET_NAMESPACE,
            "source_sha256": sha256_bytes(source_bytes),
            "manifest_sha256": sha256_bytes(manifest_bytes),
            "deployment_names": sorted(deployments),
            "service_names": sorted(services),
        },
        "oracle_contract": {
            "status": "requires_runtime_revalidation",
            "frontend": {
                "service": "frontend",
                "path": frontend_path,
                "expected": "HTTP 200 and stable frontend response",
                "source_contract_observed": frontend_path == "/_healthz",
            },
            "place_order": {
                "workflow": "AddItem_then_PlaceOrder",
                "client": "artifacts/online-boutique/ob_client.py",
                "checkout_service": "checkoutservice",
                "expected": "successful order response with order_id and shipping_tracking_id",
                "state_reset_required": True,
            },
        },
        "image_provenance": {
            "status": "pending_digest_resolution",
            "runtime_apply_allowed": False,
            "note": "Existing lab profile uses local tags; resolve and record immutable digests before apply.",
        },
        "static_gate": {
            "status": "blocked" if blocked else "passed",
            "namespace_local": not blocked or "unexpected_source_namespace" not in blocked,
            "loadgenerator_absent": "loadgenerator_present" not in blocked,
            "frontend_present": "frontend_resource_missing" not in blocked,
            "place_order_entrypoint_present": "checkoutservice_deployment_missing" not in blocked,
            "blocked_reasons": sorted(set(blocked)),
        },
        "runtime": {
            "server_side_dry_run": "pending_authorized_cluster_session",
            "baseline_windows": "pending",
            "runtime_apply_allowed": False,
            "human_review": "pending",
            "knowledge_base_updated": False,
        },
        "manifest_yaml": manifest_yaml,
    }
    return result


def pin_fresh_manifest(
    result: dict[str, Any],
    image_map: dict[str, str],
    *,
    provenance_source: str,
) -> dict[str, Any]:
    """Pin a prepared manifest and retain both input and pinned identities."""
    manifest_yaml = str(result.get("manifest_yaml", ""))
    original_hash = str(result["input"]["manifest_sha256"])
    pinned_yaml, records = pin_manifest_images(manifest_yaml, image_map)
    result["manifest_yaml"] = pinned_yaml
    result["input"]["unpinned_manifest_sha256"] = original_hash
    result["input"]["manifest_sha256"] = sha256_bytes(pinned_yaml.encode("utf-8"))
    result["image_provenance"] = {
        "status": "verified_local_repo_digests",
        "provenance_source": provenance_source,
        "runtime_apply_allowed": False,
        "images": records,
    }
    result["runtime"]["server_side_dry_run"] = "pending_authorized_cluster_session"
    result["runtime"]["runtime_apply_allowed"] = False
    return result


def write_preparation(result: dict[str, Any], output_dir: Path) -> Path:
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_yaml = str(result["manifest_yaml"])
    files = {
        "manifest.yaml": manifest_yaml,
        "fresh-manifest.json": json.dumps(
            {key: value for key, value in result.items() if key != "manifest_yaml"},
            indent=2,
            ensure_ascii=True,
        )
        + "\n",
        "oracle-contract.json": json.dumps(result["oracle_contract"], indent=2) + "\n",
        "static-gate.json": json.dumps(result["static_gate"], indent=2) + "\n",
        "README.md": (
            "# Online Boutique follow-up preparation\n\n"
            "Offline-only fresh manifest for the two active methods: "
            "`ChaosAtlas-full` and `ChaosAtlas-ablation`.\n\n"
            "- Runtime namespace: `chaosatlas-online-boutique`\n"
            "- Server-side dry-run: pending authorized cluster session\n"
            "- Runtime apply: blocked until image digests, oracle baselines, and cleanup gates pass\n"
            "- Human review: pending\n"
        ),
    }
    for name, content in files.items():
        path = output_dir / name
        if name == "manifest.yaml":
            path.write_bytes(content.encode("utf-8"))
        else:
            path.write_text(content, encoding="utf-8", newline="\n")
    return output_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", default=DEFAULT_SOURCE_COMMIT)
    args = parser.parse_args()
    result = build_fresh_manifest(args.source, source_commit=args.source_commit)
    write_preparation(result, args.output)
    print(
        json.dumps(
            {
                "project_id": result["project_id"],
                "static_gate": result["static_gate"],
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0 if result["static_gate"]["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
