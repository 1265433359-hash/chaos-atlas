"""Run isolated live extension canaries with disposable workload agents."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.compile_scenario_node import compile_scenario
from tools.deployment_capability import build_deployment_node
from tools.extension_fault_compiler import compile_extension_fault
from tools.native_extension_fault_executor import NativeExtensionFaultExecutor
from tools.kubernetes_lifecycle_executor import KubernetesLifecycleExecutor
from tools.run_chaos_experiment import http_request, start_port_forward, stop_process, wait_for_port


CONTEXT = "chaosatlas-dify"
NAMESPACE = "chaosatlas-extension-canary"
PYTHON_IMAGE = "chaosatlas/extension-python:20260904"
JVM_IMAGE = "chaosatlas/extension-jvm:20260903"


def kubectl(args: list[str], *, timeout: int = 120, input_text: str | None = None) -> tuple[int, str, str]:
    try:
        result = subprocess.run(["kubectl", "--context", CONTEXT, *args], input=input_text, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, "", str(exc)
    return result.returncode, result.stdout or "", result.stderr or ""


def docker(args: list[str], *, timeout: int = 900) -> tuple[int, str, str]:
    try:
        result = subprocess.run(["docker", "--context", "desktop-linux", *args], capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, "", str(exc)
    return result.returncode, result.stdout or "", result.stderr or ""


def _node(name: str, selector: dict[str, str], *, io: bool = False, jvm: bool = False, queue: bool = False, pool: bool = False, pause: bool = False) -> dict[str, Any]:
    extensions = {
        "capabilities": {"iochaos": io, "timechaos": True, "jvmchaos": jvm, "queue_agent": queue, "connection_pool_agent": pool, "pause_agent": pause, "disposable_target": True},
        "writable_paths": ["/data"] if io else [],
        "runtime": {"jvm_present": jvm, "process_name": "java" if jvm else "", "pid_hint": 1 if jvm else None},
    }
    deployment = {
        "metadata": {"name": name},
        "spec": {"replicas": 1, "selector": {"matchLabels": selector}, "template": {"metadata": {"labels": selector}, "spec": {"containers": [{"name": "jvm" if jvm else "python"}]}}},
        "extensions": extensions,
    }
    return build_deployment_node(
        project_id="chaosatlas-extension-canary",
        project_commit="0" * 40,
        namespace=NAMESPACE,
        deployment=deployment,
        service={"metadata": {"name": name}, "spec": {"ports": [{"port": 8080}], "selector": selector}},
        source_refs=[f"fixture/deployment/{name}"],
        manifest_sha256="0" * 64,
    )


def _scenario(node: dict[str, Any], fault: dict[str, Any], scenario_id: str) -> dict[str, Any]:
    return {
        "schema_version": 3,
        "node_type": "scenario_node",
        "scenario_id": scenario_id,
        "deployment_nodes": [node],
        "phases": [{"phase_id": "live-canary", "mode": "ordered", "duration_s": 10, "target_node_ids": [node["node_id"]], "inject_confirmation": "status.injectedCount >= 1", "cleanup_owner": "chaosatlas", "faults": [fault]}],
        "oracle": {"business": {"kind": "http", "service": "extension-python" if node["deployment"]["name"] == "extension-python" else "extension-jvm", "remote_port": 8080}},
        "recovery": {"deadline_s": 120},
        "cleanup": {"required": True, "owner": "chaosatlas"},
    }


def _wait_deployments(names: tuple[str, ...]) -> None:
    for name in names:
        code, _, error = kubectl(["-n", NAMESPACE, "rollout", "status", f"deployment/{name}", "--timeout=180s"], timeout=200)
        if code != 0:
            raise RuntimeError(f"deployment {name} did not become ready: {error.strip()}")


def _build_and_load(include_jvm: bool) -> None:
    images = [(PYTHON_IMAGE, "Dockerfile.python.runtime")]
    if include_jvm:
        images.append((JVM_IMAGE, "Dockerfile.jvm"))
    for tag, dockerfile in images:
        code, _, error = docker(["build", "-t", tag, "-f", str(REPO_ROOT / "workloads" / "extension-canary" / dockerfile), str(REPO_ROOT / "workloads" / "extension-canary")])
        if code != 0:
            raise RuntimeError(f"docker build failed for {tag}: {error[-1000:]}")
        code, _, error = subprocess.run(["minikube", "-p", "chaosatlas-dify", "image", "load", tag], capture_output=True, text=True, timeout=300, check=False).returncode, "", ""
        if code != 0:
            raise RuntimeError(f"minikube image load failed for {tag}: {error[-1000:]}")


def _install_fixture(include_jvm: bool) -> None:
    kubectl(["create", "namespace", NAMESPACE], timeout=30)
    documents = list(yaml.safe_load_all((REPO_ROOT / "workloads" / "extension-canary" / "k8s.yaml").read_text(encoding="utf-8")))
    if not include_jvm:
        documents = [document for document in documents if (document.get("metadata") or {}).get("name") != "extension-jvm"]
    manifest = yaml.safe_dump_all(documents, sort_keys=False)
    names = ("extension-python", "extension-jvm") if include_jvm else ("extension-python",)
    code, _, error = kubectl(["-n", NAMESPACE, "apply", "-f", "-"], input_text=manifest)
    if code != 0:
        raise RuntimeError(f"fixture apply failed: {error[-1000:]}")
    _wait_deployments(names)


def _probe(service: str, path: str, local_port: int, *, clock_baseline: list[float] | None = None):
    def hook(phase: str, _manifest: dict[str, Any]) -> dict[str, Any]:
        process = start_port_forward(NAMESPACE, service, local_port, 8080, kube_context=CONTEXT)
        try:
            wait_for_port("127.0.0.1", local_port, process, 30)
            sample = http_request(local_port, path, "GET", 10.0, None, 65536)
            body = str(sample.get("body") or "")
            payload = json.loads(body) if body else {}
            if phase == "baseline" and clock_baseline is not None and isinstance(payload.get("epoch"), (int, float)):
                clock_baseline.append(float(payload["epoch"]))
            if phase == "observe" and clock_baseline is not None and isinstance(payload.get("epoch"), (int, float)):
                offset = float(payload["epoch"]) - time.time()
                sample["clock_offset_s"] = offset
                if abs(offset) >= 0.2:
                    return {"status": "degraded", "phase": phase, "samples": [sample], "mechanism_evidence": {"clock_offset_s": offset}}
            status = "pass" if sample.get("status_code") == 200 else "business_unreachable"
            return {"status": status, "phase": phase, "samples": [sample]}
        except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
            return {"status": "business_unreachable", "phase": phase, "samples": [{"error": str(exc)}]}
        finally:
            stop_process(process)
    return hook


def _run_one(root: Path, node: dict[str, Any], extension_id: str, parameters: dict[str, Any], service: str, path: str, local_port: int) -> dict[str, Any]:
    fault = {"kind": extension_id, "action": extension_id, "selector": node["deployment"]["selector"], "parameters": parameters, "target_node_id": node["node_id"]}
    scenario = _scenario(node, fault, f"extension-{extension_id.split('.', 1)[1]}")
    compiled = compile_scenario(scenario)
    if compiled.get("status") != "verified":
        return {"extension_id": extension_id, "status": "method_invalid", "errors": compiled.get("errors") or []}
    baseline_clock: list[float] = []
    executor = KubernetesLifecycleExecutor(
        root=root,
        namespace=NAMESPACE,
        allowed_namespaces={NAMESPACE},
        allow_live=True,
        oracle={"kind": "http", "service": service, "remote_port": 8080, "local_port": local_port, "entrypoint": path, "expected_status": 200},
        hooks={"probe": _probe(service, path, local_port, clock_baseline=baseline_clock if extension_id == "extension.time_offset" else None)},
        poll_interval=0.5,
        injection_timeout=60.0,
        recovery_timeout=120.0,
        kube_context=CONTEXT,
    )
    manifest = compiled["manifests"][0]
    result = executor.run(manifest, action_id=f"{extension_id.replace('.', '-')}-20260903")
    return {"extension_id": extension_id, "status": result.get("status"), "outcome_status": result.get("outcome_status"), "verdict": result.get("verdict"), "attestation": result.get("attestation"), "injection": result.get("injection"), "observation": result.get("observation"), "recovery": result.get("recovery"), "cleanup": result.get("cleanup"), "errors": result.get("errors") or [], "mechanism_evidence": result.get("mechanism_evidence")}


def _native_probe(service: str, path: str, local_port: int, family: str, threshold: int):
    def hook(phase: str) -> dict[str, Any]:
        process = start_port_forward(NAMESPACE, service, local_port, 8080, kube_context=CONTEXT)
        try:
            wait_for_port("127.0.0.1", local_port, process, 30)
            sample = http_request(local_port, path, "GET", 10.0, None, 65536)
            payload = json.loads(str(sample.get("body") or "{}"))
            if family == "extension.queue_backlog":
                abnormal = payload.get("status") == "backlog" and int(payload.get("depth") or 0) >= threshold
                signal = {"queue_depth": payload.get("depth"), "queue_name": payload.get("queue_name")}
            elif family == "extension.connection_pool_exhaustion":
                abnormal = payload.get("status") == "exhausted" and int(payload.get("utilization_pct") or 0) >= 100
                signal = {"pool_in_use": payload.get("in_use"), "pool_capacity": payload.get("capacity"), "utilization_pct": payload.get("utilization_pct"), "pool_name": payload.get("pool_name")}
            else:
                abnormal = payload.get("status") == "paused"
                signal = {"target_process": payload.get("target_process"), "pause_ms": payload.get("pause_ms")}
            if phase == "observe" and abnormal:
                return {"status": "degraded", "phase": phase, "samples": [sample], "mechanism_evidence": signal}
            status = "pass" if sample.get("status_code") == 200 and not abnormal else "business_unreachable"
            return {"status": status, "phase": phase, "samples": [sample], "mechanism_evidence": signal}
        except (OSError, RuntimeError, TimeoutError, ValueError, TypeError) as exc:
            return {"status": "business_unreachable", "phase": phase, "samples": [{"error": str(exc)}]}
        finally:
            stop_process(process)
    return hook


def _run_native_one(root: Path, node: dict[str, Any], extension_id: str, parameters: dict[str, Any], path: str, local_port: int) -> dict[str, Any]:
    fault = {"kind": extension_id, "action": extension_id, "selector": node["deployment"]["selector"], "parameters": parameters, "target_node_id": node["node_id"]}
    scenario = _scenario(node, fault, f"extension-{extension_id.split('.', 1)[1]}")
    compiled = compile_scenario(scenario)
    if compiled.get("status") != "verified":
        return {"extension_id": extension_id, "status": "method_invalid", "errors": compiled.get("errors") or []}
    runtime_root = root / "runtime"
    mutation_root = runtime_root / "mutations"
    mutation_root.mkdir(parents=True, exist_ok=True)
    mutation_path = mutation_root / f"{extension_id.replace('.', '-')}.yaml"
    mutation_path.write_text(yaml.safe_dump(compiled["manifests"][0], sort_keys=False), encoding="utf-8")
    (root / "compile.json").write_text(json.dumps({"status": "verified", "manifests": compiled["manifests"]}, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    threshold = int(parameters.get("depth") or parameters.get("connections") or 1)
    service = node["deployment"]["name"]
    executor = NativeExtensionFaultExecutor(
        namespace=NAMESPACE,
        allowed_namespaces={NAMESPACE},
        allow_live=True,
        isolated=True,
        runner=lambda args, timeout=45: kubectl(args, timeout=timeout),
        probe=_native_probe(service, path, local_port, extension_id, threshold),
        target_selector=node["deployment"]["selector"],
    )
    result = executor(compiled["manifests"][0], fault=fault)
    result["mutation_ref"] = str(mutation_path.relative_to(root)).replace("\\", "/")
    result_path = runtime_root / f"{extension_id.replace('.', '-')}.json"
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return {"extension_id": extension_id, "status": result.get("status"), "outcome_status": result.get("outcome_status"), "verdict": result.get("verdict"), "attestation": result.get("attestation"), "injection": result.get("injection"), "observation": result.get("observation"), "recovery": result.get("recovery"), "cleanup": result.get("cleanup"), "errors": result.get("errors") or [], "mechanism_evidence": (result.get("observation") or {}).get("mechanism_evidence")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--skip-jvm", action="store_true", help="Run the five non-JVM extension canaries and record JVM as inapplicable")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    try:
        if not args.skip_build:
            _build_and_load(not args.skip_jvm)
        _install_fixture(not args.skip_jvm)
        python_node = _node("extension-python", {"app": "extension-python"}, io=True, queue=True, pool=True, pause=True)
        results.append(_run_one(args.output / "io-delay", python_node, "extension.io_delay", {"path": "/data", "latency_ms": 100, "percent": 100, "duration_s": 10}, "extension-python", "/io", 18082))
        results.append(_run_one(args.output / "io-error", python_node, "extension.io_error", {"path": "/data", "errno": 5, "percent": 100, "duration_s": 10}, "extension-python", "/io", 18083))
        results.append(_run_one(args.output / "time-offset", python_node, "extension.time_offset", {"offset_ms": 500, "duration_s": 10}, "extension-python", "/clock", 18084))
        results.append(_run_native_one(args.output / "queue-backlog", python_node, "extension.queue_backlog", {"queue_name": "chaosatlas-test-queue", "depth": 100, "duration_s": 10}, "/queue", 18086))
        results.append(_run_native_one(args.output / "connection-pool-exhaustion", python_node, "extension.connection_pool_exhaustion", {"pool_name": "chaosatlas-test-pool", "connections": 20, "duration_s": 10}, "/pool", 18087))
        results.append(_run_native_one(args.output / "runtime-pause", python_node, "extension.runtime_pause", {"target_process": "python", "pause_ms": 100, "duration_s": 10}, "/runtime", 18088))
        if args.skip_jvm:
            results.append({"extension_id": "extension.jvm_gc_pause", "status": "inapplicable", "reason": "Dify target has no JVM runtime; JVM canary was intentionally not run in three-extension mode"})
        else:
            jvm_node = _node("extension-jvm", {"app": "extension-jvm"}, jvm=True)
            results.append(_run_one(args.output / "jvm-gc-pause", jvm_node, "extension.jvm_gc_pause", {"target_process": "java", "pause_ms": 100, "duration_s": 10}, "extension-jvm", "/health", 18085))
    except Exception as exc:
        results.append({"status": "runner_error", "errors": [f"{type(exc).__name__}: {exc}"]})
    finally:
        kubectl(["delete", "namespace", NAMESPACE, "--ignore-not-found=true", "--wait=true"], timeout=180)
    summary = {"schema_version": "chaosatlas-extension-canary-v1", "checked_at": datetime.now(timezone.utc).isoformat(), "context": CONTEXT, "namespace": NAMESPACE, "results": results, "cleanup": "namespace_deleted"}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "output": str(args.output), "results": [{"extension_id": item.get("extension_id"), "status": item.get("status"), "attestation": (item.get("attestation") or {}).get("valid")} for item in results]}, ensure_ascii=True))
    complete = {
        "executed": lambda item: (item.get("attestation") or {}).get("valid") is True,
        "inapplicable": lambda _item: True,
    }
    return 0 if results and all(complete.get(item.get("status"), lambda _item: False)(item) for item in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
