"""Execute one Online Boutique mutation with the unified two-arm lifecycle."""

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

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from run_chaos_experiment import (  # noqa: E402
    check_mutation, delete_resource, kubectl_json, now, run_kubectl,
    start_port_forward, stop_process, wait_for_lifecycle, wait_for_port,
    wait_for_target_ready,
)
from run_grpc_chaos_experiment import run_client  # noqa: E402
from unified_experiment_protocol import comparison_eligibility  # noqa: E402


PROJECT_ID = "online-boutique"
NAMESPACE = "chaosatlas-online-boutique"


def workload_passes(workload: dict[str, Any], required: int) -> bool:
    observations = workload.get("observations") or []
    return len(observations) == required and all(item.get("grpc_status") == "OK" for item in observations)


def is_port_forward_failure(workload: dict[str, Any], transport_text: str = "") -> bool:
    observations = workload.get("observations") or []
    if not observations or all(item.get("grpc_status") == "OK" for item in observations):
        return False
    evidence = " ".join(
        str(value)
        for value in (workload.get("stdout"), workload.get("stderr"), transport_text)
        if value
    ).lower()
    local_oracle = "127.0.0.1:15050" in evidence or "127.0.0.1:17070" in evidence
    return local_oracle and (
        "connection refused" in evidence or "end of tcp stream" in evidence
    )


def consecutive_successes(samples: list[dict[str, Any]]) -> int:
    count = 0
    for sample in samples:
        count = count + 1 if sample.get("grpc_status") == "OK" else 0
    return count


def collect_sustained_successes(
    run_sample: Any,
    required: int,
    timeout: float,
    poll_interval: float = 3.0,
    monotonic: Any = time.monotonic,
    sleep: Any = time.sleep,
    on_port_forward_failure: Any = None,
) -> dict[str, Any]:
    started = monotonic()
    deadline = started + timeout
    samples: list[dict[str, Any]] = []
    workloads: list[dict[str, Any]] = []
    reconnects = 0
    last_checked = started
    while (last_checked := monotonic()) < deadline:
        workload = run_sample()
        workloads.append(workload)
        observations = workload.get("observations") or [{"grpc_status": "CLIENT_PROCESS_ERROR"}]
        samples.extend(observations)
        successes = consecutive_successes(samples)
        if successes >= required:
            return {
                "recovered": True,
                "samples": samples,
                "workloads": workloads,
                "consecutive_successes": successes,
                "successes_required": required,
                "elapsed_seconds": round(last_checked - started, 3),
                "port_forward_reconnects": reconnects,
            }
        if is_port_forward_failure(workload) and on_port_forward_failure is not None:
            if on_port_forward_failure():
                reconnects += 1
        sleep(poll_interval)
    return {
        "recovered": False,
        "samples": samples,
        "workloads": workloads,
        "consecutive_successes": consecutive_successes(samples),
        "successes_required": required,
        "elapsed_seconds": round(last_checked - started, 3),
        "port_forward_reconnects": reconnects,
    }


def classify_observation(workload: dict[str, Any]) -> str:
    observations = workload.get("observations") or []
    if not observations:
        return "observation_incomplete"
    if any(item.get("grpc_status") != "OK" for item in observations):
        return "weakness_observed"
    return "no_business_impact_observed"


def global_residuals() -> tuple[list[dict[str, str]], list[str]]:
    residuals: list[dict[str, str]] = []
    errors: list[str] = []
    for resource in ("podchaos", "networkchaos", "stresschaos"):
        data, error = kubectl_json(["get", resource, "-A"])
        if error:
            errors.append(error)
            continue
        for item in data.get("items", []):
            meta = item.get("metadata", {})
            residuals.append({"kind": item.get("kind", resource), "namespace": meta.get("namespace", ""), "name": meta.get("name", "")})
    return residuals, errors


