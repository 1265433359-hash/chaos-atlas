"""Run a bounded two-arm P08 Appsmith PodChaos experiment."""

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


NAMESPACE = "chaosatlas-p08"
IMAGE = "index.docker.io/appsmith/appsmith-ce@sha256:2d657315862dac42b43b6416aa30f70e3f777cb7a46e494ac276028c020ea467"
ARM_NAMES = ("ChaosAtlas-KB", "ChaosAtlas-noKB")
DEPLOYMENT = "appsmith-server"
SERVICE = "appsmith"
LOCAL_PORT = 18080
REMOTE_PORT = 80
ORACLE_PATH = "/api/v1/health"
CHAOS_NAME_PREFIX = "p08-appsmith-pod-kill-chaosatlas"
APP_LABELS = {"app.kubernetes.io/name": "appsmith", "app.kubernetes.io/part-of": NAMESPACE}
CHAOS_RESOURCES = "podchaos,networkchaos,stresschaos"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def dump(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=True, sort_keys=True) + "\n"


def prepare_output_dir(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise FileExistsError(f"refusing to use nonempty output directory: {path}")
    path.mkdir(parents=True, exist_ok=True)


def build_appsmith_manifest() -> dict[str, Any]:
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": DEPLOYMENT, "namespace": NAMESPACE, "labels": APP_LABELS},
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": APP_LABELS},
            "template": {
                "metadata": {"labels": APP_LABELS},
                "spec": {
                    "containers": [
                        {
                            "name": "appsmith",
                            "image": IMAGE,
                            "ports": [{"name": "http", "containerPort": REMOTE_PORT}],
                            "env": [
                                {"name": "APPSMITH_ENCRYPTION_PASSWORD", "value": "chaosatlas-p08-local"},
                                {"name": "APPSMITH_ENCRYPTION_SALT", "value": "chaosatlas-p08-salt"},
                            ],
                            "resources": {
                                "requests": {"cpu": "500m", "memory": "3000Mi"},
                                "limits": {"cpu": "2", "memory": "4Gi"},
                            },
                            "readinessProbe": {
                                "httpGet": {"path": ORACLE_PATH, "port": REMOTE_PORT},
                                "initialDelaySeconds": 45,
                                "periodSeconds": 5,
                                "timeoutSeconds": 3,
                                "failureThreshold": 12,
                            },
                            "livenessProbe": {
                                "httpGet": {"path": ORACLE_PATH, "port": REMOTE_PORT},
                                "initialDelaySeconds": 90,
                                "periodSeconds": 10,
                                "timeoutSeconds": 3,
                                "failureThreshold": 6,
                            },
                            "volumeMounts": [{"name": "appsmith-stacks", "mountPath": "/appsmith-stacks"}],
                        }
                    ],
                    "volumes": [{"name": "appsmith-stacks", "emptyDir": {}}],
                },
            },
        },
    }


def build_service_manifest() -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": SERVICE, "namespace": NAMESPACE, "labels": APP_LABELS},
        "spec": {"selector": APP_LABELS, "ports": [{"name": "http", "port": REMOTE_PORT, "targetPort": REMOTE_PORT}]},
    }


def build_podchaos_manifest(arm: str) -> dict[str, Any]:
    if arm not in ARM_NAMES:
        raise ValueError(f"unknown P08 arm: {arm}")
    suffix = "kb" if arm == "ChaosAtlas-KB" else "nokb"
    return {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "PodChaos",
        "metadata": {"name": f"{CHAOS_NAME_PREFIX}-{suffix}", "namespace": NAMESPACE},
        "spec": {
            "action": "pod-kill",
            "mode": "one",
            "selector": {"namespaces": [NAMESPACE], "labelSelectors": APP_LABELS},
        },
    }


def validate_appsmith_manifest(document: dict[str, Any]) -> str:
    metadata = document.get("metadata", {})
    spec = document.get("spec", {})
    template = spec.get("template", {})
    containers = template.get("spec", {}).get("containers", [])
    if document.get("kind") != "Deployment" or metadata.get("namespace") != NAMESPACE:
        raise ValueError("Appsmith Deployment must be in chaosatlas-p08")
    if metadata.get("name") != DEPLOYMENT or spec.get("replicas") != 1:
        raise ValueError("Appsmith Deployment must be one replica with the registered name")
    if spec.get("selector", {}).get("matchLabels") != APP_LABELS:
        raise ValueError("Appsmith Deployment selector is not namespace-local")
    if len(containers) != 1 or containers[0].get("image") != IMAGE:
        raise ValueError("Appsmith image must use the registered immutable digest")
    return NAMESPACE


