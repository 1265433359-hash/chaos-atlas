"""Offline validation for digest-pinned P09 Kubernetes profiles."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml

FORBIDDEN = re.compile(
    r"agent[_-]backend|plugin[_-]daemon|sandbox|ssrf[_-]proxy|nginx|"
    r"weaviate|qdrant|chroma|milvus|opensearch|pgvector|pgvecto|seekdb|"
    r"oceanbase|tidb|tiflash|tikv|vastbase",
    re.I,
)
REQUIRED = {"api", "worker", "worker-beat", "web", "postgres", "redis", "init-permissions"}


def run(profile: Path, output: Path) -> int:
    result = {"project_id": "P09", "namespace": "chaosatlas-p09", "apply_allowed": False, "server_side_dry_run": "not_run", "checks": []}
    if not profile.exists():
        result["checks"].append({"name": "profile", "ok": False, "reason": "digest-pinned profile not generated"})
        result["server_side_dry_run"] = "blocked_missing_digest_pinned_yaml"
    else:
        docs = list(yaml.safe_load_all(profile.read_text(encoding="utf-8")))
        names = {doc.get("metadata", {}).get("name") for doc in docs if isinstance(doc, dict)}
        images = [
            c.get("image", "")
            for doc in docs
            for c in ((doc.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])) if isinstance(doc, dict) else [])
        ]
        identities = []
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            metadata = doc.get("metadata", {}) or {}
            identities.extend([metadata.get("name", ""), metadata.get("labels", {})])
            pod = (doc.get("spec", {}) or {}).get("template", {}) or {}
            pod_meta = pod.get("metadata", {}) or {}
            identities.append(pod_meta.get("labels", {}))
            spec = pod.get("spec", {}) or {}
            identities.extend(c.get("name", "") for c in spec.get("containers", []))
            identities.extend(c.get("image", "") for c in spec.get("containers", []))
        result["checks"] += [
            {"name": "namespace-local", "ok": all(doc.get("metadata", {}).get("namespace") in (None, "chaosatlas-p09") for doc in docs if isinstance(doc, dict))},
            {"name": "forbidden-services", "ok": not any(FORBIDDEN.search(str(value)) for value in identities)},
            {"name": "immutable-images", "ok": bool(images) and all("@sha256:" in image for image in images), "images": images},
            {"name": "required-resources", "ok": REQUIRED.issubset(names), "names": sorted(names)},
        ]
        result["server_side_dry_run"] = "requires_cluster_execution"
    result["ok"] = all(check.get("ok", False) for check in result["checks"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


def main() -> int:
    here = Path(__file__).resolve().parents[1] / "artifacts/experiments/chaosatlas_10_projects/runtime_profiles/P09"
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, default=here / "minimal-profile.yaml")
    parser.add_argument("--output", type=Path, default=here / "server-side-dry-run.json")
    args = parser.parse_args()
    return run(args.profile, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
