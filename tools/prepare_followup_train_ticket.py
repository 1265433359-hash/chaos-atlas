"""Prepare an isolated, offline Train Ticket follow-up profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
TARGET_NAMESPACE = "chaosatlas-train-ticket"
DEFAULT_SOURCE_COMMIT = "313886e99befb94be6cd45f085c98e0019f59829"
REQUIRED_DEPENDENCIES = {
    "nacos",
    "rabbitmq",
    "train-ticket-db",
    "ts-order-mysql",
    "ts-station-mysql",
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_documents(path: Path) -> list[dict[str, Any]]:
    try:
        docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8-sig")))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot load Train Ticket runtime YAML: {exc}") from exc
    return [doc for doc in docs if isinstance(doc, dict)]


def _metadata(doc: dict[str, Any]) -> dict[str, Any]:
    value = doc.get("metadata")
    return value if isinstance(value, dict) else {}


def _rewrite_document(doc: dict[str, Any]) -> dict[str, Any]:
    rewritten = json.loads(json.dumps(doc))
    metadata = rewritten.setdefault("metadata", {})
    metadata["namespace"] = TARGET_NAMESPACE
    return rewritten


def _dependency_refs(documents: list[dict[str, Any]]) -> set[str]:
    refs: set[str] = set()
    for doc in documents:
        if doc.get("kind") != "Deployment":
            continue
        pod_spec = doc.get("spec", {}).get("template", {}).get("spec", {})
        for container in pod_spec.get("containers", []):
            for ref in container.get("envFrom", []):
                if "configMapRef" in ref:
                    refs.add(str(ref["configMapRef"].get("name")))
                if "secretRef" in ref:
                    refs.add(str(ref["secretRef"].get("name")))
            for env in container.get("env", []):
                value_from = env.get("valueFrom", {})
                for key in ("configMapKeyRef", "secretKeyRef"):
                    if key in value_from:
                        refs.add(str(value_from[key].get("name")))
    return {ref for ref in refs if ref and ref != "None"}


def _image_refs(documents: list[dict[str, Any]]) -> list[str]:
    images: list[str] = []
    for doc in documents:
        if doc.get("kind") != "Deployment":
            continue
        containers = (
            doc.get("spec", {})
            .get("template", {})
            .get("spec", {})
            .get("containers", [])
        )
        images.extend(
            str(container["image"])
            for container in containers
            if isinstance(container, dict) and container.get("image")
        )
    return images


def _pin_images(
    manifest_yaml: str,
    image_digests: dict[str, str] | None,
) -> tuple[str, list[dict[str, str]], list[str]]:
    records: list[dict[str, str]] = []
    refs: list[str] = []
    pattern = re.compile(r"^(\s*image:\s*)(\S+)(\s*)$", re.MULTILINE)

    def replace(match: re.Match[str]) -> str:
        source = match.group(2)
        refs.append(source)
        if image_digests is None:
            return match.group(0)
        pinned = image_digests.get(source)
        if not pinned or "@sha256:" not in pinned:
            raise ValueError(f"missing immutable digest for image: {source}")
        records.append({"source": source, "pinned": pinned})
        return f"{match.group(1)}{pinned}{match.group(3)}"

    return pattern.sub(replace, manifest_yaml), records, refs


def build_fresh_manifest(
    source_paths: list[Path],
    *,
    source_commit: str = DEFAULT_SOURCE_COMMIT,
    image_digests: dict[str, str] | None = None,
) -> dict[str, Any]:
    source_paths = [Path(path) for path in source_paths]
    all_documents: list[dict[str, Any]] = []
    source_hashes: dict[str, str] = {}
    for path in source_paths:
        source_bytes = path.read_bytes()
        source_hashes[str(path)] = sha256_bytes(source_bytes)
        all_documents.extend(_load_documents(path))

    deduplicated: dict[tuple[str, str], dict[str, Any]] = {}
    for doc in all_documents:
        key = (str(doc.get("kind")), str(_metadata(doc).get("name")))
        if key[0] == "None" or key[1] == "None":
            continue
        deduplicated.setdefault(key, doc)

    rewritten = [
        {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {"name": TARGET_NAMESPACE},
        }
    ]
    rewritten.extend(
        _rewrite_document(doc)
        for key, doc in sorted(deduplicated.items(), key=lambda item: item[0])
        if key[0] != "Namespace"
    )

    dependencies = _dependency_refs(all_documents)
    present_dependency_resources = {
        str(_metadata(doc).get("name"))
        for doc in all_documents
        if doc.get("kind") in {"Secret", "ConfigMap"}
    }
    missing_dependencies = sorted(
        REQUIRED_DEPENDENCIES - present_dependency_resources
    )

    manifest_yaml = yaml.safe_dump_all(
        rewritten,
        sort_keys=False,
        explicit_start=False,
        allow_unicode=False,
    )
    manifest_yaml, pinned_records, images = _pin_images(manifest_yaml, image_digests)
    blocked: list[str] = []
    if missing_dependencies:
        blocked.append("required_dependency_resources_missing")
    if image_digests is None:
        blocked.append("immutable_image_provenance_missing")

    result: dict[str, Any] = {
        "schema_version": "chaosatlas-followup-train-ticket-v1",
        "project_id": "train-ticket",
        "source_commit": source_commit,
        "input": {
            "source_paths": [str(path.resolve()) for path in source_paths],
            "source_sha256": source_hashes,
            "target_namespace": TARGET_NAMESPACE,
            "manifest_sha256": sha256_bytes(manifest_yaml.encode("utf-8")),
            "resource_count": len(rewritten),
            "resource_identities": [
                {"kind": doc["kind"], "name": doc["metadata"]["name"]}
                for doc in rewritten
            ],
        },
        "dependency_contract": {
            "references_observed": sorted(dependencies),
            "required_resources": sorted(REQUIRED_DEPENDENCIES),
            "present_resources": sorted(present_dependency_resources),
            "missing_resources": missing_dependencies,
            "credentials_read": False,
        },
        "oracle_contract": {
            "status": "requires_runtime_revalidation",
            "success": {
                "service": "ts-station-service",
                "port": 12345,
                "path": "/api/v1/stationservice/stations/id/shanghai",
                "expected_status": 200,
                "expected_body": {"status": 1, "msg": "Success"},
            },
            "not_found": {
                "service": "ts-station-service",
                "port": 12345,
                "path": "/api/v1/stationservice/stations/id/stationName",
                "expected_status": 200,
                "expected_body": {"status": 0, "msg": "Not exists"},
            },
            "independent_oracle_required": True,
            "historical_runtime_numbers_excluded": True,
        },
        "image_provenance": {
            "status": "verified_manifest_digests"
            if image_digests is not None
            else "pending_digest_resolution",
            "runtime_apply_allowed": False,
            "images": pinned_records,
            "image_references": images,
        },
        "static_gate": {
            "status": "blocked" if blocked else "passed",
            "namespace_local": True,
            "deduplicated_resources": True,
            "oracle_contract_recorded": True,
            "dependency_resources_present": not missing_dependencies,
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


def write_preparation(result: dict[str, Any], output_dir: Path) -> Path:
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "manifest.yaml": str(result["manifest_yaml"]),
        "fresh-manifest.json": json.dumps(
            {key: value for key, value in result.items() if key != "manifest_yaml"},
            indent=2,
            ensure_ascii=True,
        )
        + "\n",
        "dependency-contract.json": json.dumps(
            result["dependency_contract"], indent=2
        )
        + "\n",
        "image-provenance.json": json.dumps(
            result["image_provenance"], indent=2
        )
        + "\n",
        "oracle-contract.json": json.dumps(result["oracle_contract"], indent=2) + "\n",
        "static-gate.json": json.dumps(result["static_gate"], indent=2) + "\n",
        "README.md": (
            "# Train Ticket follow-up preparation\n\n"
            "Offline-only fresh manifest for `ChaosAtlas-full` and "
            "`ChaosAtlas-ablation`.\n\n"
            f"- Runtime namespace: `{TARGET_NAMESPACE}`\n"
            "- Historical runtime numbers and mutation labels are excluded.\n"
            "- Runtime apply remains disabled until dependencies, image "
            "provenance, dry-run, baseline, and cleanup gates pass.\n"
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
    parser.add_argument("--source", type=Path, nargs="+", required=True)
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
