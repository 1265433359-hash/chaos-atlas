"""Build a fresh digest-pinned Sock Shop input for the two-arm experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

try:
    from tools.build_two_arm_real_project_inputs import build_project_manifest, generic_knowledge_projection, write_bundle_root
except ModuleNotFoundError:
    from build_two_arm_real_project_inputs import build_project_manifest, generic_knowledge_projection, write_bundle_root


NAMESPACE = "chaosatlas-sock-shop"
VERIFIED_MONGO_IMAGE = "mongo@sha256:6189a342f8da4568b4b111c378a890b1fe186b1bc133742bff8811fe63d2e01e"


def build_sock_shop_manifest(source: Path, *, source_commit: str, image_overrides: dict[str, str]) -> dict[str, Any]:
    source = Path(source)
    docs = [doc for doc in yaml.safe_load_all(source.read_text(encoding="utf-8-sig")) if doc]
    if any(
        container.get("image") == "mongo"
        for doc in docs
        for container in doc.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
    ) and image_overrides.get("mongo") != VERIFIED_MONGO_IMAGE:
        raise ValueError("unversioned mongo must resolve to the verified Mongo compatibility image")
    for doc in docs:
        if doc.get("kind") == "Service":
            spec = doc.setdefault("spec", {})
            spec["type"] = "ClusterIP"
            for port in spec.get("ports", []):
                port.pop("nodePort", None)
    prepared = source.with_name(source.stem + ".chaosatlas-prepared.yaml")
    prepared.write_text(yaml.safe_dump_all(docs, sort_keys=False, allow_unicode=False), encoding="utf-8")
    try:
        oracle = {
            "workflow": "front-end home, catalogue browse, demo login, and authenticated orders read-only golden journey",
            "success": "front-end, catalogue, and login return HTTP 200; authenticated orders returns HTTP 201; all satisfy frozen response contracts",
            "steps": [
                {"id": "front-end", "service": "front-end", "path": "/", "contract": "non-empty HTML"},
                {"id": "catalogue", "service": "front-end", "path": "/catalogue", "contract": "JSON array"},
                {"id": "login", "service": "front-end", "path": "/login", "method": "GET", "auth": "frozen_demo_basic", "contract": "Cookie is set", "success_status": 200},
                {"id": "orders", "service": "front-end", "path": "/orders", "contract": "JSON array or object", "success_status": 201},
            ],
            "read_only": True,
            "timeout_seconds": 15,
            "baseline_successes": 5,
            "washout_successes": 10,
        }
        result = build_project_manifest(
            project_id="sock-shop",
            source_commit=source_commit,
            source_manifest_path=prepared,
            namespace=NAMESPACE,
            business_oracle=oracle,
            image_overrides=image_overrides,
        )
        result["source_manifest_path"] = str(source.resolve())
        result["source_manifest_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        return result
    finally:
        prepared.unlink(missing_ok=True)


def write_manifest(manifest: dict[str, Any], output: Path) -> None:
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"refusing nonempty output directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    (output / "manifest.yaml").write_text(manifest["deployable_manifest"], encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({k: v for k, v in manifest.items() if k != "deployable_manifest"}, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--image-map", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    image_data = json.loads(args.image_map.read_text(encoding="utf-8"))
    image_overrides = {str(item["source"]): str(item["pinned"]) for item in image_data["images"]}
    manifest = build_sock_shop_manifest(args.source, source_commit=args.source_commit, image_overrides=image_overrides)
    write_bundle_root({"sock-shop": manifest}, args.output, generic_knowledge_projection(), projects=["sock-shop"])
    print(json.dumps({"status": manifest["static_gate"]["status"], "images": len(image_overrides), "output": str(args.output)}))
    return 0 if manifest["static_gate"]["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
