"""Create an immutable namespace-rewritten manifest copy for a retest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml


_NAMESPACE_RE = re.compile(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_documents(source: Path) -> list[dict[str, Any]]:
    try:
        documents = [doc for doc in yaml.safe_load_all(source.read_text(encoding="utf-8-sig")) if doc is not None]
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot load manifest: {exc}") from exc
    if not documents or any(not isinstance(doc, dict) for doc in documents):
        raise ValueError("manifest must contain non-empty mapping documents")
    return documents


def _metadata(document: dict[str, Any]) -> dict[str, Any]:
    metadata = document.get("metadata")
    if metadata is None:
        metadata = {}
        document["metadata"] = metadata
    if not isinstance(metadata, dict):
        raise ValueError("manifest metadata must be an object")
    return metadata


def prepare_namespace_copy(
    source_path: Path,
    output_root: Path,
    *,
    source_namespace: str,
    target_namespace: str,
    strip_node_ports: bool = False,
) -> dict[str, Any]:
    """Write a namespace-local copy without ever mutating ``source_path``."""

    source_path = Path(source_path)
    output_root = Path(output_root)
    source_namespace = str(source_namespace).strip()
    target_namespace = str(target_namespace).strip()
    try:
        if not source_path.is_file() or source_path.is_symlink():
            raise ValueError("manifest source must be a real file")
        if not source_namespace or not _NAMESPACE_RE.fullmatch(source_namespace):
            raise ValueError("source namespace is unsafe")
        if not target_namespace or not _NAMESPACE_RE.fullmatch(target_namespace):
            raise ValueError("target namespace is unsafe")
        if source_namespace == target_namespace:
            raise ValueError("target namespace must be isolated from source")
        if output_root.exists() and (output_root.is_symlink() or not output_root.is_dir()):
            raise ValueError("output copy must be a real directory")
        if output_root.exists() and any(output_root.iterdir()):
            raise ValueError("output copy must be fresh")

        source_bytes = source_path.read_bytes()
        documents = _load_documents(source_path)
        rewritten: list[dict[str, Any]] = []
        node_port_rewrites: list[dict[str, str]] = []
        for document in documents:
            kind = str(document.get("kind") or "")
            metadata = _metadata(document)
            if kind == "Namespace":
                if str(metadata.get("name") or "") != source_namespace:
                    raise ValueError("source namespace mismatch")
                metadata.pop("namespace", None)
                metadata["name"] = target_namespace
            else:
                declared = str(metadata.get("namespace") or "").strip()
                if declared != source_namespace:
                    raise ValueError("source namespace mismatch")
                metadata["namespace"] = target_namespace
                if strip_node_ports and kind == "Service":
                    spec = document.get("spec")
                    ports = spec.get("ports") if isinstance(spec, dict) else None
                    if isinstance(spec, dict) and isinstance(ports, list) and any(
                        isinstance(port, dict) and "nodePort" in port for port in ports
                    ):
                        for port in ports:
                            if isinstance(port, dict):
                                port.pop("nodePort", None)
                        if spec.get("type") in {"NodePort", "LoadBalancer"}:
                            spec["type"] = "ClusterIP"
                            spec.pop("externalTrafficPolicy", None)
                            spec.pop("healthCheckNodePort", None)
                        node_port_rewrites.append(
                            {"kind": kind, "name": str(metadata.get("name") or "")}
                        )
            rewritten.append(document)

        manifest_text = yaml.safe_dump_all(
            rewritten,
            sort_keys=False,
            explicit_start=True,
            allow_unicode=False,
        )
        manifest_bytes = manifest_text.encode("utf-8")
        output_root.mkdir(parents=True, exist_ok=True)
        (output_root / "manifest.yaml").write_bytes(manifest_bytes)
        audit = {
            "schema_version": "chaosatlas-fresh-manifest-v1",
            "status": "prepared",
            "source_path": str(source_path.resolve()),
            "source_namespace": source_namespace,
            "target_namespace": target_namespace,
            "source_sha256": _sha256(source_bytes),
            "manifest_sha256": _sha256(manifest_bytes),
            "resource_identities": [
                {"kind": str(doc.get("kind")), "name": str(_metadata(doc).get("name"))}
                for doc in rewritten
            ],
            "node_port_rewrites": node_port_rewrites,
            "source_copy_immutable": True,
            "live_mutation": False,
        }
        (output_root / "fresh-manifest.json").write_text(
            json.dumps(audit, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        return audit
    except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
        return {"status": "blocked", "reason": str(exc), "live_mutation": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-namespace", required=True)
    parser.add_argument("--target-namespace", required=True)
    parser.add_argument("--strip-node-ports", action="store_true")
    args = parser.parse_args()
    result = prepare_namespace_copy(
        args.source,
        args.output,
        source_namespace=args.source_namespace,
        target_namespace=args.target_namespace,
        strip_node_ports=args.strip_node_ports,
    )
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0 if result.get("status") == "prepared" else 2


if __name__ == "__main__":
    raise SystemExit(main())
