"""Run one guarded dependency-edge canary against a Dify Chatflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.compile_scenario_node import compile_scenario
from tools.dify_chatflow_oracle import DifyChatflowOracle
from tools.dify_canary_closed_loop import record_canary_trial
from tools.kubernetes_lifecycle_executor import KubernetesLifecycleExecutor
from tools.kubernetes_project_adapter import KubernetesProjectAdapter


DEFAULT_PROFILE = REPO_ROOT / "projects" / "dify-kubernetes" / "profile.json"
DEFAULT_CONTEXT = "chaosatlas-dify"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _scenario(node: dict[str, Any], candidate: dict[str, Any], *, duration_s: int) -> dict[str, Any]:
    profile_oracle = candidate.get("oracle") or {}
    fault = {
        "kind": candidate["fault_family"],
        "action": candidate["fault_family"],
        "selector": candidate["selector"],
        "parameters": candidate["parameters"],
        "target_node_id": node["node_id"],
        "edge": candidate["edge"],
    }
    return {
        "schema_version": 3,
        "node_type": "scenario_node",
        "scenario_id": "dify-dependency-canary",
        "deployment_nodes": [node],
        "phases": [{
            "phase_id": "live-canary",
            "mode": "ordered",
            "duration_s": duration_s,
            "target_node_ids": [node["node_id"]],
            "inject_confirmation": "status.injectedCount >= 1",
            "cleanup_owner": "chaosatlas",
            "faults": [fault],
        }],
        "oracle": {"business": profile_oracle},
        "recovery": {"deadline_s": 120},
        "cleanup": {"required": True, "owner": "chaosatlas"},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--context", default=DEFAULT_CONTEXT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--edge", default="api-plugin-daemon", help="Declared dependency edge id")
    parser.add_argument(
        "--fault-family",
        choices=["dependency_delay", "dependency_unreachable"],
        default="dependency_delay",
    )
    parser.add_argument("--latency-ms", type=int, default=100)
    parser.add_argument("--loss-percent", type=int, default=100)
    parser.add_argument("--duration-s", type=int, default=10)
    parser.add_argument("--approve-live", action="store_true")
    args = parser.parse_args()
    if not args.approve_live:
        raise SystemExit("refusing live mutation without --approve-live")

    profile = _read(args.profile)
    adapter = KubernetesProjectAdapter(profile=profile, kube_context=args.context)
    inventory = adapter.inventory()
    detection = adapter.detect_server_deployment(inventory)
    extension_id = f"extension.{args.fault_family}"
    candidate = next(
        (
            item for item in detection.get("extension_candidates") or []
            if item.get("fault_family") == extension_id
            and item.get("dependency_edge_id") == args.edge
        ),
        None,
    )
    if not isinstance(candidate, dict):
        raise RuntimeError(f"no supported dependency-delay candidate for edge {args.edge}")
    if args.duration_s < 1:
        raise ValueError("duration must be positive")
    candidate = dict(candidate)
    if args.fault_family == "dependency_delay":
        if args.latency_ms < 1:
            raise ValueError("latency must be positive")
        candidate["parameters"] = {
            "latency_ms": args.latency_ms,
            "jitter_ms": 0,
            "correlation": 100,
            "duration_s": args.duration_s,
        }
    else:
        if not 1 <= args.loss_percent <= 100:
            raise ValueError("loss percent must be between 1 and 100")
        candidate["parameters"] = {
            "loss_percent": args.loss_percent,
            "correlation": 100,
            "duration_s": args.duration_s,
        }
    node = next(item for item in detection["deployment_nodes"] if item.get("node_id") == candidate["node_id"])
    oracle_config = next(
        item for item in profile.get("business_oracles") or []
        if item.get("id") == candidate.get("oracle_id")
    )
    oracle = DifyChatflowOracle.from_oracle(
        oracle_config,
        namespace=inventory["namespace"],
        kube_context=args.context,
    )
    scenario = _scenario(node, {**candidate, "oracle": oracle_config}, duration_s=args.duration_s)
    compiled = compile_scenario(scenario)
    if compiled.get("status") != "verified" or len(compiled.get("manifests") or []) != 1:
        raise RuntimeError(f"dependency scenario compilation failed: {compiled.get('errors')}")
    manifest = compiled["manifests"][0]
    root = args.output.resolve()
    executor = KubernetesLifecycleExecutor(
        root=root,
        namespace=inventory["namespace"],
        allowed_namespaces={inventory["namespace"]},
        allow_live=True,
        oracle={"kind": "dify_chatflow", **oracle_config},
        hooks={
            "probe": lambda phase, value: oracle(phase, value),
            "recovery_signals": lambda **_kwargs: {
                "workload": {"confirmed": True, "state": "probe-managed", "errors": []},
                "business": oracle("recovery", manifest),
            },
        },
        poll_interval=0.5,
        injection_timeout=60.0,
        recovery_timeout=120.0,
        kube_context=args.context,
    )
    result = executor.run(manifest, action_id=f"dify-{args.fault_family}-20260903-{args.edge}")
    summary = {
        "schema_version": "chaosatlas-dify-dependency-canary-v1",
        "project_id": profile.get("project_id"),
        "context": args.context,
        "namespace": inventory["namespace"],
        "candidate": candidate,
        "compiled_kind": manifest.get("kind"),
        "compiled_manifest": manifest,
        "result": result,
    }
    root.mkdir(parents=True, exist_ok=True)
    closed_loop = record_canary_trial(
        root=root,
        profile=profile,
        candidate=candidate,
        result=result,
        project_inventory=inventory,
        repetition=1,
    )
    (root / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    summary["closed_loop"] = closed_loop
    (root / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result.get("status"),
        "verdict": result.get("verdict"),
        "attestation": (result.get("attestation") or {}).get("valid"),
        "cleanup": (result.get("cleanup") or {}).get("confirmed"),
        "rca_status": closed_loop.get("rca_status"),
        "classification": closed_loop.get("classification"),
        "output": str(root),
    }, ensure_ascii=True))
    return 0 if result.get("status") == "executed" and (result.get("attestation") or {}).get("valid") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
