"""Validate the projected sock-shop prior on P02 Spring Petclinic (third migration).

Same two-arm counterfactual as the OB validation, on a different stack
(Java/Spring Cloud, gateway route -> customers-service) to test whether the
single-replica-no-PDB pod-kill prior keeps holding on a third project:

- Arm A: kill the only customers-service pod; expect a synchronized outage
  sample (gateway oracle fails while no pre-injection Ready pod serves).
- Arm B: scale customers-service to 2, repeat the kill; expect a
  surviving-UID co-proof sample.

Only the four Spring Cloud services the oracle needs are scaled up
(config-server, discovery-server, api-gateway, customers-service); the
observability stack stays parked. Everything is restored afterwards.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import yaml

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.ob_prior_validation import reduce_arm_a, reduce_arm_b, summarize_prior_validation

NAMESPACE = "chaosatlas-p02"
TARGET_DEPLOYMENT = "customers-service"
TARGET_SELECTOR = "app.kubernetes.io/name=customers-service"
GATEWAY_SERVICE = "api-gateway"
GATEWAY_PORT = 8080
BUSINESS_PATH = "/api/gateway/owners/1"
LOCAL_PORT = 18095
TARGET_REPLICAS = 2
ARM_DURATION_S = 45.0
INTERVAL_S = 0.5
NEEDED_DEPLOYMENTS = ["config-server", "discovery-server", "api-gateway", "customers-service"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _kubectl(args: list[str], *, input_text: str | None = None, timeout: int = 30) -> tuple[int, str, str]:
    completed = subprocess.run(
        ["kubectl", *args], input=input_text, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout, check=False)
    return completed.returncode, completed.stdout or "", completed.stderr or ""


def _kubectl_json(args: list[str]) -> dict[str, Any]:
    code, stdout, stderr = _kubectl([*args, "-o", "json"])
    if code != 0:
        raise RuntimeError(f"kubectl {' '.join(args)} failed: {(stderr or stdout).strip() or code}")
    value = json.loads(stdout)
    if not isinstance(value, dict):
        raise RuntimeError(f"kubectl {' '.join(args)} returned non-object JSON")
    return value


def _ready_pods(pods: dict[str, Any]) -> list[dict[str, Any]]:
    ready = []
    for pod in pods.get("items") or []:
        conditions = ((pod.get("status") or {}).get("conditions") or [])
        if any(isinstance(c, dict) and c.get("type") == "Ready" and c.get("status") == "True" for c in conditions):
            ready.append(pod)
    return ready


def _pod_uid(pod: dict[str, Any]) -> str:
    return str((pod.get("metadata") or {}).get("uid") or "")


def _wait_until(predicate, *, timeout: float, description: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(3.0)
    raise RuntimeError(f"timed out waiting for {description}")


def _business_sample() -> dict[str, Any]:
    observed_at = _now()
    try:
        with urlopen(f"http://127.0.0.1:{LOCAL_PORT}{BUSINESS_PATH}", timeout=4.0) as response:
            body = response.read(512)
            return {"observed_at": observed_at, "status_code": response.status,
                    "contract_ok": response.status == 200 and bool(body)}
    except HTTPError as exc:
        return {"observed_at": observed_at, "status_code": exc.code, "error": "HTTPError", "contract_ok": False}
    except (OSError, URLError, TimeoutError) as exc:
        return {"observed_at": observed_at, "status_code": None, "error": type(exc).__name__, "contract_ok": False}


def _capture_sample() -> dict[str, Any]:
    business = _business_sample()
    pods = _kubectl_json(["get", "pods", "-n", NAMESPACE, "-l", TARGET_SELECTOR])
    endpoints = _kubectl_json(["get", "endpoints", TARGET_DEPLOYMENT, "-n", NAMESPACE])
    return {"observed_at": business["observed_at"], "business": business, "pods": pods, "endpoints": endpoints}


def _podchaos_manifest(name: str, pod_name: str) -> str:
    manifest = {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "PodChaos",
        "metadata": {"name": name, "namespace": NAMESPACE,
                     "labels": {"chaosatlas.dev/owner": "chaosatlas", "chaosatlas.dev/pilot": "p02-prior-validation"}},
        "spec": {"action": "pod-kill", "mode": "one", "selector": {"pods": {NAMESPACE: [pod_name]}}},
    }
    return yaml.safe_dump(manifest, sort_keys=False, allow_unicode=False)


def _apply_and_confirm(name: str, manifest_text: str) -> dict[str, Any]:
    code, stdout, stderr = _kubectl(["apply", "-f", "-"], input_text=manifest_text)
    if code != 0:
        raise RuntimeError(f"PodChaos apply failed: {(stderr or stdout).strip() or code}")
    for _ in range(60):
        status = _kubectl_json(["get", "podchaos", name, "-n", NAMESPACE])
        conditions = (status.get("status") or {}).get("conditions") or []
        if any(isinstance(c, dict) and c.get("type") == "AllInjected" and c.get("status") == "True" for c in conditions):
            return status
        time.sleep(0.5)
    raise RuntimeError("PodChaos injection was not confirmed within the bounded gate")


def _sample_window(stream, duration: float) -> list[dict[str, Any]]:
    samples = []
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        sample = _capture_sample()
        samples.append(sample)
        stream.write(json.dumps(sample, ensure_ascii=True, sort_keys=True) + "\n")
        stream.flush()
        time.sleep(INTERVAL_S)
    return samples


def _delete_podchaos(name: str) -> list[str]:
    errors: list[str] = []
    code, stdout, stderr = _kubectl(["delete", "podchaos", name, "-n", NAMESPACE, "--ignore-not-found=true"])
    if code != 0:
        errors.append((stderr or stdout).strip() or f"delete returned {code}")
    else:
        try:
            _wait_until(lambda: _kubectl(["get", "podchaos", name, "-n", NAMESPACE])[0] != 0,
                        timeout=30.0, description=f"PodChaos {name} cleanup")
        except RuntimeError as exc:
            errors.append(str(exc))
    return errors


def _wait_port(process: subprocess.Popen, timeout: float = 20.0) -> None:
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


def _write(output: Path, name: str, value: Any) -> None:
    (output / name).write_text(json.dumps(value, indent=2, ensure_ascii=True, sort_keys=True) + "\n", encoding="utf-8")


def run(output: Path) -> dict[str, Any]:
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output {output} is not empty")
    output.mkdir(parents=True, exist_ok=True)

    cleanup_errors: list[str] = []
    run_error: str | None = None
    original_replicas: dict[str, int] = {}
    port_forward = None
    arm_a_samples: list[dict[str, Any]] = []
    arm_b_samples: list[dict[str, Any]] = []
    arm_a_killed = ""
    arm_b_killed = ""
    restored_replicas: int | None = None
    mutation_names = {"arm_a": "chaosatlas-p02-prior-arm-a", "arm_b": "chaosatlas-p02-prior-arm-b"}
    applied: set[str] = set()
    try:
        code, _, _ = _kubectl(["get", "podchaos", "-A"])
        if code == 0 and _kubectl_json(["get", "podchaos", "-A"]).get("items"):
            raise RuntimeError("global PodChaos residue present; refusing to run")
        for name in NEEDED_DEPLOYMENTS:
            deployment = _kubectl_json(["get", "deployment", name, "-n", NAMESPACE])
            original_replicas[name] = int((deployment.get("spec") or {}).get("replicas", 0))
            if original_replicas[name] == 0:
                code, stdout, stderr = _kubectl(["scale", f"deployment/{name}", "--replicas=1", "-n", NAMESPACE])
                if code != 0:
                    raise RuntimeError(f"scale up {name} failed: {(stderr or stdout).strip() or code}")

        def needed_ready() -> bool:
            for name in NEEDED_DEPLOYMENTS:
                selector = f"app.kubernetes.io/name={name}"
                pods = _kubectl_json(["get", "pods", "-n", NAMESPACE, "-l", selector])
                if not _ready_pods(pods):
                    return False
            return True

        _wait_until(needed_ready, timeout=600.0, description="needed P02 deployments Ready")
        _write(output, "namespace_before.json", {"captured_at": _now(), "original_replicas": original_replicas})

        port_forward = subprocess.Popen(
            ["kubectl", "port-forward", f"svc/{GATEWAY_SERVICE}", f"{LOCAL_PORT}:{GATEWAY_PORT}", "-n", NAMESPACE],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        _wait_port(port_forward)
        baseline: list[dict[str, Any]] = []
        consecutive = 0
        deadline = time.monotonic() + 1800.0  # cold Spring Cloud stack can take ~30 min before the gateway route resolves
        while time.monotonic() < deadline and consecutive < 3:
            sample = _business_sample()
            baseline.append(sample)
            consecutive = consecutive + 1 if sample["contract_ok"] else 0
            if not sample["contract_ok"]:
                time.sleep(5.0)
        if consecutive < 3:
            raise RuntimeError(f"business oracle baseline failed: {baseline[-5:]}")
        _write(output, "baseline.json", baseline)

        # Arm A
        pods = _kubectl_json(["get", "pods", "-n", NAMESPACE, "-l", TARGET_SELECTOR])
        ready = _ready_pods(pods)
        if len(ready) != 1:
            raise RuntimeError(f"arm A expects one Ready target pod, found {len(ready)}")
        arm_a_killed = _pod_uid(ready[0])
        status_a = _apply_and_confirm(mutation_names["arm_a"], _podchaos_manifest(mutation_names["arm_a"], ready[0]["metadata"]["name"]))
        applied.add("arm_a")
        _write(output, "arm_a_injection_status.json", status_a)
        with (output / "arm_a_timeline.jsonl").open("w", encoding="utf-8") as stream:
            arm_a_samples = _sample_window(stream, ARM_DURATION_S)
        cleanup_errors += _delete_podchaos(mutation_names["arm_a"])
        applied.discard("arm_a")
        _wait_until(lambda: len(_ready_pods(_kubectl_json(["get", "pods", "-n", NAMESPACE, "-l", TARGET_SELECTOR]))) >= 1,
                    timeout=300.0, description="arm A target recovery")
        _wait_until(lambda: _business_sample()["contract_ok"], timeout=300.0, description="arm A business recovery")

        # Arm B
        code, stdout, stderr = _kubectl(["scale", f"deployment/{TARGET_DEPLOYMENT}", f"--replicas={TARGET_REPLICAS}", "-n", NAMESPACE])
        if code != 0:
            raise RuntimeError(f"arm B scale up failed: {(stderr or stdout).strip() or code}")
        _wait_until(lambda: len(_ready_pods(_kubectl_json(["get", "pods", "-n", NAMESPACE, "-l", TARGET_SELECTOR]))) >= TARGET_REPLICAS,
                    timeout=420.0, description="two Ready target pods")
        pods = _kubectl_json(["get", "pods", "-n", NAMESPACE, "-l", TARGET_SELECTOR])
        victim = sorted(_ready_pods(pods), key=lambda p: p["metadata"]["name"])[0]
        arm_b_killed = _pod_uid(victim)
        status_b = _apply_and_confirm(mutation_names["arm_b"], _podchaos_manifest(mutation_names["arm_b"], victim["metadata"]["name"]))
        applied.add("arm_b")
        _write(output, "arm_b_injection_status.json", status_b)
        with (output / "arm_b_timeline.jsonl").open("w", encoding="utf-8") as stream:
            arm_b_samples = _sample_window(stream, ARM_DURATION_S)
        cleanup_errors += _delete_podchaos(mutation_names["arm_b"])
        applied.discard("arm_b")
    except Exception as exc:
        run_error = f"{type(exc).__name__}: {exc}"
    finally:
        for arm in sorted(applied):
            cleanup_errors += _delete_podchaos(mutation_names[arm])
        if port_forward is not None and port_forward.poll() is None:
            port_forward.terminate()
            try:
                port_forward.wait(timeout=5)
            except subprocess.TimeoutExpired:
                port_forward.kill()
        for name, replicas in original_replicas.items():
            if name != TARGET_DEPLOYMENT and replicas == 0:
                code, _, stderr = _kubectl(["scale", f"deployment/{name}", "--replicas=0", "-n", NAMESPACE])
                if code != 0:
                    cleanup_errors.append(f"restore {name}: {(stderr or '').strip()}")
        code, _, stderr = _kubectl(["scale", f"deployment/{TARGET_DEPLOYMENT}", "--replicas=1", "-n", NAMESPACE])
        if code != 0:
            cleanup_errors.append(f"restore target: {(stderr or '').strip()}")
        try:
            restored = _kubectl_json(["get", "deployment", TARGET_DEPLOYMENT, "-n", NAMESPACE])
            restored_replicas = int((restored.get("spec") or {}).get("replicas", -1))
        except Exception as exc:
            cleanup_errors.append(f"after snapshot: {type(exc).__name__}: {exc}")
        residual = []
        try:
            residual = _kubectl_json(["get", "podchaos", "-A"]).get("items") or []
        except Exception as exc:
            cleanup_errors.append(f"residual audit: {type(exc).__name__}: {exc}")

    arm_a = reduce_arm_a(arm_a_samples, {arm_a_killed} if arm_a_killed else set())
    arm_b = reduce_arm_b(arm_b_samples, arm_b_killed)
    summary = summarize_prior_validation(
        arm_a=arm_a, arm_b=arm_b,
        cleanup_ok=not cleanup_errors and run_error is None,
        restored_replicas=restored_replicas,
        residual_chaos_count=len(residual))
    result = {
        "schema_version": "chaosatlas-p02-prior-validation-v1",
        "round_id": "cross-project-r1-p02-validation",
        "namespace": NAMESPACE,
        "target": f"deployment:{TARGET_DEPLOYMENT}",
        "oracle": f"api-gateway {BUSINESS_PATH}",
        "arm_a_killed_uid": arm_a_killed,
        "arm_b_killed_uid": arm_b_killed,
        "arm_a": arm_a, "arm_b": arm_b,
        "run_error": run_error, "cleanup_errors": cleanup_errors,
        "restored_replicas": restored_replicas,
        "residual_podchaos": residual,
        "summary": summary,
    }
    _write(output, "result.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output)
    print(json.dumps(result["summary"], indent=2, ensure_ascii=True))
    return 0 if result["summary"]["verdict"] == "prior_validated" else 1


if __name__ == "__main__":
    raise SystemExit(main())
