"""Deploy-time readiness gate for the isolated Sock Shop two-arm experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import yaml

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

try:
    from tools.prepare_two_arm_runtime_profiles import evaluate_runtime_profile, sock_shop_cluster_facts
    from tools.run_chaos_experiment import kubectl_json, run_kubectl, start_port_forward, stop_process, wait_for_port
    from tools.run_sock_shop_two_arm import NAMESPACE, global_residuals, run_journey, run_one
except ModuleNotFoundError:
    from prepare_two_arm_runtime_profiles import evaluate_runtime_profile, sock_shop_cluster_facts
    from run_chaos_experiment import kubectl_json, run_kubectl, start_port_forward, stop_process, wait_for_port
    from run_sock_shop_two_arm import NAMESPACE, global_residuals, run_journey, run_one


def deployment_health(payload: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for item in payload.get("items", []):
        desired = int((item.get("spec") or {}).get("replicas", 1) or 0)
        available = int((item.get("status") or {}).get("availableReplicas", 0) or 0)
        rows.append({"name": str((item.get("metadata") or {}).get("name", "")), "desired": desired, "available": available, "ready": desired > 0 and available == desired})
    return {
        "deployments_total": len(rows),
        "deployments_available": sum(item["ready"] for item in rows),
        "all_ready": bool(rows) and all(item["ready"] for item in rows),
        "deployments": rows,
    }


def build_rehearsal_mutation(name: str) -> dict[str, Any]:
    return {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "PodChaos",
        "metadata": {"name": name, "namespace": NAMESPACE},
        "spec": {
            "action": "pod-kill",
            "mode": "one",
            "duration": "30s",
            "selector": {"namespaces": [NAMESPACE], "labelSelectors": {"name": "payment"}},
        },
    }


def wait_for_deployments(timeout: float = 900) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {"deployments_total": 0, "deployments_available": 0, "all_ready": False, "deployments": []}
    errors: list[str] = []
    while time.monotonic() < deadline:
        payload, error = kubectl_json(["get", "deployments", "-n", NAMESPACE])
        if error:
            errors.append(error)
        elif payload is not None:
            last = deployment_health(payload)
            if last["all_ready"]:
                break
        time.sleep(5)
    return {**last, "errors": errors[-5:]}


def collect_baseline_windows() -> list[list[dict[str, Any]]]:
    process = start_port_forward(NAMESPACE, "front-end", 18081, 80)
    try:
        wait_for_port("127.0.0.1", 18081, process, 30)
        windows: list[list[dict[str, Any]]] = []
        for window_index in range(2):
            windows.append([run_journey() for _ in range(5)])
            if window_index == 0:
                time.sleep(10)
        return windows
    finally:
        stop_process(process)


def run_gate(manifest_yaml: Path, project_manifest_path: Path, output: Path) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"refusing nonempty gate output: {output}")
    output.mkdir(parents=True, exist_ok=True)
    project_manifest = json.loads(project_manifest_path.read_text(encoding="utf-8"))
    evidence: dict[str, Any] = {
        "schema_version": "sock-shop-deployment-gate-v1",
        "namespace": NAMESPACE,
        "manifest_path": str(manifest_yaml).replace("\\", "/"),
        "manifest_sha256": hashlib.sha256(manifest_yaml.read_bytes()).hexdigest(),
        "human_review": "pending",
        "knowledge_base_updated": False,
        "status": "running",
        "errors": [],
    }
    profile: dict[str, Any] | None = None
    try:
        code, stdout, stderr = run_kubectl(["apply", "--server-side", "--dry-run=server", "-f", str(manifest_yaml)], timeout=180)
        evidence["server_side_dry_run"] = {"status": "passed" if code == 0 else "failed", "return_code": code, "stdout": stdout, "stderr": stderr}
        if code != 0:
            raise RuntimeError("server-side dry-run failed")
        health = wait_for_deployments()
        evidence["deployment_health"] = health
        if not health["all_ready"]:
            raise RuntimeError("not all Sock Shop deployments became ready")
        residuals, residual_errors = global_residuals()
        evidence["pre_rehearsal_residual_scan"] = {"residual_resources": residuals, "errors": residual_errors}
        if residuals or residual_errors:
            raise RuntimeError("global Chaos residual scan was not clear before rehearsal")
        baseline_windows = collect_baseline_windows()
        evidence["baseline_windows"] = baseline_windows
        if len(baseline_windows) != 2 or not all(window and all(item.get("pass") is True for item in window) for window in baseline_windows):
            raise RuntimeError("two failure-free Sock Shop baseline windows were not observed")
        mutation_path = output / "payment-podkill-rehearsal.yaml"
        mutation_path.write_text(yaml.safe_dump(build_rehearsal_mutation("sock-shop-runtime-gate-payment-kill"), sort_keys=False), encoding="utf-8")
        rehearsal_path = output / "payment-podkill-rehearsal.json"
        rehearsal = run_one(mutation_path, rehearsal_path, "runtime-gate", 0, "payment-podkill-rehearsal", 1)
        evidence["rehearsal_report"] = str(rehearsal_path).replace("\\", "/")
        facts = sock_shop_cluster_facts(
            {
                "context": "minikube",
                "node_ready": True,
                "namespace": NAMESPACE,
                "deployments_available": health["deployments_available"],
                "deployments_total": health["deployments_total"],
                "server_side_dry_run": "passed",
            },
            baseline_windows,
            rehearsal,
        )
        profile = evaluate_runtime_profile(project_manifest, facts)
        profile["project_manifest_path"] = str(project_manifest_path).replace("\\", "/")
        profile["project_manifest_sha256"] = hashlib.sha256(project_manifest_path.read_bytes()).hexdigest()
        if profile["runtime_ready"] is not True:
            raise RuntimeError(f"runtime profile blocked: {profile['blocked_reasons']}")
        evidence["status"] = "passed"
    except Exception as exc:
        evidence["errors"].append(f"{type(exc).__name__}: {exc}")
        evidence["status"] = "blocked"
    finally:
        residuals, residual_errors = global_residuals()
        evidence["final_global_residual_scan"] = {"residual_resources": residuals, "errors": residual_errors, "clear": not residuals and not residual_errors}
        (output / "gate.json").write_text(json.dumps(evidence, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        if profile is not None:
            (output / "runtime-profile.json").write_text(json.dumps(profile, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest-yaml", type=Path, required=True)
    parser.add_argument("--project-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_gate(args.manifest_yaml, args.project_manifest, args.output)
    print(json.dumps({"status": result["status"], "errors": result["errors"]}, ensure_ascii=True))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
