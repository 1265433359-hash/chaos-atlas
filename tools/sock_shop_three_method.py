"""Sock Shop three-method comparison helpers and isolated lifecycle runner.

The runner deliberately keeps the method identity separate from the runtime
mutation. All three methods must use the same mutation and business oracle;
method-specific discovery artifacts are recorded in the manifest, while
ChaosEater is never represented by an adapter or retrospective result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import yaml


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_NAMESPACE = "sock-shop"
METHOD_IDS = (
    "ChaosAtlas-full",
    "ChaosAtlas-ablation",
    "ChaosEater-full",
)
CHAOS_RESOURCES = ("podchaos", "networkchaos", "stresschaos")
TARGET_SERVICE = "front-end"
TARGET_LABELS = {"name": "front-end"}
TARGET_PATH = "/"
LOCAL_PORT = 18081
REMOTE_PORT = 80


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_method_id(method_id: str) -> bool:
    return method_id in METHOD_IDS


def _require_namespace(namespace: str) -> None:
    if namespace != ALLOWED_NAMESPACE:
        raise ValueError(f"Sock Shop runner only permits namespace {ALLOWED_NAMESPACE!r}")


def build_manifest(method_id: str, namespace: str, mutation: Path) -> dict[str, Any]:
    if not validate_method_id(method_id):
        raise ValueError(f"unsupported method id: {method_id}")
    _require_namespace(namespace)
    if not mutation.is_file():
        raise FileNotFoundError(mutation)
    return {
        "schema_version": "sock-shop-three-method-v1",
        "project_id": "SockShop",
        "method_id": method_id,
        "namespace": namespace,
        "mutation": {
            "path": str(mutation.resolve()).replace("\\", "/"),
            "sha256": sha256_file(mutation),
        },
        "native_input_required": method_id == "ChaosEater-full",
        "adapter_substitution_allowed": False,
        "human_review": "pending",
    }


def _bool(report: dict[str, Any], section: str, field: str) -> bool:
    value = report.get(section)
    return isinstance(value, dict) and value.get(field) is True


def comparison_status(report: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if report.get("method_id") not in METHOD_IDS:
        reasons.append("method_id")
    if report.get("namespace") != ALLOWED_NAMESPACE:
        reasons.append("namespace")
    if report.get("human_review") != "pending":
        reasons.append("human_review")
    mutation = report.get("mutation")
    if not isinstance(mutation, dict):
        reasons.append("mutation")
    else:
        path_value = mutation.get("path")
        recorded = mutation.get("sha256")
        if not isinstance(path_value, str) or not path_value:
            reasons.append("mutation.path")
        if not isinstance(recorded, str) or len(recorded) != 64:
            reasons.append("mutation.sha256")
        if isinstance(path_value, str) and isinstance(recorded, str):
            path = Path(path_value)
            if path.is_file() and sha256_file(path) != recorded:
                reasons.append("mutation.sha256")
    for section, field in (
        ("baseline", "pass"),
        ("injection", "applied"),
        ("injection", "injected"),
        ("recovery", "recovered"),
        ("washout", "stable"),
    ):
        if not _bool(report, section, field):
            reasons.append(f"{section}.{field}")
    cleanup = report.get("cleanup")
    if not isinstance(cleanup, dict) or cleanup.get("absent_confirmed") is not True:
        reasons.append("cleanup.absent_confirmed")
    if not isinstance(cleanup, dict) or cleanup.get("residual_resources") != []:
        reasons.append("cleanup.residual_resources")
    return {"eligible": not reasons, "reasons": sorted(set(reasons))}


def run_kubectl(args: list[str], timeout: int = 30) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            ["kubectl", *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return completed.returncode, completed.stdout or "", completed.stderr or ""
    except subprocess.TimeoutExpired as exc:
        return 124, str(exc.stdout or ""), str(exc.stderr or "kubectl timed out")


def kubectl_json(args: list[str], timeout: int = 30) -> tuple[dict[str, Any] | None, str | None]:
    code, out, err = run_kubectl([*args, "-o", "json"], timeout)
    if code != 0:
        return None, (err or out).strip()
    try:
        value = json.loads(out)
    except json.JSONDecodeError as exc:
        return None, str(exc)
    return value if isinstance(value, dict) else None, None


def residual_chaos() -> list[dict[str, Any]]:
    data, error = kubectl_json(["get", ",".join(CHAOS_RESOURCES), "-A"])
    if error:
        raise RuntimeError(error)
    return [
        {
            "kind": item.get("kind"),
            "namespace": item.get("metadata", {}).get("namespace"),
            "name": item.get("metadata", {}).get("name"),
        }
        for item in (data or {}).get("items", [])
    ]


def _ready_pods() -> list[dict[str, Any]]:
    data, error = kubectl_json(
        ["get", "pods", "-n", ALLOWED_NAMESPACE, "-l", "name=front-end"]
    )
    if error:
        raise RuntimeError(error)
    rows = []
    for item in (data or {}).get("items", []):
        conditions = item.get("status", {}).get("conditions", [])
        ready = any(
            condition.get("type") == "Ready" and condition.get("status") == "True"
            for condition in conditions
            if isinstance(condition, dict)
        )
        rows.append(
            {
                "name": item.get("metadata", {}).get("name"),
                "uid": item.get("metadata", {}).get("uid"),
                "ready": ready,
                "terminating": bool(item.get("metadata", {}).get("deletionTimestamp")),
            }
        )
    return rows


def namespace_health() -> dict[str, Any]:
    deployments, error = kubectl_json(["get", "deployments", "-n", ALLOWED_NAMESPACE])
    if error:
        raise RuntimeError(error)
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
    pods = _ready_pods()
    healthy = bool(deployment_rows) and all(
        row["desired"] == row["ready"] == row["available"] == row["updated"]
        for row in deployment_rows
    ) and bool(pods) and all(row["ready"] and not row["terminating"] for row in pods)
    return {"pass": healthy, "deployments": deployment_rows, "pods": pods}


def wait_health(timeout: float = 300.0, stable_checks: int = 3) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    stable = 0
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = namespace_health()
        stable = stable + 1 if last["pass"] else 0
        if stable >= stable_checks:
            return {**last, "stable_checks": stable}
        time.sleep(2)
    return {**last, "stable_checks": stable}


def start_forward(local_port: int = LOCAL_PORT) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [
            "kubectl",
            "port-forward",
            "-n",
            ALLOWED_NAMESPACE,
            f"svc/{TARGET_SERVICE}",
            f"{local_port}:{REMOTE_PORT}",
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


def wait_forward(process: subprocess.Popen[str], local_port: int = LOCAL_PORT, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            out, err = process.communicate()
            raise RuntimeError((err or out).strip() or "port-forward exited")
        try:
            with socket.create_connection(("127.0.0.1", local_port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.25)
    raise TimeoutError("port-forward did not become ready")


def request(local_port: int = LOCAL_PORT, timeout: float = 10.0) -> dict[str, Any]:
    started = time.monotonic()
    try:
        with urlopen(f"http://127.0.0.1:{local_port}{TARGET_PATH}", timeout=timeout) as response:
            body = response.read(65536).decode("utf-8", errors="replace")
            return {
                "status_code": response.status,
                "latency_ms": round((time.monotonic() - started) * 1000, 3),
                "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                "error": None,
            }
    except HTTPError as exc:
        return {
            "status_code": exc.code,
            "latency_ms": round((time.monotonic() - started) * 1000, 3),
            "body_sha256": None,
            "error": str(exc),
        }
    except (URLError, TimeoutError, OSError) as exc:
        return {
            "status_code": None,
            "latency_ms": round((time.monotonic() - started) * 1000, 3),
            "body_sha256": None,
            "error": str(exc),
        }


def wait_injected(name: str, timeout: float = 60.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        data, error = kubectl_json(["get", "podchaos", name, "-n", ALLOWED_NAMESPACE])
        if error:
            last = {"error": error}
        else:
            status = (data or {}).get("status") or {}
            experiment = status.get("experiment") or {}
            records = experiment.get("containerRecords") or []
            injected = sum(int(row.get("injectedCount", 0) or 0) for row in records)
            recovered = sum(int(row.get("recoveredCount", 0) or 0) for row in records)
            last = {
                "injected_count": injected,
                "recovered_count": recovered,
                "conditions": status.get("conditions", []),
            }
            if injected >= 1:
                return last
        time.sleep(1)
    return last


def cleanup(name: str) -> dict[str, Any]:
    code, out, err = run_kubectl(
        ["delete", "podchaos", name, "-n", ALLOWED_NAMESPACE, "--ignore-not-found=true"]
    )
    verify_code, verify_out, verify_err = run_kubectl(
        ["get", "podchaos", name, "-n", ALLOWED_NAMESPACE]
    )
    verify_text = (verify_out + "\n" + verify_err).lower()
    absent = verify_code != 0 and "not found" in verify_text
    residual = residual_chaos()
    return {
        "delete_code": code,
        "delete_output": (out or err).strip(),
        "absent_confirmed": absent,
        "residual_resources": residual,
    }


def event_capture_payload(raw: str, capture_since: str | None = None) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {
            "status": "unavailable",
            "error": str(exc),
            "items": [],
            "capture_since": capture_since,
        }
    if not isinstance(value, dict) or not isinstance(value.get("items"), list):
        return {
            "status": "unavailable",
            "error": "kubectl events payload is not an EventList JSON object",
            "items": [],
            "capture_since": capture_since,
        }
    return {
        "apiVersion": value.get("apiVersion", "v1"),
        "kind": value.get("kind", "EventList"),
        "status": "captured",
        "capture_since": capture_since,
        "items": value["items"],
    }


def diagnostics(report_path: Path, since_time: str) -> dict[str, Any]:
    logs: dict[str, Any] = {}
    for deployment in ("front-end", "carts", "catalogue"):
        path = report_path.with_name(f"{report_path.stem}.{deployment}.log")
        code, out, err = run_kubectl(
            [
                "logs",
                "-n",
                ALLOWED_NAMESPACE,
                f"deployment/{deployment}",
                "--since-time",
                since_time,
                "--timestamps=true",
            ],
            timeout=60,
        )
        content = out if code == 0 else f"diagnostic_unavailable: {(err or out).strip()}\n"
        path.write_text(content, encoding="utf-8")
        logs[deployment] = {
            "path": str(path.resolve()).replace("\\", "/"),
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "status": "captured" if code == 0 else "unavailable",
        }
    events_path = report_path.with_name(f"{report_path.stem}.events.json")
    code, out, err = run_kubectl(
        ["get", "events", "-n", ALLOWED_NAMESPACE, "-o", "json"],
        timeout=60,
    )
    if code == 0:
        events_payload = event_capture_payload(out, since_time)
    else:
        events_payload = {
            "status": "unavailable",
            "error": (err or out).strip(),
            "items": [],
            "capture_since": since_time,
        }
    events_content = json.dumps(events_payload, indent=2, ensure_ascii=True) + "\n"
    events_path.write_text(events_content, encoding="utf-8")
    zipkin_path = report_path.with_name(f"{report_path.stem}.zipkin.json")
    zipkin_payload = {
        "status": "unavailable",
        "reason": "Sock Shop native manifests do not deploy a tracing-server Service in this input",
        "capture_since": since_time,
        "traces": [],
    }
    zipkin_path.write_text(json.dumps(zipkin_payload, indent=2) + "\n", encoding="utf-8")
    return {
        "logs": logs,
        "events": {
            "path": str(events_path.resolve()).replace("\\", "/"),
            "sha256": hashlib.sha256(events_path.read_bytes()).hexdigest(),
            "status": "captured" if code == 0 else "unavailable",
        },
        "zipkin": {
            "path": str(zipkin_path.resolve()).replace("\\", "/"),
            "sha256": hashlib.sha256(zipkin_path.read_bytes()).hexdigest(),
            "status": "unavailable",
        },
    }


def run_experiment(
    mutation: Path,
    report_path: Path,
    method_id: str,
    replicate: int,
    *,
    washout_stable_successes: int = 10,
    washout_timeout: float = 240.0,
    capture_diagnostics_enabled: bool = True,
) -> dict[str, Any]:
    manifest = build_manifest(method_id, ALLOWED_NAMESPACE, mutation)
    report: dict[str, Any] = {
        "schema_version": "sock-shop-three-method-v1",
        "project_id": "SockShop",
        "method_id": method_id,
        "replicate": replicate,
        "namespace": ALLOWED_NAMESPACE,
        "mutation": manifest["mutation"],
        "baseline": {"pass": False, "samples": []},
        "injection": {"applied": False, "injected": False},
        "observation": {"samples": []},
        "recovery": {"recovered": False},
        "cleanup": {"absent_confirmed": False, "residual_resources": []},
        "washout": {"stable": False, "samples": []},
        "diagnostics": {},
        "human_review": "pending",
        "status": "failed",
        "started_at": now(),
        "errors": [],
    }
    process: subprocess.Popen[str] | None = None
    name = None
    since_time = report["started_at"]
    try:
        if residual_chaos():
            raise RuntimeError("global Chaos Mesh residuals exist before injection")
        health = wait_health()
        report["baseline"]["namespace_health"] = health
        if not health.get("pass"):
            raise RuntimeError("namespace health baseline failed")
        process = start_forward()
        wait_forward(process)
        for _ in range(5):
            report["baseline"]["samples"].append(request())
        report["baseline"]["pass"] = sum(
            item.get("status_code") == 200 for item in report["baseline"]["samples"]
        ) >= 3
        if not report["baseline"]["pass"]:
            raise RuntimeError("business baseline did not produce three HTTP 200 responses")
        doc = yaml.safe_load(mutation.read_text(encoding="utf-8"))
        name = str((doc.get("metadata") or {}).get("name") or "")
        if doc.get("kind") != "PodChaos" or not name:
            raise ValueError("Sock Shop three-method runner requires a named PodChaos")
        if (doc.get("metadata") or {}).get("namespace") != ALLOWED_NAMESPACE:
            raise ValueError("mutation namespace is outside Sock Shop boundary")
        code, out, err = run_kubectl(["apply", "-f", str(mutation)])
        report["apply"] = {"return_code": code, "stdout": out.strip(), "stderr": err.strip()}
        report["injection"]["applied"] = code == 0
        if code != 0:
            raise RuntimeError("kubectl apply failed")
        injected_status = wait_injected(name)
        report["injection"]["status"] = injected_status
        report["injection"]["injected"] = injected_status.get("injected_count", 0) >= 1
        if not report["injection"]["injected"]:
            raise RuntimeError("Chaos Mesh did not confirm injection")
        for _ in range(8):
            report["observation"]["samples"].append(request())
            time.sleep(0.5)
    except Exception as exc:
        report["errors"].append(str(exc))
    finally:
        stop_forward(process)
        if name:
            try:
                recovered_health = wait_health(timeout=300)
                report["recovery"] = {
                    "recovered": bool(recovered_health.get("pass")),
                    "namespace_health": recovered_health,
                }
            except Exception as exc:
                report["recovery"]["error"] = str(exc)
            try:
                report["cleanup"] = cleanup(name)
            except Exception as exc:
                report["cleanup"]["error"] = str(exc)
        if report["cleanup"].get("absent_confirmed"):
            deadline = time.monotonic() + washout_timeout
            stable = 0
            while time.monotonic() < deadline:
                try:
                    process = start_forward()
                    wait_forward(process)
                    sample = request()
                except Exception as exc:
                    sample = {"status_code": None, "error": str(exc)}
                finally:
                    stop_forward(process)
                    process = None
                report["washout"]["samples"].append(sample)
                if sample.get("status_code") == 200:
                    stable += 1
                else:
                    stable = 0
                if stable >= max(1, washout_stable_successes):
                    report["washout"]["stable"] = True
                    break
                time.sleep(1)
        if capture_diagnostics_enabled:
            try:
                report["diagnostics"] = diagnostics(report_path, since_time)
            except Exception as exc:
                report["diagnostics"] = {"error": str(exc)}
    report["comparison"] = comparison_status(report)
    report["status"] = "completed" if report["comparison"]["eligible"] else "failed"
    report["finished_at"] = now()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mutation", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--method-id", required=True, choices=METHOD_IDS)
    parser.add_argument("--replicate", type=int, required=True)
    parser.add_argument("--washout-stable-successes", type=int, default=10)
    parser.add_argument("--washout-timeout", type=float, default=240.0)
    args = parser.parse_args()
    report = run_experiment(
        args.mutation,
        args.report,
        args.method_id,
        args.replicate,
        washout_stable_successes=args.washout_stable_successes,
        washout_timeout=args.washout_timeout,
    )
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
