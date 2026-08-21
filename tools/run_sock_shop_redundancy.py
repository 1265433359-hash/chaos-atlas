"""Run a recoverable two-replica Sock Shop front-end PodKill control."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import urlopen

import yaml

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.sock_shop_redundancy import summarize_redundancy_timeline


NAMESPACE = "sock-shop-lab"
SERVICE = "front-end"
DEPLOYMENT = "front-end"
SELECTOR = "name=front-end"
LOCAL_PORT = 18089
TARGET_REPLICAS = 2
MAX_DURATION_S = 30.0
INTERVAL_S = 0.5


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _kubectl(args: list[str], *, input_text: str | None = None, timeout: int = 20) -> tuple[int, str, str]:
    completed = subprocess.run(
        ["kubectl", *args],
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    return completed.returncode, completed.stdout or "", completed.stderr or ""


def _kubectl_json(args: list[str]) -> dict[str, Any]:
    code, stdout, stderr = _kubectl([*args, "-o", "json"])
    if code != 0:
        raise RuntimeError(f"kubectl {' '.join(args)} failed: {(stderr or stdout).strip() or code}")
    value = json.loads(stdout)
    if not isinstance(value, dict):
        raise RuntimeError(f"kubectl {' '.join(args)} returned a non-object JSON value")
    return value


def _items(value: dict[str, Any]) -> list[dict[str, Any]]:
    items = value.get("items")
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _pod_uid(pod: dict[str, Any]) -> str | None:
    value = (pod.get("metadata") or {}).get("uid")
    return str(value) if value else None


def _pod_ready(pod: dict[str, Any]) -> bool:
    return any(
        isinstance(condition, dict)
        and condition.get("type") == "Ready"
        and condition.get("status") == "True"
        for condition in ((pod.get("status") or {}).get("conditions") or [])
    )


def _ready_pods(pods: dict[str, Any]) -> list[dict[str, Any]]:
    return [pod for pod in _items(pods) if _pod_uid(pod) and _pod_ready(pod)]


def _wait_until(predicate: Callable[[], bool], *, timeout: float, description: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.5)
    raise RuntimeError(f"timed out waiting for {description}")


def _business_sample() -> dict[str, Any]:
    observed_at = _now()
    try:
        with urlopen(f"http://127.0.0.1:{LOCAL_PORT}/", timeout=2.0) as response:
            body = response.read(256)
            return {
                "observed_at": observed_at,
                "status_code": response.status,
                "contract_ok": response.status == 200 and bool(body),
            }
    except (OSError, URLError, TimeoutError) as exc:
        return {"observed_at": observed_at, "status_code": None, "error": type(exc).__name__, "contract_ok": False}


def _capture_sample() -> dict[str, Any]:
    business = _business_sample()
    pods = _kubectl_json(["get", "pods", "-n", NAMESPACE, "-l", SELECTOR])
    endpoints = _kubectl_json(["get", "endpoints", SERVICE, "-n", NAMESPACE])
    return {"observed_at": business["observed_at"], "business": business, "pods": pods, "endpoints": endpoints}


def _wait_port(process: subprocess.Popen[str], timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("kubectl port-forward exited before becoming ready")
        try:
            with socket.create_connection(("127.0.0.1", LOCAL_PORT), timeout=0.5):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("port-forward did not become ready")


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True, sort_keys=True) + "\n", encoding="utf-8")


def run(output: Path, *, max_duration_s: float = MAX_DURATION_S, interval_s: float = INTERVAL_S) -> dict[str, Any]:
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output {output} is not empty")
    output.mkdir(parents=True, exist_ok=True)
    scale_events: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    injection_status: dict[str, Any] = {}
    mutation_name = "chaosatlas-sock-shop-front-end-podkill-redundancy-r1"
    killed_uid = ""
    original_replicas: int | None = None
    scaled = False
    mutation_applied = False
    cleanup_errors: list[str] = []
    port_forward: subprocess.Popen[str] | None = None
    run_error: str | None = None

    try:
        deployment = _kubectl_json(["get", "deployment", DEPLOYMENT, "-n", NAMESPACE])
        original_replicas = int((deployment.get("spec") or {}).get("replicas", 1))
        before = {
            "captured_at": _now(),
            "deployment": deployment,
            "pods": _kubectl_json(["get", "pods", "-n", NAMESPACE, "-l", SELECTOR]),
            "endpoints": _kubectl_json(["get", "endpoints", SERVICE, "-n", NAMESPACE]),
        }
        _write_json(output / "before.json", before)
        if original_replicas != 1:
            raise RuntimeError(f"expected singleton baseline replicas=1, found {original_replicas}")
        baseline_ready = _ready_pods(before["pods"])
        if len(baseline_ready) != 1:
            raise RuntimeError(f"expected one baseline Ready Pod, found {len(baseline_ready)}")
        killed_pod_name = str((baseline_ready[0].get("metadata") or {}).get("name"))
        killed_uid = str(_pod_uid(baseline_ready[0]))

        code, stdout, stderr = _kubectl(["scale", f"deployment/{DEPLOYMENT}", f"--replicas={TARGET_REPLICAS}", "-n", NAMESPACE])
        if code != 0:
            raise RuntimeError(f"scale up failed: {(stderr or stdout).strip() or code}")
        scaled = True
        scale_events.append({"at": _now(), "operation": "scale_up", "from": original_replicas, "to": TARGET_REPLICAS})

        def two_ready() -> bool:
            pods = _kubectl_json(["get", "pods", "-n", NAMESPACE, "-l", SELECTOR])
            return len(_ready_pods(pods)) >= TARGET_REPLICAS

        _wait_until(two_ready, timeout=60.0, description="two Ready front-end Pods")
        port_forward = subprocess.Popen(
            ["kubectl", "port-forward", f"svc/{SERVICE}", f"{LOCAL_PORT}:80", "-n", NAMESPACE],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        _wait_port(port_forward)

        mutation = yaml.safe_load(Path("artifacts/sock-shop/pilot/front-end-podkill-r1/mutation.yaml").read_text(encoding="utf-8"))
        mutation["metadata"]["name"] = mutation_name
        mutation["metadata"].setdefault("labels", {})["chaosatlas.dev/pilot"] = "sock-shop-front-end-redundancy-r1"
        mutation["spec"]["selector"] = {"pods": {NAMESPACE: [killed_pod_name]}}
        mutation_text = yaml.safe_dump(mutation, sort_keys=False, allow_unicode=False)
        (output / "mutation.yaml").write_text(mutation_text, encoding="utf-8")
        code, stdout, stderr = _kubectl(["apply", "-f", "-"], input_text=mutation_text)
        if code != 0:
            raise RuntimeError(f"PodChaos apply failed: {(stderr or stdout).strip() or code}")
        mutation_applied = True
        for _ in range(30):
            injection_status = _kubectl_json(["get", "podchaos", mutation_name, "-n", NAMESPACE])
            conditions = (injection_status.get("status") or {}).get("conditions") or []
            if any(isinstance(item, dict) and item.get("type") == "AllInjected" and item.get("status") == "True" for item in conditions):
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("PodChaos injection was not confirmed within the bounded gate")
        with (output / "timeline.jsonl").open("w", encoding="utf-8") as stream:
            deadline = time.monotonic() + max_duration_s
            while time.monotonic() < deadline:
                sample = _capture_sample()
                samples.append(sample)
                stream.write(json.dumps(sample, ensure_ascii=True, sort_keys=True) + "\n")
                stream.flush()
                time.sleep(interval_s)
    except Exception as exc:
        run_error = f"{type(exc).__name__}: {exc}"
    finally:
        if mutation_applied:
            code, stdout, stderr = _kubectl(["delete", "podchaos", mutation_name, "-n", NAMESPACE, "--ignore-not-found=true"])
            if code != 0:
                cleanup_errors.append((stderr or stdout).strip() or f"delete returned {code}")
            try:
                _wait_until(
                    lambda: _kubectl(["get", "podchaos", mutation_name, "-n", NAMESPACE])[0] != 0,
                    timeout=20.0,
                    description="PodChaos cleanup",
                )
            except RuntimeError as exc:
                cleanup_errors.append(str(exc))
        if port_forward is not None and port_forward.poll() is None:
            port_forward.terminate()
            try:
                port_forward.wait(timeout=5)
            except subprocess.TimeoutExpired:
                port_forward.kill()
        if port_forward is not None:
            (output / "port-forward.txt").write_text(
                (port_forward.stdout.read() if port_forward.stdout else "") + (port_forward.stderr.read() if port_forward.stderr else ""),
                encoding="utf-8",
            )
        if scaled and original_replicas is not None:
            code, stdout, stderr = _kubectl(["scale", f"deployment/{DEPLOYMENT}", f"--replicas={original_replicas}", "-n", NAMESPACE])
            if code != 0:
                cleanup_errors.append((stderr or stdout).strip() or f"scale restore returned {code}")
            else:
                scale_events.append({"at": _now(), "operation": "scale_restore", "from": TARGET_REPLICAS, "to": original_replicas})
                try:
                    _wait_until(
                        lambda: len(_ready_pods(_kubectl_json(["get", "pods", "-n", NAMESPACE, "-l", SELECTOR]))) >= original_replicas,
                        timeout=60.0,
                        description="restored Ready front-end replicas",
                    )
                except RuntimeError as exc:
                    cleanup_errors.append(str(exc))
    _write_json(output / "scale_events.json", scale_events)
    try:
        after = {"captured_at": _now(), "deployment": _kubectl_json(["get", "deployment", DEPLOYMENT, "-n", NAMESPACE]), "pods": _kubectl_json(["get", "pods", "-n", NAMESPACE, "-l", SELECTOR]), "endpoints": _kubectl_json(["get", "endpoints", SERVICE, "-n", NAMESPACE])}
        _write_json(output / "after.json", after)
    except Exception as exc:
        cleanup_errors.append(f"after snapshot: {type(exc).__name__}: {exc}")
    residual = []
    code, stdout, _ = _kubectl(["get", "podchaos", "-n", NAMESPACE])
    if code == 0:
        try:
            residual = _items(_kubectl_json(["get", "podchaos", "-n", NAMESPACE]))
        except Exception as exc:
            cleanup_errors.append(f"residual snapshot: {type(exc).__name__}: {exc}")
    summary = summarize_redundancy_timeline(pod_before=before.get("pods", {}), samples=samples, killed_uid=killed_uid) if before else {"classification": "observation_inconclusive", "deterministic": False, "sample_count": 0, "reason": "baseline was not captured"}
    result = {
        "schema_version": "chaosatlas-sock-shop-redundancy-runtime-v1",
        "round_id": "pilot-r4-redundancy-r1",
        "namespace": NAMESPACE,
        "target": "deployment:front-end",
        "original_replicas": original_replicas,
        "target_replicas": TARGET_REPLICAS,
        "killed_uid": killed_uid,
        "mutation_name": mutation_name,
        "sample_count": len(samples),
        "summary": summary,
        "run_error": run_error,
        "cleanup_error": "; ".join(cleanup_errors) if cleanup_errors else None,
        "residual_podchaos": residual,
        "restored_replicas": ((after.get("deployment") or {}).get("spec") or {}).get("replicas") if after else None,
        "scale_events": scale_events,
    }
    _write_json(output / "result.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output), indent=2, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
