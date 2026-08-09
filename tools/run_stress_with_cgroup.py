"""Replay a StressChaos mutation and start cgroup sampling only after injection."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
RESOURCE_BY_KIND = {
    "StressChaos": "stresschaos",
    "NetworkChaos": "networkchaos",
    "PodChaos": "podchaos",
    "IOChaos": "iochaos",
    "TimeChaos": "timechaos",
    "HTTPChaos": "httpchaos",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_kubectl(args: list[str], timeout: int = 20) -> tuple[int, str, str]:
    completed = subprocess.run(
        ["kubectl", *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return completed.returncode, completed.stdout, completed.stderr


def lifecycle_status(namespace: str, name: str) -> dict[str, Any] | None:
    code, stdout, _ = run_kubectl(["get", "stresschaos", name, "-n", namespace, "-o", "json"])
    if code != 0:
        return None
    data = json.loads(stdout)
    status = data.get("status") or {}
    experiment = status.get("experiment") or {}
    records = experiment.get("containerRecords") or []
    injected = sum(int(record.get("injectedCount", 0) or 0) for record in records)
    recovered = sum(int(record.get("recoveredCount", 0) or 0) for record in records)
    return {
        "injected_count": injected,
        "recovered_count": recovered,
        "all_recovered": any(
            condition.get("type") == "AllRecovered" and condition.get("status") == "True"
            for condition in status.get("conditions", [])
        ),
        "records": records,
    }


def wait_process(process: subprocess.Popen[Any] | None, timeout: float) -> tuple[int | None, bool]:
    if process is None:
        return None, False
    try:
        return process.wait(timeout=max(0.1, timeout)), False
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            return process.wait(timeout=5), True
        except subprocess.TimeoutExpired:
            process.kill()
            return process.wait(timeout=5), True


def selector_string(labels: dict[str, Any]) -> str:
    return ",".join(f"{key}={value}" for key, value in sorted(labels.items()))


def mutation_target(document: dict[str, Any]) -> tuple[str, str, str]:
    metadata = document.get("metadata") or {}
    spec = document.get("spec") or {}
    selector = spec.get("selector") or {}
    namespace = metadata.get("namespace")
    labels = selector.get("labelSelectors") or {}
    namespaces = selector.get("namespaces") or [namespace]
    if not namespace or not isinstance(labels, dict) or not labels:
        raise ValueError("mutation must define metadata.namespace and selector.labelSelectors")
    if namespaces != [namespace]:
        raise ValueError("cgroup sampling requires exactly the mutation selector namespace")
    rendered = selector_string(labels)
    if not rendered:
        raise ValueError("mutation selector cannot be empty")
    return str(namespace), rendered, str(document.get("kind") or "")


def cleanup_mutation(kind: str, namespace: str, name: str) -> dict[str, Any]:
    plural = RESOURCE_BY_KIND.get(kind)
    if not plural:
        return {"attempted": False, "confirmed": False, "error": f"unsupported kind: {kind}"}
    try:
        delete = run_kubectl(["delete", plural, name, "-n", namespace, "--ignore-not-found=true"], timeout=30)
        verify = run_kubectl(["get", plural, name, "-n", namespace], timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"attempted": True, "confirmed": False, "error": str(exc)}
    # Phase-1 remediation (findings #1): absence is confirmed ONLY on an explicit
    # NotFound. A timeout (124) or RBAC/API error means the resource state is
    # unknown -> confirmed stays False so callers retry / fail loudly.
    verify_code, _, verify_error = verify
    if verify_code == 0:
        verify_status = "exists"
    elif verify_code == 124:
        verify_status = "timeout"
    elif _kubectl_not_found(verify_error):
        verify_status = "absent"
    else:
        verify_status = "error"
    absent = verify_status == "absent"
    return {
        "attempted": True,
        "delete_return_code": delete[0],
        "delete_output": (delete[1] or delete[2]).strip(),
        "resource_absent_after_delete": absent,
        "verify_status": verify_status,
        "verify_error": (verify[2] or verify[1]).strip(),
        "confirmed": delete[0] == 0 and absent,
    }


def _kubectl_not_found(error: str | None) -> bool:
    if not error:
        return False
    lowered = error.lower()
    return "not found" in lowered and "forbidden" not in lowered and "timed out" not in lowered


def resource_exists(kind: str, namespace: str, name: str) -> bool:
    """Return True only when the resource exists; return False for NotFound.

    Any non-zero `kubectl get` result other than an explicit NotFound (RBAC
    Forbidden, API-server timeout, ...) raises so callers do not mistake a
    failed lookup for a confirmed-absent resource and skip cleanup.
    """
    plural = RESOURCE_BY_KIND.get(kind)
    if not plural:
        return False
    code, stdout, stderr = run_kubectl(["get", plural, name, "-n", namespace], timeout=30)
    if code == 0:
        return True
    combined = (stdout or "") + "\n" + (stderr or "")
    if "not found" in combined.lower():
        return False
    raise RuntimeError(
        f"cannot determine existence of {kind}/{namespace}/{name}: "
        f"kubectl exit {code}: {(stderr or stdout).strip()}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mutation", type=Path)
    parser.add_argument("--namespace", default="train-ticket-lab")
    parser.add_argument("--service", required=True)
    parser.add_argument("--remote-port", type=int, required=True)
    parser.add_argument("--local-port", type=int, default=18082)
    parser.add_argument("--request-path", required=True)
    parser.add_argument("--runner-report", type=Path, required=True)
    parser.add_argument("--cgroup-report", type=Path, required=True)
    parser.add_argument("--orchestration-report", type=Path, required=True)
    parser.add_argument("--request-count", type=int, default=8)
    parser.add_argument("--request-concurrency", type=int, default=1)
    parser.add_argument("--request-timeout", type=float, default=5.0)
    parser.add_argument("--request-interval", type=float, default=0.5)
    parser.add_argument("--warmup-count", type=int, default=0)
    parser.add_argument("--warmup-interval", type=float, default=0.5)
    parser.add_argument("--injection-timeout", type=float, default=30.0)
    parser.add_argument("--recovery-timeout", type=float, default=120.0)
    parser.add_argument("--cgroup-samples", type=int, default=25)
    parser.add_argument("--cgroup-interval", type=float, default=2.0)
    parser.add_argument("--process-timeout", type=float, default=240.0)
    args = parser.parse_args()

    mutation = str(args.mutation).replace("\\", "/")
    try:
        mutation_doc = yaml.safe_load(args.mutation.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        print(json.dumps({"tool": "run_stress_with_cgroup", "error": f"mutation YAML is not parseable: {exc}", "mutation": mutation}))
        return 2
    mutation_name = ((mutation_doc.get("metadata") or {}).get("name") if isinstance(mutation_doc, dict) else None)
    if not mutation_name:
        raise SystemExit("mutation metadata.name is required")
    if not isinstance(mutation_doc, dict):
        raise SystemExit("mutation YAML root must be a mapping")
    mutation_namespace, target_selector, mutation_kind = mutation_target(mutation_doc)
    if mutation_namespace != args.namespace:
        raise SystemExit(f"--namespace {args.namespace} does not match mutation namespace {mutation_namespace}")
    if resource_exists(mutation_kind, mutation_namespace, str(mutation_name)):
        raise SystemExit(f"mutation already exists: {mutation_namespace}/{mutation_name}")
    process_budget = max(
        args.process_timeout,
        args.injection_timeout
        + args.recovery_timeout
        + max(args.request_timeout, 0.1) * max(1, args.request_count)
        + max(0.0, args.request_interval) * max(0, args.request_count - 1)
        + 30.0,
    )
    runner_stdout = args.runner_report.with_suffix(".stdout.log")
    runner_stderr = args.runner_report.with_suffix(".stderr.log")
    cgroup_stdout = args.cgroup_report.with_suffix(".stdout.log")
    cgroup_stderr = args.cgroup_report.with_suffix(".stderr.log")
    runner_args = [
        sys.executable,
        str(ROOT / "tools/run_chaos_experiment.py"),
        mutation,
        "--report",
        str(args.runner_report),
        "--service",
        args.service,
        "--remote-port",
        str(args.remote_port),
        "--local-port",
        str(args.local_port),
        "--request-path",
        args.request_path,
        "--request-count",
        str(args.request_count),
        "--request-concurrency",
        str(args.request_concurrency),
        "--request-timeout",
        str(args.request_timeout),
        "--request-interval",
        str(args.request_interval),
        "--warmup-count",
        str(args.warmup_count),
        "--warmup-interval",
        str(args.warmup_interval),
        "--injection-timeout",
        str(args.injection_timeout),
        "--recovery-timeout",
        str(args.recovery_timeout),
    ]
    runner_stdout.parent.mkdir(parents=True, exist_ok=True)
    runner_out = runner_stdout.open("w", encoding="utf-8")
    runner_err = runner_stderr.open("w", encoding="utf-8")
    runner = subprocess.Popen(runner_args, stdout=runner_out, stderr=runner_err, text=True)
    injected_status: dict[str, Any] | None = None
    cgroup: subprocess.Popen[Any] | None = None
    cgroup_out = None
    cgroup_err = None
    errors: list[str] = []
    runner_exit: int | None = None
    cgroup_exit: int | None = None
    runner_timed_out = False
    cgroup_timed_out = False
    cleanup_fallback: dict[str, Any] | None = None
    try:
        deadline = time.monotonic() + max(1.0, args.injection_timeout)
        while time.monotonic() < deadline:
            injected_status = lifecycle_status(args.namespace, mutation_name)
            if injected_status and injected_status.get("injected_count", 0) >= 1:
                break
            if runner.poll() is not None:
                errors.append(f"runner exited before injection: {runner.returncode}")
                break
            time.sleep(0.5)
        if not injected_status or injected_status.get("injected_count", 0) < 1:
            errors.append("injectedCount did not reach 1 before cgroup sampling")
        else:
            cgroup_args = [
                sys.executable,
                str(ROOT / "tools/capture_cgroup_cpu.py"),
                "--namespace",
                mutation_namespace,
                "--selector",
                target_selector,
                "--samples",
                str(args.cgroup_samples),
                "--interval",
                str(args.cgroup_interval),
                "--phase",
                "generated_stress_candidate",
                "--report",
                str(args.cgroup_report),
            ]
            cgroup_stdout.parent.mkdir(parents=True, exist_ok=True)
            cgroup_out = cgroup_stdout.open("w", encoding="utf-8")
            cgroup_err = cgroup_stderr.open("w", encoding="utf-8")
            cgroup = subprocess.Popen(cgroup_args, stdout=cgroup_out, stderr=cgroup_err, text=True)
        runner_exit, runner_timed_out = wait_process(runner, process_budget)
        cgroup_exit, cgroup_timed_out = wait_process(cgroup, process_budget) if cgroup else (None, False)
    finally:
        if cgroup and cgroup.poll() is None:
            cgroup.terminate()
            try:
                cgroup.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cgroup.kill()
                cgroup.wait(timeout=5)
        if runner.poll() is None:
            runner.terminate()
            try:
                runner.wait(timeout=5)
            except subprocess.TimeoutExpired:
                runner.kill()
                runner.wait(timeout=5)
        # The parent owns a final, idempotent cleanup attempt. This covers a
        # runner killed during its recovery/finally block.
        try:
            resource_present = resource_exists(mutation_kind, mutation_namespace, str(mutation_name))
        except RuntimeError as exc:
            # Cannot determine existence (e.g. RBAC or API timeout). Attempt
            # cleanup anyway so a transient lookup failure cannot orphan the
            # mutation resource.
            errors.append(f"parent cleanup existence check failed: {exc}")
            resource_present = True
        if resource_present:
            cleanup_fallback = cleanup_mutation(mutation_kind, mutation_namespace, str(mutation_name))
        else:
            cleanup_fallback = {
                "attempted": False,
                "confirmed": True,
                "reason": "mutation resource is already absent; no parent delete required",
            }
        if not cleanup_fallback.get("confirmed"):
            errors.append("parent cleanup did not confirm mutation absence")
        runner_out.close()
        runner_err.close()
        if cgroup_out:
            cgroup_out.close()
        if cgroup_err:
            cgroup_err.close()

    report = {
        "schema_version": 1,
        "tool": "run_stress_with_cgroup",
        "started_at": now(),
        "mutation": mutation,
        "runner_report": str(args.runner_report).replace("\\", "/"),
        "cgroup_report": str(args.cgroup_report).replace("\\", "/"),
        "injected_status_before_sampling": injected_status,
        "runner_exit": runner_exit,
        "cgroup_exit": cgroup_exit,
        "errors": errors,
        "safety": {
            "cgroup_started_only_after_injected": bool(injected_status and injected_status.get("injected_count", 0) >= 1),
            "runner_owns_recovery_and_cleanup": False,
            "parent_cleanup_fallback": cleanup_fallback,
            "runner_timed_out": runner_timed_out,
            "cgroup_timed_out": cgroup_timed_out,
            "process_timeout_budget_sec": process_budget,
            "sample_selector": target_selector,
        },
        "finished_at": now(),
    }
    args.orchestration_report.parent.mkdir(parents=True, exist_ok=True)
    args.orchestration_report.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if not errors and runner_exit == 0 and cgroup_exit == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
