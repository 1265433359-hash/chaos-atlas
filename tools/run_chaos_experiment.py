"""Run one isolated Chaos Mesh mutation with an injection-aware lifecycle gate."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml

try:
    from runtime_applicability_gate import RESOURCE_BY_KIND, check_mutation
    from classify_runtime_result import classify as classify_runtime_result, exit_code_for_classification
except ImportError as exc:  # pragma: no cover
    raise SystemExit("run this script from the repository with tools/ on the import path") from exc


RESOURCE_KIND_TO_PLURAL = dict(RESOURCE_BY_KIND)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_kubectl(args: list[str], timeout: int = 30) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            ["kubectl", *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        return 124, str(stdout), f"kubectl timed out: {stderr}".strip()
    return completed.returncode, completed.stdout, completed.stderr


def kubectl_json(args: list[str]) -> tuple[dict[str, Any] | None, str | None]:
    code, stdout, stderr = run_kubectl([*args, "-o", "json"])
    if code != 0:
        return None, (stderr or stdout).strip()
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return None, f"invalid kubectl JSON: {exc}"
    if not isinstance(value, dict):
        return None, "kubectl JSON root is not an object"
    return value, None


def resource_name(kind: str) -> str:
    try:
        return RESOURCE_KIND_TO_PLURAL[kind]
    except KeyError as exc:
        raise ValueError(f"unsupported Chaos Mesh kind: {kind}") from exc


def lifecycle_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    status = data.get("status") or {}
    experiment = status.get("experiment") or {}
    records = experiment.get("containerRecords") or []
    injected = sum(int(record.get("injectedCount", 0) or 0) for record in records)
    recovered = sum(int(record.get("recoveredCount", 0) or 0) for record in records)
    conditions = {
        condition.get("type"): condition.get("status")
        for condition in status.get("conditions", [])
        if isinstance(condition, dict)
    }
    apply_events = [
        event.get("timestamp")
        for record in records
        for event in record.get("events", [])
        if event.get("operation") == "Apply"
    ]
    recover_events = [
        event.get("timestamp")
        for record in records
        for event in record.get("events", [])
        if event.get("operation") == "Recover"
    ]
    return {
        "selected": conditions.get("Selected") == "True",
        "all_injected": conditions.get("AllInjected") == "True",
        "all_recovered": conditions.get("AllRecovered") == "True",
        "injected_count": injected,
        "recovered_count": recovered,
        "records": records,
        "apply_timestamps": [value for value in apply_events if value],
        "recovery_timestamps": [value for value in recover_events if value],
        "desired_phase": experiment.get("desiredPhase"),
    }


def wait_for_lifecycle(
    kind: str,
    namespace: str,
    name: str,
    predicate: str,
    timeout: float,
    interval: float,
) -> tuple[bool, dict[str, Any], list[str]]:
    plural = resource_name(kind)
    deadline = time.monotonic() + max(0.1, timeout)
    errors: list[str] = []
    last: dict[str, Any] = {}
    while time.monotonic() <= deadline:
        data, error = kubectl_json(["get", plural, name, "-n", namespace])
        if data is None:
            if error and "not found" not in error.lower():
                errors.append(error)
            time.sleep(max(0.1, interval))
            continue
        last = lifecycle_snapshot(data)
        if predicate == "injected" and last["injected_count"] >= 1:
            return True, last, errors
        if predicate == "recovered" and last["injected_count"] >= 1 and (
            last["all_recovered"] or last["recovered_count"] >= last["injected_count"]
        ):
            return True, last, errors
        time.sleep(max(0.1, interval))
    return False, last, errors


def wait_for_target_ready(
    namespace: str,
    selector: dict[str, Any],
    timeout: float,
    interval: float,
) -> tuple[bool, dict[str, Any], list[str]]:
    """Wait for a replacement Pod to become Ready after a one-shot kill."""
    labels = selector.get("labelSelectors") if isinstance(selector, dict) else {}
    labels = labels if isinstance(labels, dict) else {}
    label_query = ",".join(f"{key}={value}" for key, value in sorted(labels.items()))
    deadline = time.monotonic() + max(0.1, timeout)
    errors: list[str] = []
    last: dict[str, Any] = {}
    while time.monotonic() <= deadline:
        args = ["get", "pods", "-n", namespace]
        if label_query:
            args.extend(["-l", label_query])
        data, error = kubectl_json(args)
        if data is None:
            if error:
                errors.append(error)
            time.sleep(max(0.1, interval))
            continue
        items = data.get("items") if isinstance(data, dict) else []
        ready_names = [
            str(item.get("metadata", {}).get("name"))
            for item in items
            if any(
                condition.get("type") == "Ready" and condition.get("status") == "True"
                for condition in item.get("status", {}).get("conditions", [])
                if isinstance(condition, dict)
            )
        ]
        last = {
            "selector": label_query,
            "pod_count": len(items),
            "ready_pods": ready_names,
        }
        if ready_names:
            return True, last, errors
        time.sleep(max(0.1, interval))
    return False, last, errors


def delete_resource(kind: str, namespace: str, name: str, timeout: int = 30) -> dict[str, Any]:
    plural = resource_name(kind)
    code, stdout, stderr = run_kubectl(
        ["delete", plural, name, "-n", namespace, "--ignore-not-found=true"], timeout=timeout
    )
    verify_code, _, verify_error = run_kubectl(["get", plural, name, "-n", namespace], timeout=timeout)
    return {
        "delete_command_ok": code == 0,
        "delete_output": (stdout or stderr).strip(),
        "resource_absent_after_delete": verify_code != 0,
        "verify_error": verify_error.strip() if verify_error else None,
    }


def wait_for_port(host: str, port: int, process: subprocess.Popen[str], timeout: float) -> None:
    deadline = time.monotonic() + max(0.1, timeout)
    last_error = ""
    while time.monotonic() <= deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise RuntimeError(
                f"port-forward exited with code {process.returncode}: {(stderr or stdout).strip()}"
            )
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError as exc:
            last_error = str(exc)
            time.sleep(0.2)
    raise TimeoutError(f"port-forward did not open {host}:{port}: {last_error}")


def start_port_forward(namespace: str, service: str, local_port: int, remote_port: int) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [
            "kubectl",
            "port-forward",
            "-n",
            namespace,
            f"svc/{service}",
            f"{local_port}:{remote_port}",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def stop_process(process: subprocess.Popen[str] | None) -> dict[str, Any] | None:
    if process is None:
        return None
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    stdout, stderr = process.communicate()
    return {
        "return_code": process.returncode,
        "stopped_by_runner": True,
        "stdout": (stdout or "").strip(),
        "stderr": (stderr or "").strip(),
    }


def http_request(
    local_port: int,
    path: str,
    method: str,
    timeout: float,
    body: str | None,
    max_body_bytes: int,
) -> dict[str, Any]:
    if not path.startswith("/"):
        path = f"/{path}"
    request_body = body.encode("utf-8") if body is not None else None
    request = Request(
        f"http://127.0.0.1:{local_port}{path}",
        data=request_body,
        method=method.upper(),
        headers={"Content-Type": "application/json"} if request_body else {},
    )
    started = time.monotonic()
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read(max_body_bytes)
            elapsed = round((time.monotonic() - started) * 1000, 3)
            return {
                "status_code": response.status,
                "latency_ms": elapsed,
                "body": payload.decode("utf-8", errors="replace"),
                "error": None,
            }
    except HTTPError as exc:
        elapsed = round((time.monotonic() - started) * 1000, 3)
        payload = exc.read(max_body_bytes)
        return {
            "status_code": exc.code,
            "latency_ms": elapsed,
            "body": payload.decode("utf-8", errors="replace"),
            "error": str(exc),
        }
    except (TimeoutError, URLError, OSError) as exc:
        elapsed = round((time.monotonic() - started) * 1000, 3)
        reason = getattr(exc, "reason", None)
        return {
            "status_code": None,
            "latency_ms": elapsed,
            "body": None,
            "error": str(reason or exc),
        }


def classify(preflight: dict[str, Any], lifecycle: dict[str, Any], requests: list[dict[str, Any]], recovered: bool) -> str:
    """Compatibility wrapper around the single project classifier."""
    normalized_lifecycle = {
        "injected": lifecycle.get("injected_count", 0) >= 1,
        "injected_status": lifecycle,
        "recovered": recovered,
    }
    return classify_runtime_result(
        {"preflight": preflight, "lifecycle": normalized_lifecycle, "requests": requests},
        None,
    )["classification"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mutation", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--service", help="Kubernetes Service to port-forward for an HTTP request")
    parser.add_argument("--remote-port", type=int, help="Service port used by the HTTP request")
    parser.add_argument("--local-port", type=int, default=18080)
    parser.add_argument("--request-path")
    parser.add_argument("--method", default="GET")
    parser.add_argument("--body")
    parser.add_argument("--request-timeout", type=float, default=5.0)
    parser.add_argument("--request-count", type=int, default=1)
    parser.add_argument("--request-concurrency", type=int, default=1)
    parser.add_argument("--request-interval", type=float, default=0.0)
    parser.add_argument("--warmup-count", type=int, default=0)
    parser.add_argument("--warmup-interval", type=float, default=0.0)
    parser.add_argument("--injection-timeout", type=float, default=30.0)
    parser.add_argument("--recovery-timeout", type=float, default=120.0)
    parser.add_argument("--poll-interval", type=float, default=0.5)
    parser.add_argument("--port-forward-timeout", type=float, default=15.0)
    parser.add_argument("--max-body-bytes", type=int, default=65536)
    args = parser.parse_args()

    report: dict[str, Any] = {
        "schema_version": 1,
        "tool": "run_chaos_experiment",
        "started_at": now(),
        "mutation": str(args.mutation).replace("\\", "/"),
        "request_config": {
            "service": args.service,
            "remote_port": args.remote_port,
            "local_port": args.local_port,
            "path": args.request_path,
            "method": args.method.upper(),
            "request_timeout_sec": args.request_timeout,
            "request_count": max(0, args.request_count),
            "request_concurrency": max(1, args.request_concurrency),
            "warmup_count": max(0, args.warmup_count),
            "warmup_interval_sec": args.warmup_interval,
        },
        "preflight": None,
        "lifecycle": {"applied": False, "injected": False, "recovered": False, "cleanup": None},
        "requests": [],
        "warmup_requests": [],
        "errors": [],
    }
    process: subprocess.Popen[str] | None = None
    applied = False
    kind = None
    namespace = None
    name = None
    forced_classification: str | None = None
    try:
        preflight = check_mutation(args.mutation)
        report["preflight"] = preflight
        kind = preflight.get("kind")
        namespace = preflight.get("namespace")
        name = preflight.get("name")
        if preflight.get("decision") != "ready_for_injection":
            # Leave classification to the shared classifier so runner and
            # offline report classification cannot drift.
            forced_classification = None
        elif args.request_path and (not args.service or args.remote_port is None):
            report["errors"].append("--request-path requires --service and --remote-port")
            forced_classification = "invalid_request_configuration"
        else:
            code, stdout, stderr = run_kubectl(["apply", "-f", str(args.mutation)])
            report["apply"] = {"return_code": code, "stdout": stdout.strip(), "stderr": stderr.strip()}
            if code != 0:
                report["errors"].append("kubectl apply failed")
                forced_classification = "apply_failed"
            else:
                applied = True
                report["lifecycle"]["applied"] = True
                injected, injected_status, errors = wait_for_lifecycle(
                    kind, namespace, name, "injected", args.injection_timeout, args.poll_interval
                )
                report["lifecycle"]["injected"] = injected
                report["lifecycle"]["injected_status"] = injected_status
                report["errors"].extend(errors)
                if args.request_path and injected:
                    process = start_port_forward(namespace, args.service, args.local_port, args.remote_port)
                    wait_for_port("127.0.0.1", args.local_port, process, args.port_forward_timeout)
                    for index in range(max(0, args.warmup_count)):
                        report["warmup_requests"].append(
                            {
                                "sample": index + 1,
                                "observed_at": now(),
                                **http_request(
                                    args.local_port,
                                    args.request_path,
                                    args.method,
                                    args.request_timeout,
                                    args.body,
                                    args.max_body_bytes,
                                ),
                            }
                        )
                        if index + 1 < max(0, args.warmup_count):
                            time.sleep(max(0.0, args.warmup_interval))
                    def formal_request(index: int) -> dict[str, Any]:
                        return {
                            "sample": index + 1,
                            "observed_at": now(),
                            **http_request(
                                args.local_port,
                                args.request_path,
                                args.method,
                                args.request_timeout,
                                args.body,
                                args.max_body_bytes,
                            ),
                        }

                    request_count = max(0, args.request_count)
                    concurrency = max(1, args.request_concurrency)
                    for batch_start in range(0, request_count, concurrency):
                        batch_indices = range(batch_start, min(batch_start + concurrency, request_count))
                        with ThreadPoolExecutor(max_workers=concurrency) as executor:
                            batch = list(executor.map(formal_request, batch_indices))
                        report["requests"].extend(batch)
                        if batch_start + len(batch) < request_count:
                            time.sleep(max(0.0, args.request_interval))
    except (OSError, RuntimeError, TimeoutError, ValueError, yaml.YAMLError) as exc:
        report["errors"].append(str(exc))
        forced_classification = "runner_error"
    finally:
        report["port_forward"] = stop_process(process)
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
                # There is no effect to wait for when injection was never
                # confirmed. Delete immediately and avoid a needless 120s
                # recovery window while still guaranteeing cleanup.
                recovered, recovered_status, errors = False, {}, []
            report["lifecycle"]["recovered"] = recovered
            report["lifecycle"]["recovered_status"] = recovered_status
            report["errors"].extend(errors)
            cleanup = delete_resource(kind, namespace, name)
            report["lifecycle"]["cleanup"] = cleanup
            report["lifecycle"]["recovery_wait_completed"] = bool(injected_confirmed and recovered)

    classification_details = classify_runtime_result(report, None)
    report["classification_details"] = classification_details
    report["result_classification"] = forced_classification or classification_details["classification"]
    report["classification_source"] = "runner_forced" if forced_classification else "shared_classifier"
    if forced_classification and classification_details["classification"] != forced_classification:
        # Keep the shared classifier's label as the evidence-derived view, but
        # record the forced outcome explicitly so the two never look like a
        # contradiction in the same report.
        classification_details["classification_note"] = (
            f"overridden by runner control outcome {forced_classification!r}; "
            f"classifier-derived label was {classification_details['classification']!r}"
        )
        classification_details["classification"] = forced_classification
    report["defense_conclusion"] = {
        "allowed": bool(report["lifecycle"].get("injected")) and bool(report["requests"]),
        "rule": "The runner records effect evidence; defense interpretation still requires baseline, path evidence and outcome-specific analysis.",
    }
    report["finished_at"] = now()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return exit_code_for_classification(str(report.get("result_classification")))


if __name__ == "__main__":
    raise SystemExit(main())