def validate_podchaos_manifest(document: dict[str, Any]) -> str:
    metadata = document.get("metadata", {})
    spec = document.get("spec", {})
    selector = spec.get("selector", {})
    if document.get("kind") != "PodChaos" or metadata.get("namespace") != NAMESPACE:
        raise ValueError("P08 PodChaos must be in chaosatlas-p08")
    if spec.get("action") != "pod-kill" or spec.get("mode") != "one":
        raise ValueError("P08 PodChaos must be mode=one pod-kill")
    if selector != {"namespaces": [NAMESPACE], "labelSelectors": APP_LABELS}:
        raise ValueError("P08 PodChaos selector must target only the Appsmith P08 labels")
    return str(metadata.get("name"))


def kubectl(args: list[str], timeout: int = 60, input_text: str | None = None) -> tuple[int, str, str]:
    try:
        result = subprocess.run(["kubectl", *args], input=input_text, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return result.returncode, result.stdout or "", result.stderr or ""
    except subprocess.TimeoutExpired as exc:
        return 124, "", str(exc)


def kubectl_json(args: list[str], timeout: int = 60) -> dict[str, Any]:
    code, out, err = kubectl([*args, "-o", "json"], timeout)
    if code != 0:
        raise RuntimeError((err or out).strip())
    value = json.loads(out)
    if not isinstance(value, dict):
        raise RuntimeError("kubectl JSON root is not an object")
    return value


def residual_chaos() -> list[dict[str, Any]]:
    data = kubectl_json(["get", CHAOS_RESOURCES, "-n", NAMESPACE])
    return [{"kind": item.get("kind"), "name": item.get("metadata", {}).get("name")} for item in data.get("items", [])]


def namespace_health() -> dict[str, Any]:
    deployment = kubectl_json(["get", "deployment", DEPLOYMENT, "-n", NAMESPACE])
    pods = kubectl_json(["get", "pods", "-n", NAMESPACE, "-l", ",".join(f"{k}={v}" for k, v in APP_LABELS.items())])
    status = deployment.get("status", {})
    pod_rows = []
    for item in pods.get("items", []):
        ready = any(c.get("type") == "Ready" and c.get("status") == "True" for c in item.get("status", {}).get("conditions", []))
        pod_rows.append({"name": item.get("metadata", {}).get("name"), "uid": item.get("metadata", {}).get("uid"), "ready": ready, "phase": item.get("status", {}).get("phase")})
    return {
        "healthy": int(status.get("readyReplicas", 0) or 0) == 1 and int(status.get("availableReplicas", 0) or 0) == 1 and len(pod_rows) == 1 and pod_rows[0]["ready"],
        "deployment": {"ready": status.get("readyReplicas", 0), "available": status.get("availableReplicas", 0), "updated": status.get("updatedReplicas", 0)},
        "pods": pod_rows,
    }


def wait_healthy(timeout: float = 300, stable_successes: int = 3) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    stable = 0
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = namespace_health()
        stable = stable + 1 if last["healthy"] else 0
        if stable >= stable_successes:
            return {**last, "stable_successes": stable}
        time.sleep(2)
    raise TimeoutError(f"P08 did not become healthy: {json.dumps(last, ensure_ascii=True)}")


def start_forward() -> subprocess.Popen[str]:
    return subprocess.Popen(["kubectl", "port-forward", "-n", NAMESPACE, f"svc/{SERVICE}", f"{LOCAL_PORT}:{REMOTE_PORT}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")


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


def wait_forward(process: subprocess.Popen[str], timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            out, err = process.communicate()
            raise RuntimeError((err or out).strip())
        try:
            with socket.create_connection(("127.0.0.1", LOCAL_PORT), timeout=0.5):
                return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError("P08 port-forward did not start")


def oracle_request(timeout: float = 10) -> dict[str, Any]:
    started = time.monotonic()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{LOCAL_PORT}{ORACLE_PATH}", timeout=timeout) as response:
            body = response.read(65536)
            return {"observed_at": now(), "status_code": response.status, "latency_ms": round((time.monotonic() - started) * 1000, 3), "body_sha256": sha256_bytes(body), "error": None}
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        return {"observed_at": now(), "status_code": getattr(exc, "code", None), "latency_ms": round((time.monotonic() - started) * 1000, 3), "body_sha256": None, "error": str(exc)}


def collect_oracle(required_successes: int, timeout: float = 180) -> tuple[list[dict[str, Any]], bool]:
    deadline = time.monotonic() + timeout
    samples: list[dict[str, Any]] = []
    consecutive = 0
    process: subprocess.Popen[str] | None = None
    try:
        while time.monotonic() < deadline and consecutive < required_successes:
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
            sample = oracle_request()
            samples.append(sample)
            consecutive = consecutive + 1 if sample.get("status_code") == 200 else 0
            if sample.get("status_code") != 200:
                stop_forward(process)
                process = None
            time.sleep(1)
        return samples, consecutive >= required_successes
    finally:
        stop_forward(process)


def apply_yaml(document: dict[str, Any]) -> None:
    code, out, err = kubectl(["apply", "-f", "-"], input_text=yaml.safe_dump(document, sort_keys=False))
    if code != 0:
        raise RuntimeError((err or out).strip())


def delete_resource(kind: str, name: str) -> dict[str, Any]:
    code, out, err = kubectl(["delete", kind, name, "-n", NAMESPACE, "--ignore-not-found=true", "--wait=true"])
    verify_code, verify_out, verify_err = kubectl(["get", kind, name, "-n", NAMESPACE])
    return {"delete_code": code, "delete_output": (out or err).strip(), "absent_confirmed": verify_code != 0, "verify_output": (verify_out or verify_err).strip()}


def run_arm(arm: str, output: Path, baseline_successes: int, recovery_timeout: float) -> dict[str, Any]:
    chaos = build_podchaos_manifest(arm)
    chaos_name = validate_podchaos_manifest(chaos)
    result: dict[str, Any] = {"project_id": "P08", "namespace": NAMESPACE, "arm": arm, "candidate_id": "P08-appsmith-server-pod_kill-01", "status": "started", "human_review": "pending", "mutation_applied": False, "cleanup": {"absent_confirmed": False}}
    try:
        baseline, baseline_ok = collect_oracle(baseline_successes, timeout=180)
        result["baseline"] = {"samples": baseline, "stable": baseline_ok}
        if not baseline_ok:
            raise RuntimeError("P08 baseline oracle did not produce required stable successes")
        result["pre_injection_health"] = wait_healthy()
        apply_yaml(chaos)
        result["mutation_applied"] = True
        result["injected"] = True
        result["injection_at"] = now()
        time.sleep(5)
        recovered_health = wait_healthy(timeout=recovery_timeout)
        result["recovery_health"] = recovered_health
        recovered_samples, recovered_ok = collect_oracle(baseline_successes, timeout=recovery_timeout)
        result["recovered"] = recovered_ok
        result["post_recovery_oracle"] = {"samples": recovered_samples, "stable": recovered_ok}
        if not recovered_ok:
            raise RuntimeError("P08 oracle did not recover")
        result["status"] = "completed"
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = str(exc)
        result.setdefault("recovered", False)
    finally:
        result["cleanup"] = delete_resource("podchaos", chaos_name)
        result["residual_chaos"] = residual_chaos()
        result["cleanup"]["global_p08_absent"] = not result["residual_chaos"]
        (output / f"{arm.lower()}.json").write_text(dump(result), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-context", default="minikube")
    parser.add_argument("--baseline-successes", type=int, default=5)
    parser.add_argument("--recovery-timeout", type=float, default=300)
    args = parser.parse_args()
    if args.baseline_successes <= 0:
        raise SystemExit("--baseline-successes must be positive")
    prepare_output_dir(args.output)
    context_code, context, context_err = kubectl(["config", "current-context"])
    if context_code != 0 or context.strip() != args.expected_context:
        raise SystemExit(f"unexpected kubectl context: {(context_err or context).strip()}")
    app = build_appsmith_manifest()
    service = build_service_manifest()
    validate_appsmith_manifest(app)
    apply_yaml(app)
    apply_yaml(service)
    (args.output / "deployment.yaml").write_text(yaml.safe_dump(app, sort_keys=False), encoding="utf-8")
    (args.output / "service.yaml").write_text(yaml.safe_dump(service, sort_keys=False), encoding="utf-8")
    wait_healthy(timeout=360)
    reports = [run_arm(arm, args.output, args.baseline_successes, args.recovery_timeout) for arm in ARM_NAMES]
    deployment_cleanup = delete_resource("deployment", DEPLOYMENT)
    service_cleanup = delete_resource("service", SERVICE)
    (args.output / "summary.json").write_text(dump({"schema_version": "1.0", "project_id": "P08", "namespace": NAMESPACE, "status": "completed" if all(r["status"] == "completed" for r in reports) else "failed", "arms": reports, "deployment_cleanup": deployment_cleanup, "service_cleanup": service_cleanup, "residual_chaos": residual_chaos(), "human_review": "pending", "knowledge_base_updated": False}), encoding="utf-8")
    return 0 if all(r["status"] == "completed" for r in reports) else 2


if __name__ == "__main__":
    raise SystemExit(main())
