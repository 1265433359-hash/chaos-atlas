"""Execute one compiled OTel two-arm mutation with a strict lifecycle."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from run_chaos_experiment import (  # noqa: E402
    check_mutation,
    delete_resource,
    kubectl_json,
    now,
    run_kubectl,
    start_port_forward,
    stop_process,
    wait_for_lifecycle,
    wait_for_port,
    wait_for_target_ready,
)
from run_grpc_chaos_experiment import run_client  # noqa: E402

NAMESPACE = "chaosatlas-otel"
CLIENT = Path("artifacts/opentelemetry-demo/otel_client.py")
CHAOS_RESOURCES = ("podchaos", "networkchaos", "stresschaos")
OTEL_APPS = {
    "cart",
    "checkout",
    "currency",
    "email",
    "flagd",
    "payment",
    "postgres",
    "product-catalog",
    "quote",
    "shipping",
    "valkey",
}


def consecutive_successes(samples: list[dict[str, Any]]) -> int:
    count = 0
    for sample in samples:
        count = count + 1 if sample.get("grpc_status") == "OK" else 0
    return count


def classify_observation(workload: dict[str, Any]) -> str:
    observations = workload.get("observations") or []
    if not observations:
        return "observation_incomplete"
    return "weakness_observed" if any(item.get("grpc_status") != "OK" for item in observations) else "no_business_impact_observed"


def validate_otel_mutation(document: dict[str, Any]) -> dict[str, Any]:
    metadata = document.get("metadata") or {}
    spec = document.get("spec") or {}
    selector = spec.get("selector") or {}
    labels = selector.get("labelSelectors") or {}
    errors: list[str] = []
    if document.get("kind") not in {"PodChaos", "NetworkChaos", "StressChaos"}:
        errors.append("unsupported chaos kind")
    if metadata.get("namespace") != NAMESPACE:
        errors.append("metadata namespace is not chaosatlas-otel")
    if selector.get("namespaces") != [NAMESPACE]:
        errors.append("selector namespace is not exact")
    if labels.get("app") not in OTEL_APPS or set(labels) != {"app"}:
        errors.append("selector must target a frozen OTel app")
    if spec.get("mode") != "one":
        errors.append("mode must be one")
    if document.get("kind") == "PodChaos" and spec.get("action") != "pod-kill":
        errors.append("PodChaos action must be pod-kill")
    return {"status": "passed" if not errors else "blocked", "errors": errors}


def global_residuals() -> tuple[list[dict[str, Any]], list[str]]:
    residuals: list[dict[str, Any]] = []
    errors: list[str] = []
    for resource in CHAOS_RESOURCES:
        data, error = kubectl_json(["get", resource, "-A"])
        if error:
            errors.append(error)
            continue
        for item in data.get("items", []):
            meta = item.get("metadata") or {}
            residuals.append({"kind": item.get("kind", resource), "namespace": meta.get("namespace"), "name": meta.get("name")})
    return residuals, errors


def capture_diagnostics(report: Path, target_selector: str) -> dict[str, Any]:
    directory = report.parent / f"{report.stem}.diagnostics"
    directory.mkdir(parents=True, exist_ok=True)
    commands = {
        "checkout.log": ["logs", "-n", NAMESPACE, "deployment/checkout", "--tail=500"],
        "cart.log": ["logs", "-n", NAMESPACE, "deployment/cart", "--tail=500"],
        "events.json": ["get", "events", "-n", NAMESPACE, "--sort-by=.lastTimestamp", "-o", "json"],
    }
    files: list[dict[str, Any]] = []
    for filename, command in commands.items():
        code, out, err = run_kubectl(command, timeout=60)
        path = directory / filename
        content = out if filename.endswith(".json") else out + (("\nSTDERR:\n" + err) if err else "")
        if filename.endswith(".json"):
            try:
                content = json.dumps(json.loads(content), indent=2, ensure_ascii=True) + "\n"
            except json.JSONDecodeError:
                content = json.dumps({"status": "unavailable", "return_code": code, "stderr": err, "raw": content}, indent=2) + "\n"
        path.write_text(content, encoding="utf-8")
        files.append({"path": str(path).replace("\\", "/"), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "return_code": code})
    trace = directory / "zipkin.json"
    trace.write_text(json.dumps({"status": "unavailable", "reason": "OTel frozen core manifest has no trace backend", "target_selector": target_selector}, indent=2) + "\n", encoding="utf-8")
    files.append({"path": str(trace).replace("\\", "/"), "sha256": hashlib.sha256(trace.read_bytes()).hexdigest(), "return_code": 0})
    return {"status": "captured", "files": files}


def _healthy_target(namespace: str, labels: dict[str, str]) -> tuple[bool, dict[str, Any], set[str]]:
    query = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
    data, error = kubectl_json(["get", "pods", "-n", namespace, "-l", query])
    if error or not data:
        return False, {"error": error}, set()
    pods = data.get("items", [])
    ready = [p for p in pods if any(c.get("type") == "Ready" and c.get("status") == "True" for c in p.get("status", {}).get("conditions", []))]
    uids = {str(p.get("metadata", {}).get("uid")) for p in pods if p.get("metadata", {}).get("uid")}
    return bool(pods) and len(ready) == len(pods), {"pod_count": len(pods), "ready_count": len(ready), "uids": sorted(uids)}, uids


def collect_successes(client: Path, required: int, timeout: float, processes: list[subprocess.Popen[str] | None]) -> dict[str, Any]:
    started = time.monotonic()
    samples: list[dict[str, Any]] = []
    workloads: list[dict[str, Any]] = []
    while time.monotonic() - started < timeout:
        workload = run_client(client, 15050, 17070, 1, 20)
        workloads.append(workload)
        samples.extend(workload.get("observations") or [{"grpc_status": "CLIENT_PROCESS_ERROR"}])
        if consecutive_successes(samples) >= required:
            return {"recovered": True, "samples": samples, "workloads": workloads, "successes_required": required}
        time.sleep(2)
    return {"recovered": False, "samples": samples, "workloads": workloads, "successes_required": required}


def restart_port_forwards(processes: list[subprocess.Popen[str] | None]) -> None:
    for process in processes:
        stop_process(process)
    processes.clear()
    for service, local, remote in (("checkout", 15050, 5050), ("cart", 17070, 7070)):
        process = start_port_forward(NAMESPACE, service, local, remote)
        processes.append(process)
        wait_for_port("127.0.0.1", local, process, 30)


def run_one(mutation: Path, report_path: Path, arm: str, seed: int, hypothesis_id: str, replicate: int, client: Path, baseline_count: int = 5, washout_seconds: float = 60, washout_successes: int = 10, washout_timeout: float = 180) -> dict[str, Any]:
    if report_path.exists():
        raise FileExistsError(report_path)
    report: dict[str, Any] = {"schema_version": "otel-two-arm-lifecycle-v1", "project_id": "opentelemetry-demo", "namespace": NAMESPACE, "arm": arm, "seed": seed, "mutation_id": hypothesis_id, "replicate": replicate, "mutation": {"path": str(mutation).replace("\\", "/"), "sha256": hashlib.sha256(mutation.read_bytes()).hexdigest()}, "baseline": {"pass": False}, "injection": {"applied": False, "injected": False}, "observation": {}, "recovery": {"recovered": False}, "cleanup": {"absent_confirmed": False}, "washout": {"stable": False}, "diagnostics": {"status": "pending"}, "human_review": "pending", "knowledge_base_updated": False, "status": "running", "errors": []}
    processes: list[subprocess.Popen[str] | None] = []
    kind = name = None
    applied = False
    try:
        document = yaml.safe_load(mutation.read_text(encoding="utf-8"))
        report["mutation_gate"] = validate_otel_mutation(document)
        if report["mutation_gate"]["status"] != "passed":
            raise RuntimeError("OTel mutation validation blocked")
        preflight = check_mutation(mutation)
        report["preflight"] = preflight
        if preflight.get("decision") != "ready_for_injection":
            raise RuntimeError(f"runtime applicability gate: {preflight.get('decision')}")
        kind, name = preflight["kind"], preflight["name"]
        restart_port_forwards(processes)
        baseline = run_client(client, 15050, 17070, baseline_count, max(60, baseline_count * 12))
        report["baseline"] = {"pass": len(baseline.get("observations", [])) == baseline_count and all(x.get("grpc_status") == "OK" for x in baseline.get("observations", [])), "workload": baseline, "successes_required": baseline_count}
        if not report["baseline"]["pass"]:
            raise RuntimeError("OTel baseline was not failure-free")
        code, out, err = run_kubectl(["apply", "-f", str(mutation)])
        report["injection"]["apply"] = {"return_code": code, "stdout": out.strip(), "stderr": err.strip()}
        if code != 0:
            raise RuntimeError("Chaos apply failed")
        applied = True
        report["injection"]["applied"] = True
        injected, lifecycle, errors = wait_for_lifecycle(kind, NAMESPACE, name, "injected", 90, 0.5)
        report["injection"].update({"injected": injected, "lifecycle": lifecycle})
        report["errors"].extend(errors)
        if not injected:
            raise RuntimeError("injection not confirmed")
        observed = run_client(client, 15050, 17070, baseline_count, max(60, baseline_count * 12))
        report["observation"] = {"workload": observed, "classification": classify_observation(observed)}
        labels = ((document.get("spec") or {}).get("selector") or {}).get("labelSelectors") or {}
        targets = ((preflight.get("checks") or {}).get("target_pods") or [])
        pre_uids = {str(item.get("uid")) for item in targets if item.get("uid")}
        expected = None
        if kind == "PodChaos":
            expected = len(pre_uids) or None
            recovered, state, errors = wait_for_target_ready(NAMESPACE, {"labelSelectors": labels}, 180, 1, expected_pod_count=expected, pre_kill_uids=pre_uids)
        else:
            recovered, state, errors = wait_for_lifecycle(kind, NAMESPACE, name, "recovered", 180, 1)
        report["recovery"].update({"resource_recovered": recovered, "state": state})
        report["errors"].extend(errors)
        cleanup = delete_resource(kind, NAMESPACE, name)
        applied = False
        residuals, residual_errors = global_residuals()
        report["cleanup"] = {**cleanup, "residual_resources": residuals, "global_scan_errors": residual_errors}
        if not cleanup.get("absent_confirmed") or residuals or residual_errors:
            raise RuntimeError("cleanup/global residual gate failed")
        restart_port_forwards(processes)
        report["recovery"]["business"] = collect_successes(client, baseline_count, 180, processes)
        report["recovery"]["recovered"] = bool(recovered and report["recovery"]["business"]["recovered"])
        if not report["recovery"]["recovered"]:
            raise RuntimeError("business recovery failed")
        washout_started = time.monotonic()
        washout_samples: list[dict[str, Any]] = []
        while time.monotonic() - washout_started < washout_timeout:
            sample = run_client(client, 15050, 17070, 1, 20)
            washout_samples.extend(sample.get("observations") or [{"grpc_status": "CLIENT_PROCESS_ERROR"}])
            if time.monotonic() - washout_started >= washout_seconds and consecutive_successes(washout_samples) >= washout_successes:
                report["washout"] = {"stable": True, "samples": washout_samples, "successes_required": washout_successes, "elapsed_seconds": round(time.monotonic() - washout_started, 3)}
                break
            time.sleep(3)
        if not report["washout"].get("stable"):
            report["washout"] = {"stable": False, "samples": washout_samples, "successes_required": washout_successes}
            raise RuntimeError("washout failed")
        selector_query = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        report["diagnostics"] = capture_diagnostics(report_path, selector_query)
        report["status"] = "completed"
    except Exception as exc:
        report["errors"].append(f"{type(exc).__name__}: {exc}")
        report["status"] = "failed"
    finally:
        if applied and kind and name:
            report["cleanup"] = {**delete_resource(kind, NAMESPACE, name), "residual_resources": global_residuals()[0]}
        report["port_forwards"] = [stop_process(p) for p in processes]
        report["finished_at"] = now()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mutation", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--arm", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--hypothesis-id", required=True)
    parser.add_argument("--replicate", type=int, choices=(1, 2), required=True)
    parser.add_argument("--client", type=Path, default=CLIENT)
    parser.add_argument("--baseline-count", type=int, default=5)
    parser.add_argument("--washout-seconds", type=float, default=60)
    parser.add_argument("--washout-successes", type=int, default=10)
    parser.add_argument("--washout-timeout", type=float, default=180)
    args = parser.parse_args()
    result = run_one(args.mutation, args.report, args.arm, args.seed, args.hypothesis_id, args.replicate, args.client, args.baseline_count, args.washout_seconds, args.washout_successes, args.washout_timeout)
    print(json.dumps({"status": result["status"], "classification": result.get("observation", {}).get("classification"), "errors": result["errors"]}, ensure_ascii=True))
    return 0 if result["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
