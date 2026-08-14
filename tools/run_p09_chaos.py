"""Run one namespace-local P09 Chaos Mesh mutation with the P02 lifecycle."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# Support both ``python -m tools.run_p09_chaos`` and direct script execution.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.p09_execution_gate import check as execution_gate_check
from tools.run_p09_podchaos import (
    capture_diagnostics,
    collect_oracle,
    namespace_health,
    residual_chaos,
    wait_namespace_stable,
    wait_replacement,
)
from tools.unified_experiment_protocol import comparison_eligibility, validate_lifecycle_report


NAMESPACE = "chaosatlas-p09"
RESOURCE_BY_KIND = {"PodChaos": "podchaos", "NetworkChaos": "networkchaos", "StressChaos": "stresschaos"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def kubectl(args: list[str], timeout: int = 30, input_text: str | None = None) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            ["kubectl", *args], input=input_text, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        return completed.returncode, completed.stdout or "", completed.stderr or ""
    except subprocess.TimeoutExpired as exc:
        return 124, "", str(exc)


def kubectl_json(args: list[str]) -> tuple[dict[str, Any] | None, str | None]:
    code, out, err = kubectl([*args, "-o", "json"])
    if code != 0:
        return None, (err or out).strip()
    try:
        value = json.loads(out)
    except json.JSONDecodeError as exc:
        return None, str(exc)
    return value if isinstance(value, dict) else None, None


def validate_mutation(document: dict[str, Any]) -> tuple[str, dict[str, str]]:
    kind = document.get("kind")
    metadata = document.get("metadata") or {}
    spec = document.get("spec") or {}
    selector = spec.get("selector") or {}
    labels = selector.get("labelSelectors") or {}
    if kind not in RESOURCE_BY_KIND or metadata.get("namespace") != NAMESPACE:
        raise ValueError("runner accepts only supported Chaos in chaosatlas-p09")
    if spec.get("mode") != "one":
        raise ValueError("runner accepts only mode=one")
    if selector.get("namespaces") != [NAMESPACE] or not isinstance(labels, dict) or not labels:
        raise ValueError("selector must be non-empty and limited to chaosatlas-p09")
    name = str(metadata.get("name") or "")
    if not name:
        raise ValueError("mutation name is required")
    return name, {str(key): str(value) for key, value in labels.items()}


def lifecycle_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    status = data.get("status") or {}
    experiment = status.get("experiment") or {}
    records = experiment.get("containerRecords") or []
    conditions = {
        condition.get("type"): condition.get("status")
        for condition in status.get("conditions", []) if isinstance(condition, dict)
    }
    return {
        "selected": conditions.get("Selected") == "True",
        "all_injected": conditions.get("AllInjected") == "True",
        "all_recovered": conditions.get("AllRecovered") == "True",
        "injected_count": sum(int(item.get("injectedCount", 0) or 0) for item in records),
        "recovered_count": sum(int(item.get("recoveredCount", 0) or 0) for item in records),
        "conditions": status.get("conditions", []),
    }


def wait_lifecycle(kind: str, name: str, predicate: str, timeout: float = 60) -> dict[str, Any]:
    resource = RESOURCE_BY_KIND[kind]
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        data, error = kubectl_json(["get", resource, name, "-n", NAMESPACE])
        if data is not None:
            last = lifecycle_snapshot(data)
            if predicate == "injected" and last["injected_count"] >= 1:
                return last
            if predicate == "recovered" and (last["all_recovered"] or last["recovered_count"] >= last["injected_count"] > 0):
                return last
        elif error and "not found" not in error.lower():
            last = {"error": error}
        time.sleep(0.5)
    return last


def cleanup(kind: str, name: str) -> dict[str, Any]:
    resource = RESOURCE_BY_KIND[kind]
    code, out, err = kubectl(["delete", resource, name, "-n", NAMESPACE, "--ignore-not-found=true"])
    verify_code, verify_out, verify_err = kubectl(["get", resource, name, "-n", NAMESPACE])
    verify_text = (verify_out or verify_err).lower()
    absent = verify_code != 0 and "not found" in verify_text and "forbidden" not in verify_text
    return {
        "delete_code": code,
        "delete_output": (out or err).strip(),
        "verify_code": verify_code,
        "verify_output": (verify_out or verify_err).strip(),
        "absent_confirmed": absent,
        "residual_resources": [],
    }


def recover_podchaos(
    before_uids: set[str], labels: dict[str, str], timeout: float
) -> tuple[bool, dict[str, Any]]:
    return wait_replacement(before_uids, labels, timeout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mutation", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--profile-gate", type=Path, required=True)
    parser.add_argument("--expected-context", default="minikube")
    parser.add_argument("--baseline-successes", type=int, default=10)
    parser.add_argument("--washout-stable-successes", type=int, default=10)
    parser.add_argument("--washout-timeout", type=float, default=180)
    parser.add_argument("--recovery-timeout", type=float, default=180)
    parser.add_argument("--arm", default="P09-unified")
    parser.add_argument("--mutation-id", required=True)
    parser.add_argument("--replicate", type=int, required=True)
    parser.add_argument("--capture-diagnostics", action="store_true")
    args = parser.parse_args()
    if args.report.exists():
        raise SystemExit(f"refusing to overwrite existing report: {args.report}")

    report: dict[str, Any] = {
        "schema_version": "unified-lifecycle-v1", "tool": "run_p09_chaos", "project_id": "P09",
        "started_at": now(), "namespace": NAMESPACE, "arm": args.arm, "mutation_id": args.mutation_id,
        "replicate": args.replicate, "mutation": {"path": str(args.mutation).replace("\\", "/"), "sha256": None},
        "status": "running", "baseline": {"pass": False, "samples": []},
        "injection": {"applied": False, "injected": False}, "observation": {"samples": []},
        "recovery": {"recovered": False}, "cleanup": {"absent_confirmed": False, "residual_resources": []},
        "washout": {"stable": False, "samples": []}, "diagnostics": {"status": "not_configured"},
        "errors": [], "human_review": "pending",
    }
    kind = name = ""
    applied = False
    try:
        raw = args.mutation.read_bytes()
        report["mutation"]["sha256"] = hashlib.sha256(raw).hexdigest()
        document = yaml.safe_load(raw.decode("utf-8"))
        name, labels = validate_mutation(document)
        kind = document["kind"]
        report["execution_gate"] = execution_gate_check(args.mutation, profile_gate=args.profile_gate)
        if report["execution_gate"].get("decision") != "ready_for_injection":
            raise RuntimeError("P09 execution gate blocked: " + "; ".join(report["execution_gate"].get("errors", [])))
        code, context, err = kubectl(["config", "current-context"])
        if code != 0 or context.strip() != args.expected_context:
            raise RuntimeError(f"unexpected kubectl context: {(err or context).strip()}")
        if residual_chaos():
            raise RuntimeError("pre-existing P09 Chaos resources")
        report["preflight_health"] = wait_namespace_stable(60)
        samples, baseline_ok = collect_oracle(args.baseline_successes, 120)
        report["baseline"] = {"pass": baseline_ok, "samples": samples, "successes_required": args.baseline_successes, "stable": baseline_ok}
        if not baseline_ok:
            raise RuntimeError("P09 API baseline did not become stable")
        target_pods, target_error = kubectl_json(
            ["get", "pods", "-n", NAMESPACE, "-l", ",".join(f"{key}={value}" for key, value in sorted(labels.items()))]
        )
        if target_error:
            raise RuntimeError(f"target pod lookup failed: {target_error}")
        target_items = (target_pods or {}).get("items", [])
        before_uids = {
            str(item.get("metadata", {}).get("uid"))
            for item in target_items
            if item.get("metadata", {}).get("uid")
        }
        if not before_uids:
            raise RuntimeError("target selector matched no Pods before injection")
        report["target_before"] = [
            {
                "name": item.get("metadata", {}).get("name"),
                "uid": item.get("metadata", {}).get("uid"),
                "ready": any(
                    condition.get("type") == "Ready" and condition.get("status") == "True"
                    for condition in item.get("status", {}).get("conditions", [])
                    if isinstance(condition, dict)
                ),
            }
            for item in target_items
        ]
        report["target_labels"] = labels
        code, out, err = kubectl(["apply", "-f", "-"], input_text=raw.decode("utf-8"))
        report["injection"]["apply"] = {"return_code": code, "output": (out or err).strip()}
        if code != 0:
            raise RuntimeError("kubectl apply failed")
        applied = True
        report["injection"]["applied"] = True
        status = wait_lifecycle(kind, name, "injected")
        report["injection"]["status"] = status
        report["injection"]["injected"] = status.get("injected_count", 0) >= 1
        if not report["injection"]["injected"]:
            raise RuntimeError("Chaos injection was not confirmed")
        observed, _ = collect_oracle(1, 45)
        report["observation"] = {"samples": observed, "oracle": "P09 API /health during or immediately after confirmed injection"}
    except Exception as exc:
        report["errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        if applied:
            try:
                if kind == "PodChaos":
                    recovered_chaos, recovered_status = recover_podchaos(
                        before_uids, labels, args.recovery_timeout
                    )
                else:
                    recovered_status = wait_lifecycle(kind, name, "recovered", args.recovery_timeout)
                    recovered_chaos = (
                        recovered_status.get("all_recovered") is True
                        or recovered_status.get("recovered_count", 0) >= recovered_status.get("injected_count", 0) > 0
                    )
                recovered_health = wait_namespace_stable(args.recovery_timeout)
                report["recovery"] = {
                    "recovered": recovered_chaos and recovered_health["healthy"],
                    "chaos_status": recovered_status,
                    "health": recovered_health,
                }
                if not report["recovery"]["recovered"]:
                    report["errors"].append("P09 Chaos or namespace did not recover")
            except Exception as exc:
                report["errors"].append(f"recovery verification failed: {type(exc).__name__}: {exc}")
            report["cleanup"] = cleanup(kind, name)
            if not report["cleanup"]["absent_confirmed"]:
                report["errors"].append("cleanup absence was not confirmed")
            try:
                samples, stable = collect_oracle(args.washout_stable_successes, args.washout_timeout)
                report["washout"] = {"samples": samples, "successes_required": args.washout_stable_successes, "stable": stable}
                if not stable:
                    report["errors"].append("P09 API washout did not regain stable HTTP 200")
            except Exception as exc:
                report["errors"].append(f"washout verification failed: {type(exc).__name__}: {exc}")
        try:
            residual = residual_chaos()
            report["post_cleanup_residual_chaos"] = residual
            report["cleanup"]["residual_resources"] = residual
            if residual:
                report["errors"].append("P09 Chaos resources remain after cleanup")
        except Exception as exc:
            report["errors"].append(f"residual check failed: {exc}")
        if args.capture_diagnostics:
            try:
                report["diagnostics"] = capture_diagnostics(args.report, report["started_at"])
            except Exception as exc:
                report["diagnostics"] = {"status": "unavailable", "error": str(exc), "captured_at": now()}
                report["errors"].append(f"diagnostics unavailable: {exc}")

    report["mutation_sha256"] = report["mutation"]["sha256"]
    report["finished_at"] = now()
    validation = validate_lifecycle_report(report)
    eligibility = comparison_eligibility(report)
    report["protocol_validation"] = validation
    report["comparison_eligibility"] = eligibility
    report["status"] = "completed" if not report["errors"] and validation["valid"] and eligibility["eligible"] else "failed"
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if report["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
