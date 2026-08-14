"""Prepare an isolated, sanitized OpenTelemetry Demo follow-up profile.

This module is offline-only. It does not call kubectl, Docker, a registry, or
an external model. Runtime apply remains disabled until image provenance,
server-side dry-run, and independent oracle gates pass.
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
TARGET_NAMESPACE = "chaosatlas-otel"
SOURCE_NAMESPACE = "otel-demo-lab"
DEFAULT_SOURCE_COMMIT = "2e72d8bcdf754603e956406808630bc9663c992c"
PASSWORD_PLACEHOLDER = "CHAOSATLAS_OTEL_DB_PASSWORD_PLACEHOLDER"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _metadata(doc: dict[str, Any]) -> dict[str, Any]:
    value = doc.get("metadata")
    return value if isinstance(value, dict) else {}


def _load_documents(source_path: Path) -> list[dict[str, Any]]:
    try:
        documents = list(yaml.safe_load_all(source_path.read_text(encoding="utf-8-sig")))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot load OTEL manifest: {exc}") from exc
    documents = [doc for doc in documents if doc is not None]
    if not documents or any(not isinstance(doc, dict) for doc in documents):
        raise ValueError("OTEL manifest must contain only non-empty mappings")
    return documents


def _rewrite_namespace(value: Any) -> Any:
    if isinstance(value, dict):
        rewritten = {key: _rewrite_namespace(item) for key, item in value.items()}
        if "metadata" in rewritten and isinstance(rewritten["metadata"], dict):
            metadata = rewritten["metadata"]
            if rewritten.get("kind") == "Namespace":
                metadata["name"] = TARGET_NAMESPACE
                metadata.pop("namespace", None)
            elif "name" in metadata:
                metadata["namespace"] = TARGET_NAMESPACE
        return rewritten
    if isinstance(value, list):
        return [_rewrite_namespace(item) for item in value]
    return value


def _scrub_sensitive_strings(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _scrub_sensitive_strings(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub_sensitive_strings(item) for item in value]
    if isinstance(value, str):
        value = value.replace("astronomy_password", PASSWORD_PLACEHOLDER)
        return value
    return value


def _image_references(documents: list[dict[str, Any]]) -> list[str]:
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
        for container in containers:
            image = container.get("image") if isinstance(container, dict) else None
            if image:
                images.append(str(image))
    return images


def _pin_images(
    manifest_yaml: str,
    image_digests: dict[str, str] | None,
) -> tuple[str, list[dict[str, str]], list[str]]:
    images: list[str] = []
    records: list[dict[str, str]] = []
    pattern = re.compile(r"^(\s*image:\s*)(\S+)(\s*)$", re.MULTILINE)

    def replace(match: re.Match[str]) -> str:
        source = match.group(2)
        images.append(source)
        if image_digests is None:
            return match.group(0)
        pinned = image_digests.get(source)
        if not pinned or "@sha256:" not in pinned:
            raise ValueError(f"missing immutable digest for image: {source}")
        records.append({"source": source, "pinned": pinned})
        return f"{match.group(1)}{pinned}{match.group(3)}"

    return pattern.sub(replace, manifest_yaml), records, images


def _config_map(name: str, filename: str, content: str) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": name, "namespace": TARGET_NAMESPACE},
        "data": {filename: content},
    }


def load_image_digests(path: Path) -> dict[str, str]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load image digest mapping: {exc}") from exc
    records = payload.get("images") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise ValueError("image digest mapping must contain an images list")
    result: dict[str, str] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("each image digest record must be an object")
        source = record.get("source")
        pinned = record.get("pinned")
        if not isinstance(source, str) or not source:
            raise ValueError("image digest source must be a non-empty string")
        if not isinstance(pinned, str) or "@sha256:" not in pinned:
            raise ValueError(f"image digest pinned value is invalid for {source}")
        result[source] = pinned
    return result


def build_fresh_manifest(
    source_path: Path,
    *,
    init_sql: Path,
    flagd_config: Path,
    source_commit: str = DEFAULT_SOURCE_COMMIT,
    image_digests: dict[str, str] | None = None,
) -> dict[str, Any]:
    source_path = Path(source_path)
    init_sql = Path(init_sql)
    flagd_config = Path(flagd_config)
    source_bytes = source_path.read_bytes()
    documents = _load_documents(source_path)

    source_namespaces = sorted(
        {
            str(_metadata(doc).get("namespace"))
            for doc in documents
            if doc.get("kind") != "Namespace" and _metadata(doc).get("namespace")
        }
    )
    blocked: list[str] = []
    if source_namespaces != [SOURCE_NAMESPACE]:
        blocked.append("unexpected_source_namespace")
    if not init_sql.is_file():
        blocked.append("postgres_init_missing")
    if not flagd_config.is_file():
        blocked.append("flagd_config_missing")

    deployments = {
        str(_metadata(doc).get("name"))
        for doc in documents
        if doc.get("kind") == "Deployment"
    }
    services = {
        str(_metadata(doc).get("name"))
        for doc in documents
        if doc.get("kind") == "Service"
    }
    required_deployments = {
        "checkout",
        "cart",
        "valkey",
        "postgres",
        "product-catalog",
        "currency",
        "flagd",
        "payment",
        "quote",
        "shipping",
        "email",
    }
    missing_deployments = sorted(required_deployments - deployments)
    if missing_deployments:
        blocked.append("required_deployments_missing")
    if not {"checkout", "cart"}.issubset(services):
        blocked.append("business_services_missing")

    rewritten = _scrub_sensitive_strings(_rewrite_namespace(documents))
    if init_sql.is_file() and flagd_config.is_file():
        rewritten.extend(
            [
                _config_map(
                    "postgres-init",
                    "init.sql",
                    init_sql.read_text(encoding="utf-8-sig"),
                ),
                _config_map(
                    "flagd-config",
                    "demo.flagd.json",
                    flagd_config.read_text(encoding="utf-8-sig"),
                ),
            ]
        )

    manifest_yaml = yaml.safe_dump_all(
        rewritten,
        sort_keys=False,
        explicit_start=False,
        allow_unicode=False,
    )
    manifest_yaml, pinned_records, images = _pin_images(manifest_yaml, image_digests)
    if image_digests is None:
        blocked.append("immutable_image_provenance_missing")

    trace_backend = {
        "status": "recorded_unavailable",
        "service": None,
        "reason": "fresh core manifest does not include Jaeger or collector resources",
        "runtime_required": True,
    }
    result: dict[str, Any] = {
        "schema_version": "chaosatlas-followup-opentelemetry-demo-v1",
        "project_id": "opentelemetry-demo",
        "source_commit": source_commit,
        "input": {
            "source_path": str(source_path.resolve()),
            "source_namespace": source_namespaces[0] if source_namespaces else None,
            "target_namespace": TARGET_NAMESPACE,
            "source_sha256": sha256_bytes(source_bytes),
            "manifest_sha256": sha256_bytes(manifest_yaml.encode("utf-8")),
            "deployment_names": sorted(deployments),
            "service_names": sorted(services),
            "configmap_names": ["postgres-init", "flagd-config"]
            if init_sql.is_file() and flagd_config.is_file()
            else [],
        },
        "oracle_contract": {
            "status": "requires_runtime_revalidation",
            "workflow": "AddItem_then_PlaceOrder",
            "client": "artifacts/opentelemetry-demo/otel_client.py",
            "entry_service": "checkout",
            "supporting_service": "cart",
            "expected": "successful order response with order_id and shipping_tracking_id",
            "state_reset_required": True,
            "independent_oracle_required": True,
        },
        "trace_backend": trace_backend,
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
            "namespace_local": "unexpected_source_namespace" not in blocked,
            "configmaps_present": not {
                "postgres_init_missing",
                "flagd_config_missing",
            }.intersection(blocked),
            "required_deployments_present": not missing_deployments,
            "business_services_present": "business_services_missing" not in blocked,
            "trace_contract_recorded": True,
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
        "trace-contract.json": json.dumps(result["trace_backend"], indent=2) + "\n",
        "static-gate.json": json.dumps(result["static_gate"], indent=2) + "\n",
        "README.md": (
            "# OpenTelemetry Demo follow-up preparation\n\n"
            "Offline-only fresh manifest for `ChaosAtlas-full` and "
            "`ChaosAtlas-ablation`.\n\n"
            f"- Runtime namespace: `{TARGET_NAMESPACE}`\n"
            "- Runtime apply: blocked until immutable image provenance, "
            "server-side dry-run, baseline, and trace gates pass\n"
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
    parser.add_argument("--init-sql", type=Path, required=True)
    parser.add_argument("--flagd-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", default=DEFAULT_SOURCE_COMMIT)
    parser.add_argument("--image-digests", type=Path)
    args = parser.parse_args()
    result = build_fresh_manifest(
        args.source,
        init_sql=args.init_sql,
        flagd_config=args.flagd_config,
        source_commit=args.source_commit,
        image_digests=load_image_digests(args.image_digests)
        if args.image_digests
        else None,
    )
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
