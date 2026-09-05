"""Build a read-only project inventory and extension capability matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.extension_runtime_probe import probe_extension_environment
from tools.kubernetes_project_adapter import KubernetesProjectAdapter


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--context", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text(encoding="utf-8-sig"))
    adapter = KubernetesProjectAdapter(profile=profile, kube_context=args.context)
    inventory = adapter.inventory()
    detection = adapter.detect_server_deployment(inventory)
    runtime_probe = probe_extension_environment(profile, kube_context=args.context)
    result = {
        "schema_version": "chaosatlas-extension-project-matrix-v1",
        "project_id": profile.get("project_id"),
        "context": args.context,
        "inventory": inventory,
        "detection": {
            "status": detection.get("status"),
            "deployment_count": len(detection.get("deployment_nodes") or []),
            "core_candidate_count": len(detection.get("candidates") or []),
            "extension_candidate_count": len(detection.get("extension_candidates") or []),
            "extension_capability_matrix": detection.get("extension_capability_matrix") or [],
        },
        "runtime_probe": runtime_probe,
        "read_only": True,
        "injection_performed": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    statuses = {item["extension_id"]: item["status"] for item in runtime_probe["extensions"]}
    print(json.dumps({"status": "verified", "output": str(args.output), "deployments": result["detection"]["deployment_count"], "extension_candidates": result["detection"]["extension_candidate_count"], "runtime_status": statuses}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
