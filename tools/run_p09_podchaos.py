"""Run one bounded P09 API PodChaos pilot in chaosatlas-p09 only."""

from __future__ import annotations

import argparse
import hashlib
import json
import socket
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


NAMESPACE = "chaosatlas-p09"
SERVICE = "api"
REMOTE_PORT = 5001
LOCAL_PORT = 15092
ORACLE_PATH = "/health"
CHAOS_RESOURCES = "podchaos,networkchaos,stresschaos"
API_SELECTOR = {
    "app.kubernetes.io/name": "api",
    "app.kubernetes.io/part-of": NAMESPACE,
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def kubectl(
    args: list[str], timeout: int = 30, input_text: str | None = None
) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            ["kubectl", *args],
            input=input_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return completed.returncode, completed.stdout or "", completed.stderr or ""
    except subprocess.TimeoutExpired as exc:
        return 124, "", str(exc)


def kubectl_json(args: list[str], timeout: int = 30) -> tuple[dict[str, Any] | None, str | None]:
    code, out, err = kubectl([*args, "-o", "json"], timeout)
    if code != 0:
        return None, (err or out).strip()
    try:
        value = json.loads(out)
    except json.JSONDecodeError as exc:
        return None, str(exc)
    return (value, None) if isinstance(value, dict) else (None, "kubectl JSON root is not an object")


def validate_mutation(document: dict[str, Any]) -> tuple[str, dict[str, str]]:
    metadata = document.get("metadata", {})
    spec = document.get("spec", {})
    selector = spec.get("selector", {})
    if document.get("kind") != "PodChaos" or metadata.get("namespace") != NAMESPACE:
        raise ValueError("runner accepts only PodChaos in chaosatlas-p09")
    if spec.get("action") != "pod-kill" or spec.get("mode") != "one":
        raise ValueError("runner accepts only mode=one pod-kill")
    if selector.get("namespaces") != [NAMESPACE]:
        raise ValueError("selector must be limited to chaosatlas-p09")
    if selector.get("labelSelectors") != API_SELECTOR:
        raise ValueError("selector must use the exact API selector")
    if set(selector) != {"namespaces", "labelSelectors"}:
        raise ValueError("selector must use the exact selector shape")
    name = str(metadata.get("name") or "")
    if not name:
        raise ValueError("mutation name is required")
    return name, API_SELECTOR


def residual_chaos() -> list[dict[str, Any]]:
    data, error = kubectl_json(["get", CHAOS_RESOURCES, "-n", NAMESPACE])
    if error:
        raise RuntimeError(f"cannot verify P09 Chaos cleanup: {error}")
    return [
        {"kind": item.get("kind"), "name": item.get("metadata", {}).get("name")}
        for item in (data or {}).get("items", [])
    ]


def namespace_health() -> dict[str, Any]:
    deployments, dep_error = kubectl_json(["get", "deployments", "-n", NAMESPACE])
    pods, pod_error = kubectl_json(["get", "pods", "-n", NAMESPACE])
    if dep_error or pod_error:
        raise RuntimeError(dep_error or pod_error)
    dep_rows = []
    for item in (deployments or {}).get("items", []):
        desired = int(item.get("spec", {}).get("replicas", 1) or 0)
        status = item.get("status", {})
        dep_rows.append(
            {
                "name": item.get("metadata", {}).get("name"),
                "desired": desired,
                "ready": int(status.get("readyReplicas", 0) or 0),
                "available": int(status.get("availableReplicas", 0) or 0),
                "updated": int(status.get("updatedReplicas", 0) or 0),
            }
        )
    pod_rows = []
    for item in (pods or {}).get("items", []):
        phase = item.get("status", {}).get("phase")
        ready = any(
            c.get("type") == "Ready" and c.get("status") == "True"
            for c in item.get("status", {}).get("conditions", [])
            if isinstance(c, dict)
        )
        if phase != "Succeeded":
            pod_rows.append(
                {
                    "name": item.get("metadata", {}).get("name"),
                    "uid": item.get("metadata", {}).get("uid"),
                    "ready": ready,
                    "terminating": bool(item.get("metadata", {}).get("deletionTimestamp")),
                }
            )
    healthy = (
        len(dep_rows) == 6
        and all(row["desired"] == row["ready"] == row["available"] == row["updated"] for row in dep_rows)
        and len(pod_rows) == 6
        and all(row["ready"] and not row["terminating"] for row in pod_rows)
    )
    return {"healthy": healthy, "deployments": dep_rows, "pods": pod_rows}


def wait_namespace_stable(timeout: float, stable_checks: int = 3) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    stable = 0
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = namespace_health()
        stable = stable + 1 if last["healthy"] else 0
        if stable >= stable_checks:
            return {**last, "stable_checks": stable}
        time.sleep(1)
    raise RuntimeError(f"P09 namespace did not stabilize: {json.dumps(last, ensure_ascii=True)}")


def pod_snapshot(labels: dict[str, str]) -> list[dict[str, Any]]:
    selector = ",".join(f"{key}={value}" for key, value in sorted(labels.items()))
    data, error = kubectl_json(["get", "pods", "-n", NAMESPACE, "-l", selector])
    if error:
        raise RuntimeError(error)
    return [
        {
            "name": item.get("metadata", {}).get("name"),
            "uid": item.get("metadata", {}).get("uid"),
            "ready": any(
                c.get("type") == "Ready" and c.get("status") == "True"
                for c in item.get("status", {}).get("conditions", [])
                if isinstance(c, dict)
            ),
            "terminating": bool(item.get("metadata", {}).get("deletionTimestamp")),
        }
        for item in (data or {}).get("items", [])
    ]


def start_forward() -> subprocess.Popen[str]:
    return subprocess.Popen(
        ["kubectl", "port-forward", "-n", NAMESPACE, f"svc/{SERVICE}", f"{LOCAL_PORT}:{REMOTE_PORT}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def stop_forward(process: subprocess.Popen[str] | None) -> None:
    if process is None:
        return
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    process.communicate()


def wait_forward(process: subprocess.Popen[str], timeout: float = 20) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            out, err = process.communicate()
            raise RuntimeError(f"port-forward exited: {(err or out).strip()}")
        try:
            with socket.create_connection(("127.0.0.1", LOCAL_PORT), timeout=0.5):
                return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError("P09 API port-forward did not become ready")


def request(timeout: float = 5) -> dict[str, Any]:
    started = time.monotonic()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{LOCAL_PORT}{ORACLE_PATH}", timeout=timeout) as response:
            body = response.read(65536).decode("utf-8", errors="replace")
            return {"observed_at": now(), "status_code": response.status, "latency_ms": round((time.monotonic() - started) * 1000, 3), "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(), "error": None}
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        return {"observed_at": now(), "status_code": getattr(exc, "code", None), "latency_ms": round((time.monotonic() - started) * 1000, 3), "body_sha256": None, "error": str(exc)}


def collect_oracle(required_successes: int, timeout: float) -> tuple[list[dict[str, Any]], bool]:
    deadline = time.monotonic() + timeout
    samples: list[dict[str, Any]] = []
    successes = 0
    process: subprocess.Popen[str] | None = None
    try:
        while time.monotonic() < deadline and successes < required_successes:
            if process is None or process.poll() is not None:
                stop_forward(process)
                process = start_forward()
                try:
                    wait_forward(process)
                except Exception:
                    stop_forward(process)
                    process = None
                    time.sleep(1)
                    continue
            sample = request()
            samples.append(sample)
            successes = successes + 1 if sample.get("status_code") == 200 else 0
            if sample.get("status_code") != 200:
                stop_forward(process)
                process = None
            time.sleep(1)
    finally:
        stop_forward(process)
    return samples, successes >= required_successes


def wait_injected(name: str, timeout: float = 45) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        data, error = kubectl_json(["get", "podchaos", name, "-n", NAMESPACE])
        if error:
            last = {"error": error}
        else:
            status = (data or {}).get("status", {})
            experiment = status.get("experiment", {}) or {}
            records = experiment.get("containerRecords", []) or []
            injected = sum(int(record.get("injectedCount", 0) or 0) for record in records)
            last = {"injected_count": injected, "conditions": status.get("conditions", [])}
            if injected >= 1:
                return last
        time.sleep(0.5)
    return last


def cleanup(name: str) -> dict[str, Any]:
    code, out, err = kubectl(["delete", "podchaos", name, "-n", NAMESPACE, "--ignore-not-found=true"])
    verify_code, verify_out, verify_err = kubectl(["get", "podchaos", name, "-n", NAMESPACE])
    verify_text = (verify_err or verify_out).lower()
    absent = verify_code != 0 and "notfound" in verify_text.replace(" ", "") or (
        verify_code != 0 and "not found" in verify_text
    )
    return {"delete_code": code, "delete_output": (out or err).strip(), "verify_code": verify_code, "verify_output": (verify_out or verify_err).strip(), "absent_confirmed": bool(absent)}


def wait_replacement(before_uids: set[str], timeout: float) -> tuple[bool, dict[str, Any]]:
    deadline = time.monotonic() + timeout
    stable = 0
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        pods = [pod for pod in pod_snapshot(API_SELECTOR) if not pod["terminating"]]
        ready = [pod for pod in pods if pod["ready"]]
        new_uids = {pod["uid"] for pod in ready} - before_uids
        last = {"pods": pods, "before_uids": sorted(before_uids), "new_ready_uids": sorted(new_uids)}
        recovered = len(pods) == 1 and len(ready) == 1 and bool(new_uids)
        stable = stable + 1 if recovered else 0
        if stable >= 3:
            return True, {**last, "stable_checks": stable}
        time.sleep(1)
    return False, last


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mutation", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--expected-context", default="minikube")
    parser.add_argument("--baseline-successes", type=positive_int, default=5)
    parser.add_argument("--washout-successes", type=positive_int, default=10)
    parser.add_argument("--recovery-timeout", type=float, default=180)
    args = parser.parse_args()
    if args.report.exists():
        raise SystemExit(f"refusing to overwrite existing report: {args.report}")
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "tool": "run_p09_podchaos",
        "started_at": now(),
        "namespace": NAMESPACE,
        "mutation_path": str(args.mutation).replace("\\", "/"),
        "status": "running",
        "baseline": None,
        "injection": {"applied": False, "injected": False},
        "cleanup": None,
        "recovery": None,
        "washout": None,
        "errors": [],
        "human_review": "pending",
    }
    apply_attempted = False
    name = ""
    mutation_bytes: bytes | None = None
    try:
        mutation_bytes = args.mutation.read_bytes()
        mutation_text = mutation_bytes.decode("utf-8")
        document = yaml.safe_load(mutation_text)
        name, labels = validate_mutation(document)
        context_code, context, context_error = kubectl(["config", "current-context"])
        if context_code != 0 or context.strip() != args.expected_context:
            raise RuntimeError(f"unexpected kubectl context: {(context_error or context).strip()}")
        residual = residual_chaos()
        if residual:
            raise RuntimeError(f"pre-existing P09 Chaos resources: {residual}")
        report["preflight_health"] = wait_namespace_stable(60)
        baseline_samples, baseline_ok = collect_oracle(args.baseline_successes, 90)
        report["baseline"] = {"samples": baseline_samples, "successes_required": args.baseline_successes, "stable": baseline_ok}
        if not baseline_ok:
            raise RuntimeError("P09 API baseline did not become stable")
        before = pod_snapshot(labels)
        before_uids = {str(pod["uid"]) for pod in before if pod.get("uid")}
        if len(before) != 1 or len(before_uids) != 1 or not before[0]["ready"]:
            raise RuntimeError(f"expected one Ready API Pod before injection: {before}")
        report["target_before"] = before
        apply_attempted = True
        code, out, err = kubectl(["apply", "-f", "-"], input_text=mutation_text)
        report["injection"]["apply"] = {"return_code": code, "output": (out or err).strip()}
        if code != 0:
            raise RuntimeError("kubectl apply failed")
        report["injection"]["applied"] = True
        status = wait_injected(name)
        report["injection"]["status"] = status
        report["injection"]["injected"] = int(status.get("injected_count", 0) or 0) >= 1
        if not report["injection"]["injected"]:
            raise RuntimeError("PodChaos injection was not confirmed")
    except Exception as exc:
        report["errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        if apply_attempted and name:
            report["cleanup"] = cleanup(name)
            if not report["cleanup"]["absent_confirmed"]:
                report["errors"].append("cleanup absence was not confirmed")
            try:
                before_uids = {str(pod["uid"]) for pod in report.get("target_before", []) if pod.get("uid")}
                recovered, recovery = wait_replacement(before_uids, args.recovery_timeout)
                report["recovery"] = {"recovered": recovered, **recovery}
                if not recovered:
                    report["errors"].append("API Pod identity replacement did not stabilize")
                samples, stable = collect_oracle(args.washout_successes, args.recovery_timeout)
                report["washout"] = {"samples": samples, "successes_required": args.washout_successes, "stable": stable}
                if not stable:
                    report["errors"].append("P09 API washout did not regain stable HTTP 200")
                report["post_recovery_health"] = wait_namespace_stable(args.recovery_timeout)
            except Exception as exc:
                report["errors"].append(f"recovery verification failed: {type(exc).__name__}: {exc}")
        try:
            report["post_cleanup_residual_chaos"] = residual_chaos()
            if report["post_cleanup_residual_chaos"]:
                report["errors"].append("P09 Chaos resources remain after cleanup")
        except Exception as exc:
            report["errors"].append(f"residual check failed: {exc}")
    report["mutation_sha256"] = (
        hashlib.sha256(mutation_bytes).hexdigest() if mutation_bytes is not None else None
    )
    report["finished_at"] = now()
    report["status"] = "completed" if not report["errors"] else "failed"
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if report["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
