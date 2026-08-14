"""Run one bounded P09 API PodChaos pilot in chaosatlas-p09 only."""

from __future__ import annotations

import argparse
import hashlib
import json
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from tools.p09_execution_gate import check as execution_gate_check
from tools.unified_experiment_protocol import (
    comparison_eligibility,
    validate_lifecycle_report,
)


NAMESPACE = "chaosatlas-p09"
SERVICE = "api"
REMOTE_PORT = 5001
LOCAL_PORT = 15092
ZIPKIN_LOCAL_PORT = 19412
ZIPKIN_REMOTE_PORT = 9411
ORACLE_PATH = "/health"
CHAOS_RESOURCES = "podchaos,networkchaos,stresschaos"
DIAGNOSTIC_DEPLOYMENTS = (
    "api",
    "worker",
    "worker-beat",
    "web",
    "postgres",
    "redis",
)
API_SELECTOR = {
    "app.kubernetes.io/name": "api",
    "app.kubernetes.io/part-of": NAMESPACE,
}
UNIFIED_API_SELECTOR = {
    **API_SELECTOR,
    "chaosatlas.io/profile": "minimal",
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
    if selector.get("labelSelectors") not in (API_SELECTOR, UNIFIED_API_SELECTOR):
        raise ValueError("selector must use an exact API selector")
    if set(selector) != {"namespaces", "labelSelectors"}:
        raise ValueError("selector must use the exact selector shape")
    name = str(metadata.get("name") or "")
    if not name:
        raise ValueError("mutation name is required")
    return name, selector["labelSelectors"]


def residual_chaos() -> list[dict[str, Any]]:
    data, error = kubectl_json(["get", CHAOS_RESOURCES, "-A"])
    if error:
        raise RuntimeError(f"cannot verify global Chaos cleanup: {error}")
    return [
        {
            "kind": item.get("kind"),
            "name": item.get("metadata", {}).get("name"),
            "namespace": item.get("metadata", {}).get("namespace"),
        }
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


def start_service_forward(
    service: str, local_port: int, remote_port: int
) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [
            "kubectl",
            "port-forward",
            "-n",
            NAMESPACE,
            f"svc/{service}",
            f"{local_port}:{remote_port}",
        ],
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


def wait_forward(
    process: subprocess.Popen[str],
    timeout: float = 20,
    local_port: int = LOCAL_PORT,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            out, err = process.communicate()
            raise RuntimeError(f"port-forward exited: {(err or out).strip()}")
        try:
            with socket.create_connection(("127.0.0.1", local_port), timeout=0.5):
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


def wait_replacement(
    before_uids: set[str],
    labels: dict[str, str],
    timeout: float,
) -> tuple[bool, dict[str, Any]]:
    deadline = time.monotonic() + timeout
    stable = 0
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        pods = [pod for pod in pod_snapshot(labels) if not pod["terminating"]]
        ready = [pod for pod in pods if pod["ready"]]
        new_uids = {pod["uid"] for pod in ready} - before_uids
        last = {"pods": pods, "before_uids": sorted(before_uids), "new_ready_uids": sorted(new_uids)}
        recovered = len(pods) == 1 and len(ready) == 1 and bool(new_uids)
        stable = stable + 1 if recovered else 0
        if stable >= 3:
            return True, {**last, "stable_checks": stable}
        time.sleep(1)
    return False, last


def artifact_ref(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")


def write_sidecar(
    path: Path,
    content: str,
    *,
    status: str,
    return_code: int,
    error: str | None = None,
) -> dict[str, Any]:
    data = content.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {
        "status": status,
        "return_code": return_code,
        "path": artifact_ref(path),
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "error": error,
    }


def capture_logs(report_path: Path, since_time: str) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for deployment in DIAGNOSTIC_DEPLOYMENTS:
        path = report_path.with_name(f"{report_path.stem}.{deployment}.log")
        code, out, err = kubectl(
            [
                "logs",
                "-n",
                NAMESPACE,
                f"deployment/{deployment}",
                "--since-time",
                since_time,
                "--timestamps=true",
            ],
            timeout=60,
        )
        out = out or ""
        err = err or ""
        if code == 0:
            results[deployment] = write_sidecar(
                path,
                out,
                status="captured" if out.strip() else "empty",
                return_code=code,
            )
        else:
            message = (err or out).strip() or "kubectl logs returned no diagnostic text"
            results[deployment] = write_sidecar(
                path,
                f"diagnostic_unavailable: {message}\n",
                status="unavailable",
                return_code=code,
                error=message,
            )
    return results


def _event_time(item: dict[str, Any]) -> datetime | None:
    value = (
        item.get("eventTime")
        or item.get("lastTimestamp")
        or (item.get("series") or {}).get("lastObservedTime")
        or (item.get("metadata") or {}).get("creationTimestamp")
    )
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def capture_events(report_path: Path, since_time: str) -> dict[str, Any]:
    path = report_path.with_name(f"{report_path.stem}.events.json")
    data, error = kubectl_json(["get", "events", "-n", NAMESPACE], timeout=60)
    started = datetime.fromisoformat(since_time.replace("Z", "+00:00"))
    if error or data is None:
        payload = {
            "status": "unavailable",
            "error": error or "event payload was not a JSON object",
            "items": [],
        }
        return write_sidecar(
            path,
            json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
            status="unavailable",
            return_code=1,
            error=str(payload["error"]),
        )
    items = [
        item
        for item in data.get("items", [])
        if (_event_time(item) or started) >= started
    ]
    payload = {
        "apiVersion": data.get("apiVersion", "v1"),
        "kind": data.get("kind", "EventList"),
        "capture_since": since_time,
        "items": items,
    }
    return write_sidecar(
        path,
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        status="captured" if items else "empty",
        return_code=0,
    )


def _trace_overlaps(trace: Any, started_us: int) -> bool:
    return isinstance(trace, list) and any(
        isinstance(span, dict)
        and isinstance(span.get("timestamp"), (int, float))
        and int(span["timestamp"]) + int(span.get("duration", 0) or 0) >= started_us
        for span in trace
    )


def capture_zipkin(report_path: Path, since_time: str) -> dict[str, Any]:
    path = report_path.with_name(f"{report_path.stem}.zipkin.json")
    process: subprocess.Popen[str] | None = None
    started = datetime.fromisoformat(since_time.replace("Z", "+00:00"))
    captured = datetime.now(timezone.utc)
    lookback_ms = max(
        300_000, int((captured - started).total_seconds() * 1000) + 60_000
    )
    query = urllib.parse.urlencode(
        {
            "endTs": int(captured.timestamp() * 1000),
            "lookback": lookback_ms,
            "limit": 100,
        }
    )
    try:
        process = start_service_forward(
            "tracing-server", ZIPKIN_LOCAL_PORT, ZIPKIN_REMOTE_PORT
        )
        wait_forward(process, timeout=20, local_port=ZIPKIN_LOCAL_PORT)
        with urllib.request.urlopen(
            f"http://127.0.0.1:{ZIPKIN_LOCAL_PORT}/api/v2/traces?{query}",
            timeout=20,
        ) as response:
            raw = response.read(8 * 1024 * 1024).decode("utf-8", errors="replace")
        value = json.loads(raw)
        if not isinstance(value, list):
            raise ValueError("Zipkin trace response root is not an array")
        traces = [
            trace
            for trace in value
            if _trace_overlaps(trace, int(started.timestamp() * 1_000_000))
        ]
        payload = {"capture_since": since_time, "query": query, "traces": traces}
        metadata = write_sidecar(
            path,
            json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
            status="captured" if traces else "empty",
            return_code=0,
        )
        metadata["trace_count"] = len(traces)
        return metadata
    except (
        OSError,
        TimeoutError,
        urllib.error.URLError,
        json.JSONDecodeError,
        ValueError,
        RuntimeError,
    ) as exc:
        message = str(exc)
        payload = {
            "capture_since": since_time,
            "status": "unavailable",
            "trace_unavailable": True,
            "error": message,
            "traces": [],
        }
        metadata = write_sidecar(
            path,
            json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
            status="unavailable",
            return_code=1,
            error=message,
        )
        metadata["trace_count"] = 0
        return metadata
    finally:
        stop_forward(process)


def capture_diagnostics(report_path: Path, since_time: str) -> dict[str, Any]:
    return {
        "captured_at": now(),
        "capture_since": since_time,
        "logs": capture_logs(report_path, since_time),
        "events": capture_events(report_path, since_time),
        "zipkin": capture_zipkin(report_path, since_time),
    }


def collect_washout(
    required_successes: int,
    minimum_duration: float,
    timeout: float,
) -> tuple[list[dict[str, Any]], bool]:
    started = time.monotonic()
    samples: list[dict[str, Any]] = []
    consecutive = 0
    deadline = started + timeout
    process: subprocess.Popen[str] | None = None
    try:
        while time.monotonic() < deadline:
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
            if sample.get("status_code") == 200:
                consecutive += 1
            else:
                consecutive = 0
                stop_forward(process)
                process = None
            duration_ok = time.monotonic() - started >= minimum_duration
            if consecutive >= required_successes and duration_ok:
                return samples, True
            time.sleep(1)
    finally:
        stop_forward(process)
    return samples, False


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
    parser.add_argument("--washout-seconds", type=float, default=0.0)
    parser.add_argument("--washout-stable-successes", type=positive_int, default=None)
    parser.add_argument("--washout-timeout", type=float, default=None)
    parser.add_argument("--recovery-timeout", type=float, default=180)
    parser.add_argument("--arm", default="P09-unified")
    parser.add_argument("--mutation-id", default=None)
    parser.add_argument("--replicate", type=positive_int, default=1)
    parser.add_argument("--capture-diagnostics", action="store_true")
    parser.add_argument(
        "--profile-gate",
        type=Path,
        default=None,
        help="explicit P09 profile gate JSON; defaults to the execution-gate default",
    )
    args = parser.parse_args()
    washout_successes = args.washout_stable_successes or args.washout_successes
    washout_timeout = args.washout_timeout or args.recovery_timeout
    if args.report.exists():
        raise SystemExit(f"refusing to overwrite existing report: {args.report}")
    mutation_id = args.mutation_id or args.mutation.stem
    report: dict[str, Any] = {
        "schema_version": "unified-lifecycle-v1",
        "tool": "run_p09_podchaos",
        "project_id": "P09",
        "started_at": now(),
        "namespace": NAMESPACE,
        "arm": args.arm,
        "mutation_id": mutation_id,
        "replicate": args.replicate,
        "mutation": {
            "path": str(args.mutation).replace("\\", "/"),
            "sha256": None,
        },
        "status": "running",
        "baseline": {"pass": False, "samples": []},
        "injection": {"applied": False, "injected": False},
        "observation": {"samples": []},
        "recovery": {"recovered": False},
        "cleanup": {"absent_confirmed": False, "residual_resources": []},
        "washout": {"stable": False, "samples": []},
        "diagnostics": {"status": "not_configured"},
        "errors": [],
        "human_review": "pending",
    }
    apply_attempted = False
    name = ""
    mutation_bytes: bytes | None = None
    try:
        mutation_bytes = args.mutation.read_bytes()
        mutation_text = mutation_bytes.decode("utf-8")
        report["mutation"]["sha256"] = hashlib.sha256(mutation_bytes).hexdigest()
        document = yaml.safe_load(mutation_text)
        name, labels = validate_mutation(document)
        gate_kwargs = {}
        if args.profile_gate is not None:
            gate_kwargs["profile_gate"] = args.profile_gate
        report["execution_gate"] = execution_gate_check(args.mutation, **gate_kwargs)
        if report["execution_gate"].get("decision") != "ready_for_injection":
            raise RuntimeError(
                "P09 execution gate blocked: "
                + "; ".join(report["execution_gate"].get("errors", []))
            )
        context_code, context, context_error = kubectl(["config", "current-context"])
        if context_code != 0 or context.strip() != args.expected_context:
            raise RuntimeError(f"unexpected kubectl context: {(context_error or context).strip()}")
        residual = residual_chaos()
        if residual:
            raise RuntimeError(f"pre-existing P09 Chaos resources: {residual}")
        report["preflight_health"] = wait_namespace_stable(60)
        baseline_samples, baseline_ok = collect_oracle(args.baseline_successes, 90)
        report["baseline"] = {
            "pass": baseline_ok,
            "samples": baseline_samples,
            "successes_required": args.baseline_successes,
            "stable": baseline_ok,
        }
        if not baseline_ok:
            raise RuntimeError("P09 API baseline did not become stable")
        before = pod_snapshot(labels)
        before_uids = {str(pod["uid"]) for pod in before if pod.get("uid")}
        if len(before) != 1 or len(before_uids) != 1 or not before[0]["ready"]:
            raise RuntimeError(f"expected one Ready API Pod before injection: {before}")
        report["target_before"] = before
        report["target_labels"] = labels
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
        observation_samples, _ = collect_oracle(1, 30)
        report["observation"] = {
            "samples": observation_samples,
            "oracle": "P09 API /health during or immediately after confirmed injection",
        }
    except Exception as exc:
        report["errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        if apply_attempted and name:
            report["cleanup"] = cleanup(name)
            report["cleanup"].setdefault("residual_resources", [])
            if not report["cleanup"]["absent_confirmed"]:
                report["errors"].append("cleanup absence was not confirmed")
            try:
                before_uids = {str(pod["uid"]) for pod in report.get("target_before", []) if pod.get("uid")}
                recovered, recovery = wait_replacement(
                    before_uids,
                    report.get("target_labels", labels),
                    args.recovery_timeout,
                )
                report["recovery"] = {"recovered": recovered, **recovery}
                if not recovered:
                    report["errors"].append("API Pod identity replacement did not stabilize")
                if args.washout_seconds > 0:
                    samples, stable = collect_washout(
                        washout_successes,
                        args.washout_seconds,
                        washout_timeout,
                    )
                else:
                    samples, stable = collect_oracle(
                        washout_successes,
                        washout_timeout,
                    )
                report["washout"] = {
                    "samples": samples,
                    "successes_required": washout_successes,
                    "minimum_duration_seconds": args.washout_seconds,
                    "timeout_seconds": washout_timeout,
                    "stable": stable,
                }
                if not stable:
                    report["errors"].append("P09 API washout did not regain stable HTTP 200")
                report["post_recovery_health"] = wait_namespace_stable(args.recovery_timeout)
            except Exception as exc:
                report["errors"].append(f"recovery verification failed: {type(exc).__name__}: {exc}")
        try:
            report["post_cleanup_residual_chaos"] = residual_chaos()
            report["cleanup"]["residual_resources"] = report["post_cleanup_residual_chaos"]
            if report["post_cleanup_residual_chaos"]:
                report["errors"].append("P09 Chaos resources remain after cleanup")
        except Exception as exc:
            report["errors"].append(f"residual check failed: {exc}")
        if args.capture_diagnostics:
            try:
                report["diagnostics"] = capture_diagnostics(args.report, report["started_at"])
            except Exception as exc:
                report["diagnostics"] = {
                    "status": "unavailable",
                    "error": str(exc),
                    "captured_at": now(),
                }
                report["errors"].append(f"diagnostics unavailable: {exc}")
    report["mutation_sha256"] = report["mutation"].get("sha256")
    report["finished_at"] = now()
    validation = validate_lifecycle_report(report)
    eligibility = comparison_eligibility(report)
    report["protocol_validation"] = validation
    report["comparison_eligibility"] = eligibility
    report["status"] = (
        "completed"
        if not report["errors"] and validation["valid"] and eligibility["eligible"]
        else "failed"
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if report["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
