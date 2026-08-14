"""Run an isolated Chaos Mesh mutation around a gRPC workload client."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml

try:
    from run_chaos_experiment import (
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
    from classify_runtime_result import exit_code_for_classification
    from environment_fingerprint import load_fingerprint  # phase-5 provenance
except ImportError as exc:  # pragma: no cover
    raise SystemExit("run this script from the repository with tools/ on the import path") from exc


CLIENT_LINE = re.compile(r"^\[(?P<sample>\d+)\]\s+(?P<result>.*?)\s+\((?P<latency>[0-9.]+)ms\)\s*$")
CLIENT_CART_FAILURE_LINE = re.compile(r"^\[(?P<sample>\d+)\]\s+(?P<result>cart_add_failed\b.*)$")
CLIENT_SAMPLE_BLOCK = re.compile(
    r"^\[(?P<sample>\d+)\]\s+(?P<body>.*?)(?=^\[\d+\]\s+|\Z)",
    re.MULTILINE | re.DOTALL,
)
CLIENT_LATENCY_SUFFIX = re.compile(r"\s*\((?P<latency>[0-9.]+)ms\)\s*\Z", re.DOTALL)


def parse_client_output(stdout: str, stderr: str = "") -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for match in CLIENT_SAMPLE_BLOCK.finditer(stdout):
        body = match.group("body").strip()
        latency_match = CLIENT_LATENCY_SUFFIX.search(body)
        latency_ms = float(latency_match.group("latency")) if latency_match else None
        result = body[:latency_match.start()].strip() if latency_match else body
        if result.startswith("ok "):
            status = "OK"
            error = None
        elif result.startswith("rpc_error "):
            code_match = re.search(r"code=(?P<code>[A-Z0-9_]+)", result)
            status = code_match.group("code") if code_match else "RPC_ERROR"
            error = result
        elif result.startswith("cart_add_failed"):
            status = "CART_ADD_FAILED"
            error = result
        else:
            status = "UNKNOWN"
            error = result
        observations.append(
            {
                "sample": int(match.group("sample")) + 1,
                "grpc_status": status,
                "latency_ms": latency_ms,
                "result": result,
                "error": error,
            }
        )
    if not observations and (stdout.strip() or stderr.strip()):
        observations.append(
            {
                "sample": 1,
                "grpc_status": "CLIENT_PROCESS_ERROR",
                "latency_ms": None,
                "result": stdout.strip(),
                "error": stderr.strip() or "client produced no parseable observation",
            }
        )
    return observations


def run_client(
    script: Path,
    checkout_local_port: int,
    cart_local_port: int,
    count: int,
    timeout: float,
) -> dict[str, Any]:
    started = time.monotonic()
    command = [
        sys.executable,
        str(script),
        f"127.0.0.1:{checkout_local_port}",
        f"127.0.0.1:{cart_local_port}",
        str(max(1, count)),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=max(1.0, timeout),
        )
        return {
            "command": [str(value) for value in command],
            "return_code": completed.returncode,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "observations": parse_client_output(completed.stdout, completed.stderr),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": [str(value) for value in command],
            "return_code": 124,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "client timeout",
            "observations": parse_client_output(exc.stdout or "", exc.stderr or "client timeout"),
        }


def classify_workload(lifecycle: dict[str, Any], workload: dict[str, Any]) -> str:
    if lifecycle.get("injected_count", 0) < 1:
        return "invalid_not_injected"
    observations = workload.get("observations") or []
    if any(item.get("grpc_status") not in {"OK"} for item in observations):
        return "grpc_error_observed"
    if observations:
        return "grpc_response_observed"
    return "transport_or_observation_error"


def baseline_is_valid(workload: dict[str, Any]) -> bool:
    return any(
        item.get("grpc_status") == "OK"
        for item in (workload.get("observations") or [])
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mutation", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--client-script", type=Path, required=True)
    parser.add_argument("--checkout-service", default="checkoutservice")
    parser.add_argument("--checkout-remote-port", type=int, default=5050)
    parser.add_argument("--checkout-local-port", type=int, default=15050)
    parser.add_argument("--cart-service", default="cartservice")
    parser.add_argument("--cart-remote-port", type=int, default=7070)
    parser.add_argument("--cart-local-port", type=int, default=17070)
    parser.add_argument("--client-count", type=int, default=1)
    parser.add_argument("--client-timeout", type=float, default=30.0)
    parser.add_argument("--injection-timeout", type=float, default=45.0)
    parser.add_argument("--recovery-timeout", type=float, default=120.0)
    parser.add_argument("--poll-interval", type=float, default=0.5)
    parser.add_argument("--port-forward-timeout", type=float, default=15.0)
    args = parser.parse_args()

    report: dict[str, Any] = {
        "schema_version": 2,
        "tool": "run_grpc_chaos_experiment",
        "started_at": now(),
        "mutation": str(args.mutation).replace("\\", "/"),
        "client_script": str(args.client_script).replace("\\", "/"),
        # Phase-5 provenance: bind environment fingerprint; baseline lifecycle is
        # declared up front and must be populated by the runner (never assumed).
        "environment_fingerprint": load_fingerprint(),
        "request_config": {
            "checkout_service": args.checkout_service,
            "checkout_remote_port": args.checkout_remote_port,
            "checkout_local_port": args.checkout_local_port,
            "cart_service": args.cart_service,
            "cart_remote_port": args.cart_remote_port,
            "cart_local_port": args.cart_local_port,
            "client_count": max(1, args.client_count),
            "client_timeout_sec": args.client_timeout,
        },
        "preflight": None,
        "lifecycle": {"applied": False, "injected": False, "recovered": False, "cleanup": None},
        "baseline": None,
        "baseline_workload": None,
        "workload": None,
        "errors": [],
    }
    processes: list[subprocess.Popen[str] | None] = []
    applied = False
    kind = namespace = name = None
    try:
        preflight = check_mutation(args.mutation)
        report["preflight"] = preflight
        kind = preflight.get("kind")
        namespace = preflight.get("namespace")
        name = preflight.get("name")
        if preflight.get("decision") != "ready_for_injection":
            report["result_classification"] = str(
                "platform_or_preflight_blocked"
                if preflight.get("decision") == "blocked"
                else "not_applicable"
            )
        else:
            if not args.client_script.exists():
                raise FileNotFoundError(args.client_script)
            for service, local_port, remote_port in (
                (args.checkout_service, args.checkout_local_port, args.checkout_remote_port),
                (args.cart_service, args.cart_local_port, args.cart_remote_port),
            ):
                process = start_port_forward(namespace, service, local_port, remote_port)
                processes.append(process)
                wait_for_port("127.0.0.1", local_port, process, args.port_forward_timeout)
            report["baseline_workload"] = run_client(
                args.client_script,
                args.checkout_local_port,
                args.cart_local_port,
                args.client_count,
                args.client_timeout,
            )
            if not baseline_is_valid(report["baseline_workload"]):
                report["errors"].append("baseline produced no successful gRPC response")
                report["result_classification"] = "invalid_baseline"
            else:
                code, stdout, stderr = run_kubectl(["apply", "-f", str(args.mutation)])
                report["apply"] = {
                    "return_code": code,
                    "stdout": stdout.strip(),
                    "stderr": stderr.strip(),
                }
                if code != 0:
                    report["errors"].append("kubectl apply failed")
                    report["result_classification"] = "apply_failed"
                else:
                    applied = True
                    report["lifecycle"]["applied"] = True
                    injected, injected_status, errors = wait_for_lifecycle(
                        kind,
                        namespace,
                        name,
                        "injected",
                        args.injection_timeout,
                        args.poll_interval,
                    )
                    report["lifecycle"]["injected"] = injected
                    report["lifecycle"]["injected_status"] = injected_status
                    report["errors"].extend(errors)
                    report["workload"] = (
                        run_client(
                            args.client_script,
                            args.checkout_local_port,
                            args.cart_local_port,
                            args.client_count,
                            args.client_timeout,
                        )
                        if injected
                        else {"observations": []}
                    )
                    report["result_classification"] = classify_workload(
                        injected_status, report["workload"]
                    )
    except (OSError, RuntimeError, TimeoutError, ValueError, yaml.YAMLError) as exc:
        report["errors"].append(str(exc))
        report["result_classification"] = "runner_error"
    finally:
        report["port_forwards"] = [stop_process(process) for process in processes]
        if applied and kind and namespace and name:
            injected_confirmed = bool(report["lifecycle"].get("injected"))
            if injected_confirmed:
                if kind == "PodChaos":
                    recovered, recovered_status, errors = wait_for_target_ready(
                        namespace,
                        (report.get("preflight") or {}).get("selector") or {},
                        args.recovery_timeout,
                        args.poll_interval,
                    )
                    report["lifecycle"]["recovery_semantics"] = "target_selector_ready_after_podchaos"
                else:
                    recovered, recovered_status, errors = wait_for_lifecycle(
                        kind, namespace, name, "recovered", args.recovery_timeout, args.poll_interval
                    )
            else:
                recovered, recovered_status, errors = False, {}, []
            report["lifecycle"]["recovered"] = recovered
            report["lifecycle"]["recovered_status"] = recovered_status
            report["errors"].extend(errors)
            report["lifecycle"]["cleanup"] = delete_resource(kind, namespace, name)
            if report.get("result_classification") == "grpc_response_observed" and not recovered:
                report["result_classification"] = "grpc_response_without_recovery_confirmation"
    report["finished_at"] = now()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if report.get("result_classification") not in {
        "platform_or_preflight_blocked", "not_applicable", "invalid_baseline",
        "invalid_not_injected", "apply_failed", "runner_error"
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
