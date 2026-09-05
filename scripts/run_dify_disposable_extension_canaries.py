"""Run queue and connection-pool extensions against Dify's disposable target."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.compile_scenario_node import compile_scenario
from tools.extension_fault_compiler import compile_extension_fault
from tools.kubernetes_project_adapter import KubernetesProjectAdapter
from tools.native_extension_fault_executor import NativeExtensionFaultExecutor
from tools.run_chaos_experiment import http_request, start_port_forward, stop_process, wait_for_port


CONTEXT = "chaosatlas-dify"
NAMESPACE = "dify-k8s-lab"
TARGET_ID = "dify-extension-canary"


def kubectl(args: list[str], *, timeout: int = 45) -> tuple[int, str, str]:
    try:
        result = subprocess.run(["kubectl", "--context", CONTEXT, *args], capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, "", str(exc)
    return result.returncode, result.stdout or "", result.stderr or ""


def _scenario(node: dict, fault: dict, scenario_id: str) -> dict:
    return {
        "schema_version": 3,
        "node_type": "scenario_node",
        "scenario_id": scenario_id,
        "deployment_nodes": [node],
        "phases": [{"phase_id": "dify-disposable-canary", "mode": "ordered", "duration_s": 10, "target_node_ids": [node["node_id"]], "inject_confirmation": "status.injectedCount >= 1", "cleanup_owner": "chaosatlas", "faults": [fault]}],
        "oracle": {"business": {"kind": "http", "service": fault["service_target"], "remote_port": 8080}},
        "recovery": {"deadline_s": 60},
        "cleanup": {"required": True, "owner": "chaosatlas"},
    }


def _probe(service: str, path: str, local_port: int, family: str, threshold: int):
    def hook(phase: str) -> dict:
        process = start_port_forward(NAMESPACE, service, local_port, 8080, kube_context=CONTEXT)
        try:
            wait_for_port("127.0.0.1", local_port, process, 30)
            sample = http_request(local_port, path, "GET", 10.0, None, 65536)
            payload = json.loads(str(sample.get("body") or "{}"))
            if family == "extension.queue_backlog":
                abnormal = payload.get("status") == "backlog" and int(payload.get("depth") or 0) >= threshold
                evidence = {"queue_depth": payload.get("depth"), "queue_name": payload.get("queue_name")}
            else:
                abnormal = payload.get("status") == "exhausted" and int(payload.get("utilization_pct") or 0) >= 100
                evidence = {"pool_in_use": payload.get("in_use"), "pool_capacity": payload.get("capacity"), "utilization_pct": payload.get("utilization_pct"), "pool_name": payload.get("pool_name")}
            if phase == "observe" and abnormal:
                return {"status": "degraded", "phase": phase, "samples": [sample], "mechanism_evidence": evidence}
            return {"status": "pass" if sample.get("status_code") == 200 and not abnormal else "business_unreachable", "phase": phase, "samples": [sample], "mechanism_evidence": evidence}
        except (OSError, RuntimeError, TimeoutError, ValueError, TypeError) as exc:
            return {"status": "business_unreachable", "phase": phase, "samples": [{"error": str(exc)}]}
        finally:
            stop_process(process)
    return hook


def _run_one(output_root: Path, candidate: dict, node: dict, family: str, path: str, local_port: int) -> dict:
    parameters = dict(candidate["parameters"])
    fault = {**candidate, "kind": family, "action": family, "service_target": str(((node.get("service") or {}).get("name")) or node["deployment"]["name"]), "parameters": parameters, "target_node_id": node["node_id"]}
    scenario = _scenario(node, fault, family.replace(".", "-"))
    compiled = compile_scenario(scenario)
    if compiled.get("status") != "verified":
        return {"extension_id": family, "status": "method_invalid", "errors": compiled.get("errors") or []}
    root = output_root / family.replace(".", "-")
    (root / "runtime" / "mutations").mkdir(parents=True, exist_ok=True)
    (root / "compile.json").write_text(json.dumps({"status": "verified", "manifests": compiled["manifests"]}, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    (root / "runtime" / "mutations" / f"{family.replace('.', '-')}.yaml").write_text(yaml.safe_dump(compiled["manifests"][0], sort_keys=False), encoding="utf-8")
    threshold = int(parameters.get("depth") or parameters.get("connections") or 1)
    executor = NativeExtensionFaultExecutor(
        namespace=NAMESPACE,
        allowed_namespaces={NAMESPACE},
        allow_live=True,
        isolated=True,
        runner=lambda args, timeout=45: kubectl(args, timeout=timeout),
        probe=_probe(fault["service_target"], path, local_port, family, threshold),
        target_selector=candidate["selector"],
    )
    result = executor(compiled["manifests"][0], fault=fault)
    result["mutation_ref"] = f"runtime/mutations/{family.replace('.', '-')}.yaml"
    (root / "runtime" / f"{family.replace('.', '-')}.json").write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return {"extension_id": family, "status": result.get("status"), "outcome_status": result.get("outcome_status"), "verdict": result.get("verdict"), "attestation": result.get("attestation"), "observation": result.get("observation"), "recovery": result.get("recovery"), "cleanup": result.get("cleanup"), "errors": result.get("errors") or [], "mutation_ref": result["mutation_ref"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=REPO_ROOT / "projects" / "dify-kubernetes" / "profile.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text(encoding="utf-8-sig"))
    adapter = KubernetesProjectAdapter(profile=profile, kube_context=CONTEXT)
    inventory = adapter.inventory()
    detection = adapter.detect_server_deployment(inventory)
    nodes = {item["node_id"]: item for item in detection.get("deployment_nodes") or []}
    target = next((item for item in nodes.values() if ((item.get("extensions") or {}).get("resource_facts") or {}).get("disposable_target_id") == TARGET_ID), None)
    results: list[dict] = []
    if target is None:
        results.append({"status": "environment_blocked", "errors": [f"disposable target {TARGET_ID} was not discovered"]})
    else:
        for family, path, port in (("extension.queue_backlog", "/queue", 18186), ("extension.connection_pool_exhaustion", "/pool", 18187)):
            candidate = next((item for item in detection.get("extension_candidates") or [] if item.get("extension_id") == family and item.get("node_id") == target["node_id"]), None)
            if candidate is None:
                results.append({"extension_id": family, "status": "environment_blocked", "errors": ["supported candidate was not generated"]})
            else:
                results.append(_run_one(args.output, candidate, target, family, path, port))
    args.output.mkdir(parents=True, exist_ok=True)
    summary = {"schema_version": "chaosatlas-dify-disposable-extension-canary-v1", "checked_at": datetime.now(timezone.utc).isoformat(), "context": CONTEXT, "namespace": NAMESPACE, "target_id": TARGET_ID, "inventory": {"workloads": len(inventory.get("workloads") or []), "statefulsets": len(inventory.get("statefulsets") or []), "dependencies": len(inventory.get("dependencies") or [])}, "results": results, "cleanup": "target_preserved_disposable_only"}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "output": str(args.output), "target": TARGET_ID, "results": [{"extension_id": item.get("extension_id"), "status": item.get("status"), "attestation": (item.get("attestation") or {}).get("valid")} for item in results]}, ensure_ascii=True))
    return 0 if results and all(item.get("status") == "executed" and (item.get("attestation") or {}).get("valid") is True for item in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
