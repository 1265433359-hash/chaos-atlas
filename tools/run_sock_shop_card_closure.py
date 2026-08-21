"""Close the two provisional Sock Shop RCA cards with live evidence (cluster).

card=catalogue-db (KB-RCA-sock-shop-catalogue-catalogue-db-podchaos-pod-kill):
two arms, same reducers as the OB prior validation. Arm A kills the only
catalogue-db pod and requires a synchronized outage sample (business fails
while no pre-injection Ready pod is serving). Arm B scales catalogue-db to 2
(mongo self-seeds each replica at startup), repeats the kill and requires a
surviving-UID co-proof. Outcome decides the card disposition honestly:
defended arm B supports the same redundancy mechanism as the front-end card;
a failing arm B would refine the knowledge (naive scale-out of a stateful
singleton without replication is NOT a defense) instead of being forced.

card=http-abort (KB-RCA-sock-shop-front-end-catalogue-httpchaos-abort):
single confirmation arm. HTTPChaos Response abort on catalogue (port 80,
path /catalogue) — the front-end->catalogue edge from the card. Business
failures during confirmed injection confirm the transport-abort propagation;
all-200 would mean the edge degrades gracefully and the card stays bounded.
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

from tools.ob_prior_validation import reduce_arm_a, reduce_arm_b

NAMESPACE = "chaosatlas-sock-shop"
FRONTEND_SERVICE = "front-end"
FRONTEND_PORT = 80
LOCAL_PORT = 18093
ARM_DURATION_S = 40.0
INTERVAL_S = 0.5
DB_DEPLOYMENT = "catalogue-db"
DB_SELECTOR = "name=catalogue-db"
DB_SERVICE = "catalogue-db"


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


def _wait_until(predicate, *, timeout: float, description: str, interval: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise RuntimeError(f"timed out waiting for {description}")


def _business_sample() -> dict[str, Any]:
    """Catalogue oracle: front-end /catalogue JSON must be a non-empty product list.

    The plain '/' page renders (HTTP 200) even when the catalogue chain is
    broken, so the home page cannot detect this card's outage; the JSON route
    traverses front-end -> catalogue -> catalogue-db.
    """
    observed_at = _now()
    try:
        with urlopen(f"http://127.0.0.1:{LOCAL_PORT}/catalogue", timeout=3.0) as response:
            body = response.read(2048)
            return {"observed_at": observed_at, "status_code": response.status,
                    "contract_ok": response.status == 200 and b'"name"' in body}
    except HTTPError as exc:
        return {"observed_at": observed_at, "status_code": exc.code, "error": "HTTPError", "contract_ok": False}
    except (OSError, URLError, TimeoutError) as exc:
        return {"observed_at": observed_at, "status_code": None, "error": type(exc).__name__, "contract_ok": False}


def _podchaos_manifest(name: str, pod_name: str) -> str:
    manifest = {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "PodChaos",
        "metadata": {"name": name, "namespace": NAMESPACE,
                     "labels": {"chaosatlas.dev/owner": "chaosatlas", "chaosatlas.dev/pilot": "card-closure"}},
        "spec": {"action": "pod-kill", "mode": "one", "selector": {"pods": {NAMESPACE: [pod_name]}}},
    }
    return yaml.safe_dump(manifest, sort_keys=False, allow_unicode=False)


def _httpchaos_manifest(name: str) -> str:
    manifest = {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "HTTPChaos",
        "metadata": {"name": name, "namespace": NAMESPACE,
                     "labels": {"chaosatlas.dev/owner": "chaosatlas", "chaosatlas.dev/pilot": "card-closure"}},
        "spec": {
            "mode": "one",
            "selector": {"namespaces": [NAMESPACE], "labelSelectors": {"name": "catalogue"}},
            "target": "Response", "abort": True, "port": 80, "path": "/catalogue", "duration": "45s",
        },
    }
    return yaml.safe_dump(manifest, sort_keys=False, allow_unicode=False)


def _apply_and_confirm(kind: str, name: str, manifest_text: str) -> dict[str, Any]:
    code, stdout, stderr = _kubectl(["apply", "-f", "-"], input_text=manifest_text)
    if code != 0:
        raise RuntimeError(f"{kind} apply failed: {(stderr or stdout).strip() or code}")
    for _ in range(60):
        status = _kubectl_json(["get", kind.lower(), name, "-n", NAMESPACE])
        conditions = (status.get("status") or {}).get("conditions") or []
        if any(isinstance(c, dict) and c.get("type") == "AllInjected" and c.get("status") == "True" for c in conditions):
            return status
        time.sleep(0.5)
    raise RuntimeError(f"{kind} injection was not confirmed within the bounded gate")


def _delete(kind: str, name: str) -> list[str]:
    errors: list[str] = []
    code, stdout, stderr = _kubectl(["delete", kind.lower(), name, "-n", NAMESPACE, "--ignore-not-found=true"])
    if code != 0:
        errors.append((stderr or stdout).strip() or f"delete returned {code}")
    else:
        try:
            _wait_until(lambda: _kubectl(["get", kind.lower(), name, "-n", NAMESPACE])[0] != 0,
                        timeout=30.0, description=f"{kind} {name} cleanup")
        except RuntimeError as exc:
            errors.append(str(exc))
    return errors


def _sample_db(stream, duration: float) -> list[dict[str, Any]]:
    samples = []
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        business = _business_sample()
        pods = _kubectl_json(["get", "pods", "-n", NAMESPACE, "-l", DB_SELECTOR])
        endpoints = _kubectl_json(["get", "endpoints", DB_SERVICE, "-n", NAMESPACE])
        sample = {"observed_at": business["observed_at"], "business": business, "pods": pods, "endpoints": endpoints}
        samples.append(sample)
        stream.write(json.dumps(sample, ensure_ascii=True, sort_keys=True) + "\n")
        stream.flush()
        time.sleep(INTERVAL_S)
    return samples


def _sample_business(stream, duration: float) -> list[dict[str, Any]]:
    samples = []
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        business = _business_sample()
        sample = {"observed_at": business["observed_at"], "business": business}
        samples.append(sample)
        stream.write(json.dumps(sample, ensure_ascii=True, sort_keys=True) + "\n")
        stream.flush()
        time.sleep(INTERVAL_S)
    return samples


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


def close_catalogue_db(output: Path) -> dict[str, Any]:
    port_forward = None
    cleanup_errors: list[str] = []
    run_error: str | None = None
    arm_a_samples: list[dict[str, Any]] = []
    arm_b_samples: list[dict[str, Any]] = []
    arm_a_killed = ""
    arm_b_killed = ""
    mutation_a = "chaosatlas-card-closure-db-arm-a"
    mutation_b = "chaosatlas-card-closure-db-arm-b"
    applied: set[str] = set()
    original_replicas = 1
    try:
        deployment = _kubectl_json(["get", "deployment", DB_DEPLOYMENT, "-n", NAMESPACE])
        original_replicas = int((deployment.get("spec") or {}).get("replicas", 1))
        if original_replicas != 1:
            raise RuntimeError(f"expected singleton catalogue-db, found replicas={original_replicas}")
        port_forward = subprocess.Popen(
            ["kubectl", "port-forward", f"svc/{FRONTEND_SERVICE}", f"{LOCAL_PORT}:{FRONTEND_PORT}", "-n", NAMESPACE],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        _wait_port(port_forward)
        baseline = [_business_sample() for _ in range(3)]
        if not all(s["contract_ok"] for s in baseline):
            raise RuntimeError(f"business baseline failed: {baseline}")

        pods = _kubectl_json(["get", "pods", "-n", NAMESPACE, "-l", DB_SELECTOR])
        ready = _ready_pods(pods)
        if len(ready) != 1:
            raise RuntimeError(f"arm A expects one Ready catalogue-db pod, found {len(ready)}")
        arm_a_killed = _pod_uid(ready[0])
        status_a = _apply_and_confirm("PodChaos", mutation_a, _podchaos_manifest(mutation_a, ready[0]["metadata"]["name"]))
        applied.add(mutation_a)
        _write(output, "arm_a_injection_status.json", status_a)
        with (output / "arm_a_timeline.jsonl").open("w", encoding="utf-8") as stream:
            arm_a_samples = _sample_db(stream, ARM_DURATION_S)
        cleanup_errors += _delete("PodChaos", mutation_a)
        applied.discard(mutation_a)
        _wait_until(lambda: len(_ready_pods(_kubectl_json(["get", "pods", "-n", NAMESPACE, "-l", DB_SELECTOR]))) >= 1,
                    timeout=180.0, description="arm A catalogue-db recovery")
        _wait_until(lambda: _business_sample()["contract_ok"], timeout=180.0, description="arm A business recovery")

        code, stdout, stderr = _kubectl(["scale", f"deployment/{DB_DEPLOYMENT}", "--replicas=2", "-n", NAMESPACE])
        if code != 0:
            raise RuntimeError(f"arm B scale up failed: {(stderr or stdout).strip() or code}")
        _wait_until(lambda: len(_ready_pods(_kubectl_json(["get", "pods", "-n", NAMESPACE, "-l", DB_SELECTOR]))) >= 2,
                    timeout=240.0, description="two Ready catalogue-db pods")
        pods = _kubectl_json(["get", "pods", "-n", NAMESPACE, "-l", DB_SELECTOR])
        victim = sorted(_ready_pods(pods), key=lambda p: p["metadata"]["name"])[0]
        arm_b_killed = _pod_uid(victim)
        status_b = _apply_and_confirm("PodChaos", mutation_b, _podchaos_manifest(mutation_b, victim["metadata"]["name"]))
        applied.add(mutation_b)
        _write(output, "arm_b_injection_status.json", status_b)
        with (output / "arm_b_timeline.jsonl").open("w", encoding="utf-8") as stream:
            arm_b_samples = _sample_db(stream, ARM_DURATION_S)
        cleanup_errors += _delete("PodChaos", mutation_b)
        applied.discard(mutation_b)
    except Exception as exc:
        run_error = f"{type(exc).__name__}: {exc}"
    finally:
        for name in sorted(applied):
            cleanup_errors += _delete("PodChaos", name)
        if port_forward is not None and port_forward.poll() is None:
            port_forward.terminate()
            try:
                port_forward.wait(timeout=5)
            except subprocess.TimeoutExpired:
                port_forward.kill()
        code, _, stderr = _kubectl(["scale", f"deployment/{DB_DEPLOYMENT}", f"--replicas={original_replicas}", "-n", NAMESPACE])
        if code != 0:
            cleanup_errors.append(f"replica restore: {(stderr or '').strip()}")
        try:
            _wait_until(lambda: len(_ready_pods(_kubectl_json(["get", "pods", "-n", NAMESPACE, "-l", DB_SELECTOR]))) == original_replicas,
                        timeout=240.0, description="restored catalogue-db replicas")
        except RuntimeError as exc:
            cleanup_errors.append(str(exc))
        residual = _kubectl_json(["get", "podchaos", "-A"]).get("items") or []
        restored = _kubectl_json(["get", "deployment", DB_DEPLOYMENT, "-n", NAMESPACE])
        restored_replicas = int((restored.get("spec") or {}).get("replicas", -1))

    arm_a = reduce_arm_a(arm_a_samples, {arm_a_killed} if arm_a_killed else set())
    arm_b = reduce_arm_b(arm_b_samples, arm_b_killed)
    lifecycle_ok = not cleanup_errors and run_error is None and restored_replicas == original_replicas and not residual
    if arm_a["classification"] == "weakness_reproduced" and arm_b["classification"] == "defended" and lifecycle_ok:
        disposition = "redundancy_mechanism_confirmed"
        note = "stateful singleton outage reproduced; two-replica counterfactual defended (self-seeding replicas)"
    elif arm_a["classification"] == "weakness_reproduced" and lifecycle_ok:
        disposition = "naive_scale_out_not_a_defense"
        note = "singleton outage reproduced, but the two-replica counterfactual did NOT prove surviving-replica service; scaling without replication is not a defense"
    else:
        disposition = "inconclusive"
        note = "arms or lifecycle did not close; card stays provisional"
    result = {
        "schema_version": "chaosatlas-sock-shop-card-closure-v1",
        "card": "KB-RCA-sock-shop-catalogue-catalogue-db-podchaos-pod-kill",
        "round_id": "card-closure-catalogue-db-r1",
        "namespace": NAMESPACE,
        "target": f"deployment:{DB_DEPLOYMENT}",
        "oracle": f"front-end GET /catalogue (via {FRONTEND_SERVICE}:{FRONTEND_PORT})",
        "arm_a": arm_a, "arm_b": arm_b,
        "arm_a_killed_uid": arm_a_killed, "arm_b_killed_uid": arm_b_killed,
        "run_error": run_error, "cleanup_errors": cleanup_errors,
        "restored_replicas": restored_replicas,
        "residual_podchaos": residual,
        "disposition": disposition, "note": note,
    }
    _write(output, "result.json", result)
    return result


def close_http_abort(output: Path) -> dict[str, Any]:
    port_forward = None
    cleanup_errors: list[str] = []
    run_error: str | None = None
    samples: list[dict[str, Any]] = []
    mutation = "chaosatlas-card-closure-abort"
    applied = False
    try:
        port_forward = subprocess.Popen(
            ["kubectl", "port-forward", f"svc/{FRONTEND_SERVICE}", f"{LOCAL_PORT}:{FRONTEND_PORT}", "-n", NAMESPACE],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        _wait_port(port_forward)
        baseline = [_business_sample() for _ in range(3)]
        if not all(s["contract_ok"] for s in baseline):
            raise RuntimeError(f"business baseline failed: {baseline}")
        status = _apply_and_confirm("HTTPChaos", mutation, _httpchaos_manifest(mutation))
        applied = True
        _write(output, "injection_status.json", status)
        with (output / "timeline.jsonl").open("w", encoding="utf-8") as stream:
            samples = _sample_business(stream, ARM_DURATION_S)
        cleanup_errors += _delete("HTTPChaos", mutation)
        applied = False
        _wait_until(lambda: _business_sample()["contract_ok"], timeout=60.0, description="post-abort business recovery")
    except Exception as exc:
        run_error = f"{type(exc).__name__}: {exc}"
    finally:
        if applied:
            cleanup_errors += _delete("HTTPChaos", mutation)
        if port_forward is not None and port_forward.poll() is None:
            port_forward.terminate()
            try:
                port_forward.wait(timeout=5)
            except subprocess.TimeoutExpired:
                port_forward.kill()
        residual = _kubectl_json(["get", "httpchaos", "-A"]).get("items") or []

    failures = [s for s in samples if not s["business"]["contract_ok"]]
    codes = sorted({str(s["business"].get("status_code")) for s in failures})
    lifecycle_ok = not cleanup_errors and run_error is None and not residual
    if run_error is None and samples and failures and lifecycle_ok:
        disposition = "transport_abort_propagates"
        note = f"front-end business oracle failed during confirmed abort (codes: {','.join(codes)}); no graceful degradation observed"
    elif run_error is None and samples and not failures and lifecycle_ok:
        disposition = "graceful_degradation_observed"
        note = "business oracle stayed HTTP 200 through the abort window; the edge degrades gracefully"
    else:
        disposition = "inconclusive"
        note = "injection, sampling, or lifecycle did not close; card stays provisional"
    result = {
        "schema_version": "chaosatlas-sock-shop-card-closure-v1",
        "card": "KB-RCA-sock-shop-front-end-catalogue-httpchaos-abort",
        "round_id": "card-closure-http-abort-r1",
        "namespace": NAMESPACE,
        "target": "http:catalogue:/catalogue (front-end->catalogue edge)",
        "oracle": "front-end GET /",
        "sample_count": len(samples),
        "failure_sample_count": len(failures),
        "failure_status_codes": codes,
        "run_error": run_error, "cleanup_errors": cleanup_errors,
        "residual_httpchaos": residual,
        "disposition": disposition, "note": note,
    }
    _write(output, "result.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("card", choices=["catalogue-db", "http-abort"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output {output} is not empty")
    output.mkdir(parents=True, exist_ok=True)
    if args.card == "catalogue-db":
        result = close_catalogue_db(output)
    else:
        result = close_http_abort(output)
    print(json.dumps({k: result[k] for k in ("disposition", "note")}, indent=2, ensure_ascii=True))
    return 0 if result["disposition"] != "inconclusive" else 1


if __name__ == "__main__":
    raise SystemExit(main())
