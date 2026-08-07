"""Verify whether a probe restart escapes a still-active NetworkChaos."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any

from run_chaos_experiment import (
    delete_resource,
    kubectl_json,
    now,
    run_kubectl,
    start_port_forward,
    stop_process,
    wait_for_lifecycle,
    wait_for_port,
)
from run_grpc_chaos_experiment import baseline_is_valid, run_client
from runtime_applicability_gate import check_mutation, ready_condition


def target_state(namespace: str, labels: dict[str, Any]) -> dict[str, Any]:
    selector = ",".join(f"{key}={value}" for key, value in sorted(labels.items()))
    args = ["get", "pods", "-n", namespace]
    if selector:
        args.extend(["-l", selector])
    data, error = kubectl_json(args)
    if error:
        raise RuntimeError(error)
    pods = [
        pod
        for pod in data.get("items", [])
        if not pod.get("metadata", {}).get("deletionTimestamp")
    ]
    if len(pods) != 1:
        raise RuntimeError(f"expected exactly one stable target pod, found {len(pods)}")
    pod = pods[0]
    return {
        "pod": pod.get("metadata", {}).get("name"),
        "ready": ready_condition(pod),
        "restarts": sum(
            int(item.get("restartCount", 0))
            for item in pod.get("status", {}).get("containerStatuses", [])
        ),
    }


def wait_for_restart(
    namespace: str,
    labels: dict[str, Any],
    initial_restarts: int,
    timeout: float,
    poll_interval: float,
) -> tuple[bool, bool, dict[str, Any], list[dict[str, Any]]]:
    deadline = time.monotonic() + timeout
    timeline: list[dict[str, Any]] = []
    latest: dict[str, Any] = {}
    restart_detected = False
    while time.monotonic() < deadline:
        latest = target_state(namespace, labels)
        timeline.append({"observed_at": now(), **latest})
        restart_detected = restart_detected or latest["restarts"] > initial_restarts
        if restart_detected and latest["ready"]:
            return True, True, latest, timeline
        time.sleep(poll_interval)
    return restart_detected, False, latest, timeline


def wait_for_ready_target(
    namespace: str,
    labels: dict[str, Any],
    timeout: float,
    poll_interval: float,
) -> tuple[bool, dict[str, Any]]:
    deadline = time.monotonic() + timeout
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = target_state(namespace, labels)
        if latest["ready"]:
            return True, latest
        time.sleep(poll_interval)
    return False, latest


def first_observation(workload: dict[str, Any]) -> dict[str, Any]:
    observations = workload.get("observations") or []
    return observations[0] if observations else {}


def wait_for_valid_workload(
    script: Path,
    checkout_local_port: int,
    cart_local_port: int,
    timeout: float,
    poll_interval: float,
) -> tuple[bool, dict[str, Any], list[dict[str, Any]]]:
    deadline = time.monotonic() + timeout
    attempts: list[dict[str, Any]] = []
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = run_client(script, checkout_local_port, cart_local_port, 1, 15.0)
        attempts.append(latest)
        if baseline_is_valid(latest):
            return True, latest, attempts
        time.sleep(poll_interval)
    return False, latest, attempts


def classify_escape(
    baseline: dict[str, Any],
    injected: dict[str, Any],
    after_restart: dict[str, Any],
    reinjected: dict[str, Any],
    restart_detected: bool,
) -> str:
    observations = [
        first_observation(item)
        for item in (baseline, injected, after_restart, reinjected)
    ]
    if not restart_detected:
        return "probe_restart_not_observed"
    baseline_observation, injected_observation, after_observation, reinjected_observation = observations
    if any(
        item.get("grpc_status") != "OK"
        for item in (baseline_observation, injected_observation, reinjected_observation)
    ):
        return "inconclusive_workload_error"
    latencies = [item.get("latency_ms") for item in observations]
    if any(value is None for value in latencies):
        return "inconclusive_missing_latency"
    base, during, escaped, again = (float(value) for value in latencies)
    if after_observation.get("grpc_status") != "OK":
        if during >= base + 1000 and again >= base + 1000:
            return "probe_restart_connection_failure_confirmed"
        return "inconclusive_workload_error"
    if during >= base + 1000 and escaped <= base + 500 and again >= escaped + 1000:
        return "probe_restart_escape_confirmed"
    return "restart_observed_without_escape_pattern"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mutation", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--client-script", type=Path, required=True)
    parser.add_argument("--checkout-service", default="checkoutservice")
    parser.add_argument("--cart-service", default="cartservice")
    parser.add_argument("--checkout-local-port", type=int, default=35050)
    parser.add_argument("--cart-local-port", type=int, default=37070)
    parser.add_argument("--restart-timeout", type=float, default=120.0)
    parser.add_argument("--poll-interval", type=float, default=3.0)
    parser.add_argument("--post-restart-settle", type=float, default=5.0)
    args = parser.parse_args()

    report: dict[str, Any] = {
        "schema_version": 1,
        "tool": "run_probe_restart_escape",
        "started_at": now(),
        "mutation": str(args.mutation).replace("\\", "/"),
        "preflight": None,
        "baseline": None,
        "first_injection": {},
        "restart_timeline": [],
        "after_restart": None,
        "reinjection": {},
        "cleanup": [],
        "errors": [],
    }
    processes: list[subprocess.Popen[str] | None] = []
    active_resource: tuple[str, str, str] | None = None
    try:
        preflight = check_mutation(args.mutation)
        report["preflight"] = preflight
        if preflight.get("decision") != "ready_for_injection":
            raise RuntimeError(f"preflight decision: {preflight.get('decision')}")
        namespace = preflight["namespace"]
        kind = preflight["kind"]
        name = preflight["name"]
        labels = preflight["selector"].get("labelSelectors") or {}
        active_resource = (kind, namespace, name)

        for service, local_port, remote_port in (
            (args.checkout_service, args.checkout_local_port, 5050),
            (args.cart_service, args.cart_local_port, 7070),
        ):
            process = start_port_forward(namespace, service, local_port, remote_port)
            processes.append(process)
            wait_for_port("127.0.0.1", local_port, process, 15.0)

        report["baseline"] = run_client(
            args.client_script,
            args.checkout_local_port,
            args.cart_local_port,
            1,
            15.0,
        )
        if not baseline_is_valid(report["baseline"]):
            raise RuntimeError("baseline produced no successful gRPC response")
        before = target_state(namespace, labels)
        report["target_before"] = before

        code, stdout, stderr = run_kubectl(["apply", "-f", str(args.mutation)])
        report["first_injection"]["apply"] = {
            "return_code": code,
            "stdout": stdout.strip(),
            "stderr": stderr.strip(),
        }
        if code != 0:
            raise RuntimeError("first kubectl apply failed")
        injected, status, errors = wait_for_lifecycle(kind, namespace, name, "injected", 45.0, 0.5)
        report["first_injection"].update(injected=injected, status=status)
        report["errors"].extend(errors)
        if not injected:
            raise RuntimeError("first injection was not confirmed")
        report["first_injection"]["workload"] = run_client(
            args.client_script,
            args.checkout_local_port,
            args.cart_local_port,
            1,
            15.0,
        )

        restart_detected, ready_after_restart, state, timeline = wait_for_restart(
            namespace,
            labels,
            before["restarts"],
            args.restart_timeout,
            args.poll_interval,
        )
        report["restart_detected"] = restart_detected
        report["target_ready_after_restart"] = ready_after_restart
        report["target_after_restart"] = state
        report["restart_timeline"] = timeline
        if ready_after_restart:
            time.sleep(args.post_restart_settle)
        report["after_restart"] = run_client(
            args.client_script,
            args.checkout_local_port,
            args.cart_local_port,
            1,
            15.0,
        )

        report["cleanup"].append(delete_resource(kind, namespace, name))
        active_resource = None
        target_recovered, recovered_state = wait_for_ready_target(
            namespace, labels, 120.0, args.poll_interval
        )
        report["target_recovered_after_cleanup"] = target_recovered
        report["target_after_cleanup"] = recovered_state
        if not target_recovered:
            raise RuntimeError("target did not become Ready after first cleanup")
        workload_recovered, recovery_workload, recovery_attempts = wait_for_valid_workload(
            args.client_script,
            args.checkout_local_port,
            args.cart_local_port,
            90.0,
            args.poll_interval,
        )
        report["workload_recovered_after_cleanup"] = workload_recovered
        report["recovery_workload"] = recovery_workload
        report["recovery_workload_attempts"] = recovery_attempts
        if not workload_recovered:
            raise RuntimeError("business workload did not recover after first cleanup")
        recheck = check_mutation(args.mutation)
        report["reinjection"]["preflight"] = recheck
        if recheck.get("decision") != "ready_for_injection":
            raise RuntimeError(f"reinjection preflight decision: {recheck.get('decision')}")
        code, stdout, stderr = run_kubectl(["apply", "-f", str(args.mutation)])
        report["reinjection"]["apply"] = {
            "return_code": code,
            "stdout": stdout.strip(),
            "stderr": stderr.strip(),
        }
        if code != 0:
            raise RuntimeError("reinjection kubectl apply failed")
        active_resource = (kind, namespace, name)
        reinjected, status, errors = wait_for_lifecycle(kind, namespace, name, "injected", 45.0, 0.5)
        report["reinjection"].update(injected=reinjected, status=status)
        report["errors"].extend(errors)
        if not reinjected:
            raise RuntimeError("reinjection was not confirmed")
        report["reinjection"]["workload"] = run_client(
            args.client_script,
            args.checkout_local_port,
            args.cart_local_port,
            1,
            15.0,
        )
        report["result_classification"] = classify_escape(
            report["baseline"],
            report["first_injection"]["workload"],
            report["after_restart"],
            report["reinjection"]["workload"],
            restart_detected,
        )
    except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
        report["errors"].append(str(exc))
        report["result_classification"] = "runner_error"
    finally:
        if active_resource:
            report["cleanup"].append(delete_resource(*active_resource))
        report["port_forwards"] = [stop_process(process) for process in processes]
        report["finished_at"] = now()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if report.get("result_classification") in {
        "probe_restart_escape_confirmed",
        "probe_restart_connection_failure_confirmed",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