def capture_diagnostics(report_path: Path, target_selector: str) -> dict[str, Any]:
    directory = report_path.parent / f"{report_path.stem}.diagnostics"
    directory.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, str]] = []
    commands = {
        "events.log": ["get", "events", "-n", NAMESPACE, "--sort-by=.lastTimestamp"],
        "checkoutservice.log": ["logs", "-n", NAMESPACE, "deployment/checkoutservice", "--tail=500"],
        "cartservice.log": ["logs", "-n", NAMESPACE, "deployment/cartservice", "--tail=500"],
        "target.log": ["logs", "-n", NAMESPACE, "-l", target_selector, "--tail=500"],
    }
    for filename, command in commands.items():
        code, stdout, stderr = run_kubectl(command, timeout=60)
        path = directory / filename
        path.write_text(stdout + ("\nSTDERR:\n" + stderr if stderr else ""), encoding="utf-8")
        files.append({"path": str(path).replace("\\", "/"), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "return_code": str(code)})
    unavailable = directory / "trace-unavailable.json"
    unavailable.write_text(json.dumps({"status": "unavailable", "reason": "Online Boutique r4 has no frozen trace backend oracle"}, indent=2) + "\n", encoding="utf-8")
    files.append({"path": str(unavailable).replace("\\", "/"), "sha256": hashlib.sha256(unavailable.read_bytes()).hexdigest(), "return_code": "0"})
    return {"status": "captured", "files": files}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mutation", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--client-script", type=Path, default=Path("artifacts/online-boutique/ob_client.py"))
    parser.add_argument("--arm", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--hypothesis-id", required=True)
    parser.add_argument("--replicate", type=int, choices=(1, 2), required=True)
    parser.add_argument("--baseline-count", type=int, default=5)
    parser.add_argument("--observation-count", type=int, default=5)
    parser.add_argument("--recovery-count", type=int, default=5)
    parser.add_argument("--recovery-timeout", type=float, default=180.0)
    parser.add_argument("--recovery-poll-interval", type=float, default=3.0)
    parser.add_argument("--washout-seconds", type=float, default=60.0)
    parser.add_argument("--washout-successes", type=int, default=10)
    parser.add_argument("--washout-timeout", type=float, default=180.0)
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError(f"refusing to overwrite report: {args.report}")
    mutation_hash = hashlib.sha256(args.mutation.read_bytes()).hexdigest()
    report: dict[str, Any] = {
        "schema_version": "unified-lifecycle-v1", "project_id": PROJECT_ID,
        "namespace": NAMESPACE, "arm": args.arm, "seed": args.seed,
        "mutation_id": args.hypothesis_id, "replicate": args.replicate,
        "mutation": {"path": str(args.mutation).replace("\\", "/"), "sha256": mutation_hash},
        "baseline": {"pass": False}, "injection": {"applied": False, "injected": False},
        "observation": {}, "recovery": {"recovered": False},
        "cleanup": {"absent_confirmed": False, "residual_resources": []},
        "washout": {"stable": False, "samples": []}, "diagnostics": {"status": "pending"},
        "human_review": "pending", "knowledge_base_updated": False,
        "status": "running", "errors": [], "started_at": now(),
    }
    processes: list[subprocess.Popen[str] | None] = []
    applied = False
    kind = name = None
    selector_query = ""
    try:
        preflight = check_mutation(args.mutation)
        report["preflight"] = preflight
        if preflight.get("decision") != "ready_for_injection" or preflight.get("namespace") != NAMESPACE:
            raise RuntimeError(f"preflight decision: {preflight.get('decision')}")
        kind, name = preflight.get("kind"), preflight.get("name")
        labels = (preflight.get("selector") or {}).get("labelSelectors") or {}
        selector_query = ",".join(f"{key}={value}" for key, value in sorted(labels.items()))
        for service, local, remote in (("checkoutservice", 15050, 5050), ("cartservice", 17070, 7070)):
            process = start_port_forward(NAMESPACE, service, local, remote)
            processes.append(process)
            wait_for_port("127.0.0.1", local, process, 30)

        def reconnect_port_forwards() -> bool:
            try:
                for process in processes:
                    stop_process(process)
                processes.clear()
                for service, local, remote in (("checkoutservice", 15050, 5050), ("cartservice", 17070, 7070)):
                    process = start_port_forward(NAMESPACE, service, local, remote)
                    processes.append(process)
                    wait_for_port("127.0.0.1", local, process, 30)
                return True
            except (OSError, RuntimeError, TimeoutError):
                return False
        baseline = run_client(args.client_script, 15050, 17070, args.baseline_count, max(60, args.baseline_count * 12))
        report["baseline"] = {"pass": workload_passes(baseline, args.baseline_count), "workload": baseline, "successes_required": args.baseline_count}
        if not report["baseline"]["pass"]:
            raise RuntimeError("baseline was not failure-free")
        code, stdout, stderr = run_kubectl(["apply", "-f", str(args.mutation)])
        report["injection"]["apply"] = {"return_code": code, "stdout": stdout.strip(), "stderr": stderr.strip()}
        if code != 0:
            raise RuntimeError("kubectl apply failed")
        applied = True
        report["injection"]["applied"] = True
        injected, lifecycle, errors = wait_for_lifecycle(kind, NAMESPACE, name, "injected", 60, 0.5)
        report["injection"].update(injected=injected, lifecycle=lifecycle)
        report["errors"].extend(errors)
        if not injected:
            raise RuntimeError("injection was not confirmed")
        observed = run_client(args.client_script, 15050, 17070, args.observation_count, max(60, args.observation_count * 12))
        report["observation"] = {"workload": observed, "classification": classify_observation(observed)}
        if kind == "PodChaos":
            targets = (preflight.get("checks") or {}).get("target_pods") or []
            expected = len(targets) or None
            uids = {str(item.get("uid")) for item in targets if item.get("uid")} or None
            recovered, recovery_state, errors = wait_for_target_ready(NAMESPACE, preflight.get("selector") or {}, 180, 1, expected_pod_count=expected, pre_kill_uids=uids)
        else:
            recovered, recovery_state, errors = wait_for_lifecycle(kind, NAMESPACE, name, "recovered", 180, 1)
        report["recovery"].update(resource_recovered=recovered, state=recovery_state)
        report["errors"].extend(errors)
        cleanup = delete_resource(kind, NAMESPACE, name)
        applied = False
        residuals, residual_errors = global_residuals()
        report["cleanup"] = {**cleanup, "residual_resources": residuals, "global_scan_errors": residual_errors}
        if not cleanup.get("absent_confirmed") or residuals or residual_errors:
            raise RuntimeError("cleanup or global residual scan failed")
        business_recovery = collect_sustained_successes(
            lambda: run_client(args.client_script, 15050, 17070, 1, 15),
            required=args.recovery_count,
            timeout=args.recovery_timeout,
            poll_interval=args.recovery_poll_interval,
            on_port_forward_failure=reconnect_port_forwards,
        )
        recovery_workload = {"observations": business_recovery["samples"]}
        report["recovery"].update(
            workload=recovery_workload,
            business=business_recovery,
            recovered=bool(recovered and business_recovery["recovered"]),
        )
        if not report["recovery"]["recovered"]:
            raise RuntimeError("business workload did not recover")
        washout_started = time.monotonic()
        deadline = washout_started + args.washout_timeout
        samples: list[dict[str, Any]] = []
        while time.monotonic() < deadline:
            sample = run_client(args.client_script, 15050, 17070, 1, 15)
            observations = sample.get("observations") or [{"grpc_status": "CLIENT_PROCESS_ERROR"}]
            samples.extend(observations)
            elapsed = time.monotonic() - washout_started
            if elapsed >= args.washout_seconds and consecutive_successes(samples) >= args.washout_successes:
                report["washout"] = {"stable": True, "samples": samples, "elapsed_seconds": round(elapsed, 3), "successes_required": args.washout_successes}
                break
            time.sleep(3)
        if not report["washout"].get("stable"):
            report["washout"].update(samples=samples, elapsed_seconds=round(time.monotonic() - washout_started, 3), successes_required=args.washout_successes)
            raise RuntimeError("washout did not regain sustained health")
        report["diagnostics"] = capture_diagnostics(args.report, selector_query)
        report["status"] = "completed"
    except (OSError, RuntimeError, TimeoutError, ValueError, yaml.YAMLError) as exc:
        report["errors"].append(f"{type(exc).__name__}: {exc}")
        report["status"] = "failed"
    finally:
        if applied and kind and name:
            cleanup = delete_resource(kind, NAMESPACE, name)
            residuals, residual_errors = global_residuals()
            report["cleanup"] = {**cleanup, "residual_resources": residuals, "global_scan_errors": residual_errors}
        report["port_forwards"] = [stop_process(process) for process in processes]
        report["finished_at"] = now()
        report["eligibility"] = comparison_eligibility(report)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "classification": report.get("observation", {}).get("classification"), "eligible": report["eligibility"]["eligible"], "errors": report["errors"]}))
    return 0 if report["status"] == "completed" and report["eligibility"]["eligible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
