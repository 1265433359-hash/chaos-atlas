"""Execute one P02 PodChaos experiment with baseline/recovery/cleanup evidence.

Unlike the legacy runner, this script is scoped to the P02 lab namespace and
the currently deployed Spring Petclinic service. It performs one mutation at
a time and always attempts cleanup after an apply.
"""

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

ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = "chaosatlas-p02"
SERVICE = "api-gateway"
REMOTE_PORT = 8080
LOCAL_PORT = 18080
ZIPKIN_LOCAL_PORT = 19411
ZIPKIN_REMOTE_PORT = 9411
ORACLE_PATH = "/api/gateway/owners/1"
CHAOS_RESOURCES = ("podchaos", "networkchaos", "stresschaos")
DIAGNOSTIC_DEPLOYMENTS = (
    "api-gateway",
    "discovery-server",
    "customers-service",
    "visits-service",
    "vets-service",
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def kubectl(args: list[str], timeout: int = 30) -> tuple[int, str, str]:
    try:
        p = subprocess.run(["kubectl", *args], capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
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
    return value if isinstance(value, dict) else None, None


def cluster_identity() -> dict[str, Any]:
    code, context, context_error = kubectl(["config", "current-context"])
    nodes, nodes_error = kubectl_json(["get", "nodes"])
    if code != 0 or nodes_error:
        raise RuntimeError(f"cluster identity unavailable: {(context_error or nodes_error or context).strip()}")
    return {
        "context": context.strip(),
        "nodes": [
            {
                "name": item.get("metadata", {}).get("name"),
                "uid": item.get("metadata", {}).get("uid"),
                "kubernetes_version": item.get("status", {}).get("nodeInfo", {}).get("kubeletVersion"),
            }
            for item in (nodes or {}).get("items", [])
        ],
    }


def residual_chaos() -> list[dict[str, Any]]:
    data, error = kubectl_json(["get", ",".join(CHAOS_RESOURCES), "-A"])
    if error:
        raise RuntimeError(f"cannot verify global Chaos Mesh cleanup: {error}")
    return [
        {
            "kind": item.get("kind"),
            "namespace": item.get("metadata", {}).get("namespace"),
            "name": item.get("metadata", {}).get("name"),
        }
        for item in (data or {}).get("items", [])
    ]


def namespace_health() -> dict[str, Any]:
    deployments, deployment_error = kubectl_json(["get", "deployments", "-n", NAMESPACE])
    pods, pod_error = kubectl_json(["get", "pods", "-n", NAMESPACE])
    if deployment_error or pod_error:
        raise RuntimeError(f"P02 health lookup failed: {deployment_error or pod_error}")
    deployment_rows = []
    for item in (deployments or {}).get("items", []):
        spec = item.get("spec", {})
        status = item.get("status", {})
        desired = int(spec.get("replicas", 1) or 0)
        deployment_rows.append(
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
        pod_rows.append(
            {
                "name": item.get("metadata", {}).get("name"),
                "uid": item.get("metadata", {}).get("uid"),
                "ready": any(
                    condition.get("type") == "Ready" and condition.get("status") == "True"
                    for condition in item.get("status", {}).get("conditions", [])
                    if isinstance(condition, dict)
                ),
                "terminating": bool(item.get("metadata", {}).get("deletionTimestamp")),
            }
        )
    healthy = (
        bool(deployment_rows)
        and all(row["desired"] == row["ready"] == row["available"] == row["updated"] for row in deployment_rows)
        and bool(pod_rows)
        and all(row["ready"] and not row["terminating"] for row in pod_rows)
    )
    return {"healthy": healthy, "deployments": deployment_rows, "pods": pod_rows}


def wait_namespace_stable(timeout: float = 180.0, stable_checks: int = 3) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    stable = 0
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = namespace_health()
        stable = stable + 1 if last["healthy"] else 0
        if stable >= stable_checks:
            return {**last, "stable_checks": stable}
        time.sleep(1)
    raise RuntimeError(f"P02 namespace did not become stable: {json.dumps(last, ensure_ascii=True)}")


def request(local_port: int, timeout: float = 5.0) -> dict[str, Any]:
    started = time.monotonic()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{local_port}{ORACLE_PATH}", timeout=timeout) as response:
            body = response.read(65536).decode("utf-8", errors="replace")
            return {"observed_at": now(), "status_code": response.status, "latency_ms": round((time.monotonic() - started) * 1000, 3), "body": body, "error": None}
    except urllib.error.HTTPError as exc:
        body = exc.read(65536).decode("utf-8", errors="replace")
        return {"observed_at": now(), "status_code": exc.code, "latency_ms": round((time.monotonic() - started) * 1000, 3), "body": body, "error": str(exc)}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"observed_at": now(), "status_code": None, "latency_ms": round((time.monotonic() - started) * 1000, 3), "body": None, "error": str(exc)}


def start_service_forward(service: str, local_port: int, remote_port: int) -> subprocess.Popen[str]:
    return subprocess.Popen(
        ["kubectl", "port-forward", "-n", NAMESPACE, f"svc/{service}", f"{local_port}:{remote_port}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def start_forward() -> subprocess.Popen[str]:
    return start_service_forward(SERVICE, LOCAL_PORT, REMOTE_PORT)


def wait_forward(proc: subprocess.Popen[str], timeout: float = 20.0, local_port: int = LOCAL_PORT) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            out, err = proc.communicate()
            raise RuntimeError(f"port-forward exited: {(err or out).strip()}")
        try:
            with socket.create_connection(("127.0.0.1", local_port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError("port-forward did not become ready")


def reconnect_forward(proc: subprocess.Popen[str] | None, timeout: float = 30.0) -> subprocess.Popen[str]:
    """Restart the tunnel and require the process to remain alive briefly."""
    stop_forward(proc)
    fresh = start_forward()
    try:
        wait_forward(fresh, timeout=timeout)
        time.sleep(0.5)
        if fresh.poll() is not None:
            out, err = fresh.communicate()
            raise RuntimeError(f"port-forward exited after opening: {(err or out).strip()}")
        return fresh
    except Exception:
        stop_forward(fresh)
        raise


def collect_post_recovery(
    proc: subprocess.Popen[str] | None,
    required_successes: int,
    timeout: float = 120.0,
) -> tuple[subprocess.Popen[str] | None, list[dict[str, Any]], int, list[str]]:
    """Retry tunnel startup until the recovered application serves HTTP 200."""
    deadline = time.monotonic() + timeout
    samples: list[dict[str, Any]] = []
    warnings: list[str] = []
    successes = 0
    stop_forward(proc)
    proc = None
    while time.monotonic() < deadline and successes < max(1, required_successes):
        if proc is None or proc.poll() is not None:
            try:
                proc = reconnect_forward(proc, timeout=min(30.0, max(1.0, deadline - time.monotonic())))
            except Exception as exc:
                warnings.append(f"post_recovery_port_forward_retry: {exc}")
                proc = None
                time.sleep(1)
                continue
        sample = request(LOCAL_PORT)
        samples.append(sample)
        if sample.get("status_code") == 200:
            successes += 1
        else:
            stop_forward(proc)
            proc = None
            time.sleep(1)
    return proc, samples, successes, warnings


def collect_post_cleanup_washout(
    duration: float,
    stable_successes: int,
    timeout: float,
    interval: float = 1.0,
) -> tuple[list[dict[str, Any]], int, bool, list[str]]:
    """Observe delayed effects and require a stable oracle before the next run."""
    started = time.monotonic()
    deadline = started + timeout
    minimum_end = started + max(0.0, duration)
    consecutive = 0
    samples: list[dict[str, Any]] = []
    warnings: list[str] = []
    proc: subprocess.Popen[str] | None = None
    try:
        while time.monotonic() < deadline:
            if proc is None or proc.poll() is not None:
                try:
                    proc = reconnect_forward(proc, timeout=min(30.0, max(1.0, deadline - time.monotonic())))
                except Exception as exc:
                    warnings.append(f"post_cleanup_port_forward_retry: {exc}")
                    proc = None
                    consecutive = 0
                    time.sleep(interval)
                    continue
            sample = request(LOCAL_PORT)
            samples.append(sample)
            if sample.get("status_code") == 200:
                consecutive += 1
            else:
                consecutive = 0
            if time.monotonic() >= minimum_end and consecutive >= max(1, stable_successes):
                return samples, consecutive, True, warnings
            if sample.get("status_code") != 200:
                stop_forward(proc)
                proc = None
            time.sleep(interval)
    finally:
        stop_forward(proc)
    return samples, consecutive, False, warnings


def stop_forward(proc: subprocess.Popen[str] | None) -> None:
    if proc is None:
        return
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    proc.communicate()


def pod_snapshot(labels: dict[str, Any]) -> list[dict[str, Any]]:
    selector = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
    data, error = kubectl_json(["get", "pods", "-n", NAMESPACE, "-l", selector])
    if error:
        raise RuntimeError(error)
    pods = []
    for item in (data or {}).get("items", []):
        ready = any(c.get("type") == "Ready" and c.get("status") == "True" for c in item.get("status", {}).get("conditions", []) if isinstance(c, dict))
        pods.append({"name": item.get("metadata", {}).get("name"), "uid": item.get("metadata", {}).get("uid"), "ready": ready, "terminating": bool(item.get("metadata", {}).get("deletionTimestamp"))})
    return pods


def wait_injected(kind: str, name: str, timeout: float = 45.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        data, error = kubectl_json(["get", "podchaos", name, "-n", NAMESPACE])
        if error:
            last = {"error": error}
        else:
            status = (data or {}).get("status") or {}
            experiment = status.get("experiment") or {}
            records = experiment.get("containerRecords") or []
            injected = sum(int(r.get("injectedCount", 0) or 0) for r in records)
            recovered = sum(int(r.get("recoveredCount", 0) or 0) for r in records)
            last = {"injected_count": injected, "recovered_count": recovered, "desired_phase": experiment.get("desiredPhase"), "conditions": status.get("conditions", [])}
            if injected >= 1:
                return last
        time.sleep(0.5)
    return last


def wait_recovery(labels: dict[str, Any], before_uids: set[str], timeout: float = 150.0) -> tuple[bool, dict[str, Any]]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    stable = 0
    while time.monotonic() < deadline:
        pods = pod_snapshot(labels)
        active = [p for p in pods if not p["terminating"]]
        ready = [p for p in active if p["ready"]]
        last = {"pods": pods, "active_count": len(active), "ready_count": len(ready), "before_uids": sorted(before_uids), "new_ready_uids": sorted({p["uid"] for p in ready} - before_uids)}
        recovered = len(active) == 1 and len(ready) == 1 and bool(set(last["new_ready_uids"]))
        stable = stable + 1 if recovered else 0
        if stable >= 2:
            return True, last
        time.sleep(1)
    return False, last


def cleanup(name: str) -> dict[str, Any]:
    code, out, err = kubectl(["delete", "podchaos", name, "-n", NAMESPACE, "--ignore-not-found=true"])
    verify_code, verify_out, verify_err = kubectl(["get", "podchaos", name, "-n", NAMESPACE])
    absent = verify_code != 0 and "not found" in (verify_err or verify_out).lower()
    return {"delete_code": code, "delete_output": (out or err).strip(), "verify_code": verify_code, "verify_output": (verify_out or verify_err).strip(), "absent_confirmed": absent}


def artifact_ref(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path.resolve()).replace("\\", "/")


def write_sidecar(path: Path, content: str, *, status: str, return_code: int, error: str | None = None) -> dict[str, Any]:
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
            ["logs", "-n", NAMESPACE, f"deployment/{deployment}", "--since-time", since_time, "--timestamps=true"],
            timeout=60,
        )
        if code == 0:
            results[deployment] = write_sidecar(path, out, status="captured" if out.strip() else "empty", return_code=code)
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
        payload = {"status": "unavailable", "error": error or "event payload was not a JSON object", "items": []}
        return write_sidecar(
            path,
            json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
            status="unavailable",
            return_code=1,
            error=str(payload["error"]),
        )
    items = [item for item in data.get("items", []) if (_event_time(item) or started) >= started]
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
    proc: subprocess.Popen[str] | None = None
    started = datetime.fromisoformat(since_time.replace("Z", "+00:00"))
    captured = datetime.now(timezone.utc)
    lookback_ms = max(300_000, int((captured - started).total_seconds() * 1000) + 60_000)
    query = urllib.parse.urlencode({"endTs": int(captured.timestamp() * 1000), "lookback": lookback_ms, "limit": 100})
    try:
        proc = start_service_forward("tracing-server", ZIPKIN_LOCAL_PORT, ZIPKIN_REMOTE_PORT)
        wait_forward(proc, timeout=20, local_port=ZIPKIN_LOCAL_PORT)
        with urllib.request.urlopen(f"http://127.0.0.1:{ZIPKIN_LOCAL_PORT}/api/v2/traces?{query}", timeout=20) as response:
            raw = response.read(8 * 1024 * 1024).decode("utf-8", errors="replace")
        value = json.loads(raw)
        if not isinstance(value, list):
            raise ValueError("Zipkin trace response root is not an array")
        traces = [trace for trace in value if _trace_overlaps(trace, int(started.timestamp() * 1_000_000))]
        payload = {"capture_since": since_time, "query": query, "traces": traces}
        status = "captured" if traces else "empty"
        metadata = write_sidecar(path, json.dumps(payload, indent=2, ensure_ascii=True) + "\n", status=status, return_code=0)
        metadata["trace_count"] = len(traces)
        metadata["trace_unavailable"] = not traces
        return metadata
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
        message = str(exc)
        payload = {"capture_since": since_time, "status": "unavailable", "trace_unavailable": True, "error": message, "traces": []}
        metadata = write_sidecar(
            path,
            json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
            status="unavailable",
            return_code=1,
            error=message,
        )
        metadata["trace_count"] = 0
        metadata["trace_unavailable"] = True
        return metadata
    finally:
        stop_forward(proc)


def capture_diagnostics(report_path: Path, since_time: str) -> dict[str, Any]:
    """Collect bounded root-cause evidence without changing cleanup outcome."""
    return {
        "captured_at": now(),
        "capture_since": since_time,
        "logs": capture_logs(report_path, since_time),
        "events": capture_events(report_path, since_time),
        "zipkin": capture_zipkin(report_path, since_time),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mutation", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--baseline-count", type=int, default=5)
    parser.add_argument("--observe-count", type=int, default=10)
    parser.add_argument("--arm", required=True)
    parser.add_argument("--mutation-id", required=True)
    parser.add_argument("--replicate", type=int, required=True)
    parser.add_argument("--expected-context")
    parser.add_argument("--washout-seconds", type=float, default=0.0)
    parser.add_argument("--washout-stable-successes", type=int, default=10)
    parser.add_argument("--washout-timeout", type=float, default=180.0)
    parser.add_argument("--capture-diagnostics", action="store_true")
    args = parser.parse_args()
    report: dict[str, Any] = {
        "schema_version": 3,
        "tool": "run_p02_podchaos",
        "experiment": {"project": "P02", "arm": args.arm, "mutation_id": args.mutation_id, "replicate": args.replicate},
        "mutation": str(args.mutation).replace("\\", "/"),
        "started_at": now(),
        "mutation_applied": False,
        "baseline": [],
        "requests": [],
        "lifecycle": {},
        "errors": [],
        "warnings": [],
    }
    proc: subprocess.Popen[str] | None = None
    applied = False
    doc = yaml.safe_load(args.mutation.read_text(encoding="utf-8"))
    try:
        report["cluster"] = cluster_identity()
        if args.expected_context and report["cluster"]["context"] != args.expected_context:
            raise RuntimeError(
                f"kubectl context changed: expected {args.expected_context}, got {report['cluster']['context']}"
            )
        residual = residual_chaos()
        report["lifecycle"]["preflight_residual_chaos"] = residual
        if residual:
            raise RuntimeError(f"residual Chaos Mesh resources exist before injection: {residual}")
        report["lifecycle"]["pre_injection_namespace_health"] = wait_namespace_stable()
        if doc.get("kind") != "PodChaos" or doc.get("metadata", {}).get("namespace") != NAMESPACE:
            raise RuntimeError("only P02 PodChaos manifests are accepted")
        spec = doc.get("spec") or {}
        labels = ((spec.get("selector") or {}).get("labelSelectors") or {})
        name = str(doc["metadata"]["name"])
        report["target"] = {"name": name, "labels": labels, "namespace": NAMESPACE}
        proc = start_forward()
        wait_forward(proc)
        baseline_deadline = time.monotonic() + 60
        while time.monotonic() < baseline_deadline and sum(sample.get("status_code") == 200 for sample in report["baseline"]) < max(1, args.baseline_count):
            sample = request(LOCAL_PORT)
            report["baseline"].append(sample)
            time.sleep(0.5 if sample.get("status_code") == 200 else 1)
        if sum(sample.get("status_code") == 200 for sample in report["baseline"]) < max(1, args.baseline_count):
            raise RuntimeError("invalid_baseline: insufficient successful HTTP 200 business-oracle samples")
        before = pod_snapshot(labels)
        before_uids = {str(p["uid"]) for p in before if p.get("uid")}
        report["lifecycle"]["pre_injection_pods"] = before
        code, out, err = kubectl(["apply", "-f", str(args.mutation)])
        report["apply"] = {"return_code": code, "stdout": out.strip(), "stderr": err.strip()}
        if code != 0:
            raise RuntimeError("kubectl apply failed")
        applied = True
        report["mutation_applied"] = True
        injected = wait_injected("PodChaos", name)
        report["lifecycle"]["injected_status"] = injected
        report["lifecycle"]["injected"] = injected.get("injected_count", 0) >= 1
        if not report["lifecycle"]["injected"]:
            raise RuntimeError("Chaos Mesh did not confirm injection")
        # Keep the pre-injection tunnel long enough to capture the immediate
        # failure. It may exit when the selected Pod is killed; that is valid
        # observation evidence, not a runner error.
        for _ in range(max(1, min(args.observe_count, 3))):
            report["requests"].append(request(LOCAL_PORT))
            if proc is not None and proc.poll() is not None:
                report["lifecycle"]["port_forward_interrupted"] = True
                break
            time.sleep(0.5)
        recovered, recovery = wait_recovery(labels, before_uids)
        report["lifecycle"]["recovered"] = recovered
        report["lifecycle"]["recovery_status"] = recovery
        if not recovered:
            raise RuntimeError("target Pod did not recover with a replacement UID")
        # After recovery, reconnect and collect stable business responses so
        # the report contains an independent post-fault oracle as well.
        if recovered:
            required_successes = max(1, args.observe_count - min(args.observe_count, 3))
            proc, samples, post_recovery_successes, warnings = collect_post_recovery(
                proc,
                required_successes,
            )
            report["requests"].extend(samples)
            report["warnings"].extend(warnings)
            report["lifecycle"]["post_recovery_http_200_count"] = post_recovery_successes
            if post_recovery_successes < required_successes:
                report["errors"].append(
                    "post_recovery_oracle_unconfirmed: insufficient HTTP 200 responses after recovered Pod became Ready"
                )
            report["lifecycle"]["post_recovery_namespace_health"] = wait_namespace_stable()
    except Exception as exc:
        report["errors"].append(str(exc))
    finally:
        stop_forward(proc)
        if applied:
            report["lifecycle"]["cleanup"] = cleanup(str(doc["metadata"]["name"]))
            if not report["lifecycle"]["cleanup"]["absent_confirmed"]:
                report["errors"].append("cleanup_unconfirmed: Chaos Mesh resource may still exist")
        try:
            report["lifecycle"]["post_cleanup_residual_chaos"] = residual_chaos()
            if report["lifecycle"]["post_cleanup_residual_chaos"]:
                report["errors"].append("post_cleanup_residual_chaos: one or more Chaos Mesh resources remain")
        except Exception as exc:
            report["errors"].append(str(exc))
        if applied and args.washout_seconds > 0 and not report["lifecycle"].get("post_cleanup_residual_chaos"):
            samples, consecutive, stable, warnings = collect_post_cleanup_washout(
                args.washout_seconds,
                args.washout_stable_successes,
                args.washout_timeout,
            )
            report["warnings"].extend(warnings)
            report["lifecycle"]["post_cleanup_washout"] = {
                "minimum_duration_s": args.washout_seconds,
                "stable_successes_required": args.washout_stable_successes,
                "samples": samples,
                "http_200": sum(sample.get("status_code") == 200 for sample in samples),
                "http_500": sum(sample.get("status_code") == 500 for sample in samples),
                "non_200": sum(sample.get("status_code") != 200 for sample in samples),
                "final_consecutive_http_200": consecutive,
                "stable": stable,
            }
            if not stable:
                report["errors"].append("post_cleanup_washout_unstable: business oracle did not regain sustained health")
        if args.capture_diagnostics:
            try:
                report["diagnostics"] = capture_diagnostics(args.report, report["started_at"])
            except Exception as exc:
                # Diagnostics are supporting evidence. Cleanup and the primary
                # runtime verdict remain valid, but causal review must stay open.
                report["diagnostics"] = {"status": "unavailable", "error": str(exc), "captured_at": now()}
                report["warnings"].append(f"diagnostics_unavailable: {exc}")
    report["finished_at"] = now()
    report["status"] = "completed" if not report["errors"] else "failed"
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if report["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
