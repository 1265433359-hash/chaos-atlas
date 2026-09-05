"""Run namespace-scoped Dify Kubernetes PodChaos service canaries.

Each canary kills one target Pod and uses a target-specific independent probe:
HTTP for Dify services, redis-cli for Redis, and pg_isready for PostgreSQL.
The lifecycle executor owns the Chaos Mesh apply, injection, recovery, and
cleanup gates; this runner only supplies the service probe and manifests.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import time
from typing import Any

# Keep direct ``python scripts\...`` execution consistent with the repository
# CLI, which imports the top-level ``tools`` package.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.kubernetes_lifecycle_executor import KubernetesLifecycleExecutor
from tools.dify_canary_closed_loop import record_canary_trial
from tools.run_chaos_experiment import (
    http_request,
    observation_failure_sample,
    run_kubectl,
    start_port_forward,
    stop_process,
    wait_for_port,
)


NAMESPACE = "dify-k8s-lab"
CONTEXT = "chaosatlas-dify"
PROFILE = Path(__file__).resolve().parents[1] / "projects" / "dify-kubernetes" / "profile.json"


def _read_profile() -> dict[str, Any]:
    value = json.loads(PROFILE.read_text(encoding="utf-8-sig"))
    return value if isinstance(value, dict) else {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _selector_arg(labels: dict[str, str]) -> str:
    return ",".join(f"{key}={value}" for key, value in labels.items())


def _manifest(name: str, labels: dict[str, str], fault_family: str, container: str) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "selector": {"namespaces": [NAMESPACE], "labelSelectors": labels},
        "action": "pod-kill" if fault_family == "pod_kill" else "container-kill",
        "mode": "one",
        "duration": "30s",
    }
    if fault_family == "container_kill":
        spec["containerNames"] = [container]
    return {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "PodChaos",
        "metadata": {
            "name": name,
            "namespace": NAMESPACE,
            "labels": {"chaosatlas.dev/cleanup-owner": "chaosatlas"},
        },
        "spec": spec,
    }


def _ready_pod(labels: dict[str, str]) -> tuple[str | None, str | None]:
    code, stdout, stderr = run_kubectl(
        ["get", "pods", "-n", NAMESPACE, "-l", _selector_arg(labels), "-o", "json"],
        timeout=20,
        kube_context=CONTEXT,
    )
    if code != 0:
        return None, (stderr or stdout).strip()[-300:] or f"kubectl exited {code}"
    try:
        items = json.loads(stdout).get("items") or []
    except (TypeError, json.JSONDecodeError) as exc:
        return None, f"invalid Pod JSON: {exc}"
    for item in items:
        metadata = item.get("metadata") or {}
        status = item.get("status") or {}
        if metadata.get("deletionTimestamp"):
            continue
        ready = any(
            condition.get("type") == "Ready" and condition.get("status") == "True"
            for condition in status.get("conditions") or []
            if isinstance(condition, dict)
        )
        if ready and metadata.get("name"):
            return str(metadata["name"]), None
    return None, "no Ready target Pod"


def _http_probe(
    *,
    phase: str,
    service: str,
    remote_port: int,
    local_port: int,
    path: str,
    expected_body: str | None = None,
    headers: dict[str, str] | None = None,
    observation_window_s: float = 60.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + (observation_window_s if phase == "observe" else 0.0)
    retry_interval = 2.0
    samples: list[dict[str, Any]] = []
    failures: list[str] = []
    sample_index = 0
    while True:
        process = None
        try:
            process = start_port_forward(
                NAMESPACE, service, local_port, remote_port, kube_context=CONTEXT
            )
            wait_for_port("127.0.0.1", local_port, process, 15.0)
            sample = http_request(local_port, path, "GET", 5.0, None, 65536, headers=headers)
            sample_index += 1
            sample["sample"] = sample_index
            samples.append(sample)
            passed = sample.get("status_code") == 200 and (
                expected_body is None or expected_body in str(sample.get("body") or "")
            )
            if passed:
                return {
                    "status": "degraded" if failures else "pass",
                    "phase": phase,
                    "samples": samples,
                    "reason": "target recovered after transient probe failures" if failures else None,
                }
            failures.append(f"HTTP status {sample.get('status_code')}")
        except (OSError, RuntimeError, TimeoutError) as exc:
            sample_index += 1
            samples.append(observation_failure_sample(sample_index, str(exc)))
            failures.append(str(exc))
        finally:
            stop_process(process)
        if time.monotonic() >= deadline:
            return {
                "status": "business_unreachable",
                "phase": phase,
                "samples": samples,
                "reason": failures[-1] if failures else "HTTP probe did not pass",
            }
        time.sleep(min(retry_interval, max(0.0, deadline - time.monotonic())))


def _exec_probe(
    *,
    phase: str,
    labels: dict[str, str],
    command: str,
    expected_output: str,
    observation_window_s: float = 60.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + (observation_window_s if phase == "observe" else 0.0)
    samples: list[dict[str, Any]] = []
    failures: list[str] = []
    sample_index = 0
    while True:
        pod, reason = _ready_pod(labels)
        if pod:
            code, stdout, stderr = run_kubectl(
                ["exec", pod, "-n", NAMESPACE, "--", "sh", "-c", command],
                timeout=20,
                kube_context=CONTEXT,
            )
            sample_index += 1
            output = (stdout or "").strip()
            sample = {
                "sample": sample_index,
                "pod": pod,
                "return_code": code,
                "output": output[-300:],
                "error": (stderr or "").strip()[-300:] or None,
            }
            samples.append(sample)
            if code == 0 and expected_output in output:
                return {
                    "status": "degraded" if failures else "pass",
                    "phase": phase,
                    "samples": samples,
                    "reason": "target recovered after transient probe failures" if failures else None,
                }
            failures.append((stderr or stdout or f"probe exited {code}").strip()[-300:])
        else:
            sample_index += 1
            samples.append({"sample": sample_index, "observation_status": "fail", "reason": reason})
            failures.append(reason or "no Ready target Pod")
        if time.monotonic() >= deadline:
            return {
                "status": "business_unreachable",
                "phase": phase,
                "samples": samples,
                "reason": failures[-1] if failures else "exec probe did not pass",
            }
        time.sleep(min(2.0, max(0.0, deadline - time.monotonic())))


def _plugin_tenant_id() -> str:
    code, stdout, _stderr = run_kubectl(
        ["logs", "deploy/dify-k8s-plugin-daemon", "-n", NAMESPACE, "--tail=300"],
        timeout=30,
        kube_context=CONTEXT,
    )
    if code == 0:
        matches = re.findall(r"tenant_id=([0-9a-fA-F-]{36})", stdout)
        if matches:
            return matches[-1]
    raise RuntimeError("could not discover a tenant id from Plugin Daemon logs")


def _plugin_server_key() -> str:
    code, stdout, _stderr = run_kubectl(
        [
            "exec",
            "deploy/dify-k8s-plugin-daemon",
            "-n",
            NAMESPACE,
            "--",
            "sh",
            "-c",
            "printf %s \"$SERVER_KEY\"",
        ],
        timeout=20,
        kube_context=CONTEXT,
    )
    value = stdout.strip() if code == 0 else ""
    if not value:
        raise RuntimeError("SERVER_KEY is unavailable in Plugin Daemon")
    return value


def _targets() -> list[dict[str, Any]]:
    tenant_id = _plugin_tenant_id()
    server_key = _plugin_server_key()
    return [
        {
            "id": "plugin-daemon",
            "labels": {
                "app.kubernetes.io/instance": "dify-k8s",
                "app.kubernetes.io/name": "dify",
                "component": "plugin-daemon",
            },
            "container": "plugin-daemon",
            "probe": lambda phase: _http_probe(
                phase=phase,
                service="dify-k8s-plugin-daemon",
                remote_port=5002,
                local_port=18092,
                path=f"/plugin/{tenant_id}/management/models?page=1&page_size=1",
                headers={"X-Api-Key": server_key},
                observation_window_s=60.0,
            ),
        },
        {
            "id": "sandbox",
            "labels": {
                "app.kubernetes.io/instance": "dify-k8s",
                "app.kubernetes.io/name": "dify",
                "component": "sandbox",
            },
            "container": "sandbox",
            "probe": lambda phase: _http_probe(
                phase=phase,
                service="dify-k8s-sandbox",
                remote_port=8194,
                local_port=18093,
                path="/health",
                expected_body="ok",
                observation_window_s=60.0,
            ),
        },
        {
            "id": "redis",
            "labels": {
                "app.kubernetes.io/instance": "dify-k8s",
                "app.kubernetes.io/name": "redis",
                "app.kubernetes.io/component": "master",
            },
            "container": "redis",
            "probe": lambda phase: _exec_probe(
                phase=phase,
                labels={
                    "app.kubernetes.io/instance": "dify-k8s",
                    "app.kubernetes.io/name": "redis",
                    "app.kubernetes.io/component": "master",
                },
                command='REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli --no-auth-warning -h 127.0.0.1 -p 6379 ping',
                expected_output="PONG",
                observation_window_s=60.0,
            ),
        },
        {
            "id": "postgresql",
            "labels": {
                "app.kubernetes.io/instance": "dify-k8s",
                "app.kubernetes.io/name": "postgresql",
                "app.kubernetes.io/component": "primary",
            },
            "container": "postgresql",
            "probe": lambda phase: _exec_probe(
                phase=phase,
                labels={
                    "app.kubernetes.io/instance": "dify-k8s",
                    "app.kubernetes.io/name": "postgresql",
                    "app.kubernetes.io/component": "primary",
                },
                command="pg_isready -U postgres -d dbname=dify -h 127.0.0.1 -p 5432",
                expected_output="accepting connections",
                observation_window_s=60.0,
            ),
        },
        {
            "id": "weaviate",
            "labels": {"app": "weaviate"},
            "container": "weaviate",
            "probe": lambda phase: _http_probe(
                phase=phase,
                service="weaviate",
                remote_port=80,
                local_port=18094,
                path="/v1/.well-known/ready",
                observation_window_s=60.0,
            ),
        },
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--only",
        action="append",
        choices=["plugin-daemon", "sandbox", "redis", "postgresql", "weaviate"],
    )
    parser.add_argument("--fault-family", choices=["pod_kill", "container_kill"], default="pod_kill")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    profile = _read_profile()

    try:
        targets = _targets()
    except RuntimeError as exc:
        (output / "summary.json").write_text(
            json.dumps({"status": "failed", "error": str(exc)}, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"status": "failed", "error": str(exc)}))
        return 2

    selected = set(args.only or [item["id"] for item in targets])
    results: list[dict[str, Any]] = []
    for target in targets:
        if target["id"] not in selected:
            continue
        resource_family = args.fault_family.replace("_", "-")
        action_id = f"{target['id']}-{resource_family}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        manifest = _manifest(action_id, target["labels"], args.fault_family, target["container"])
        root = output / target["id"]
        executor = KubernetesLifecycleExecutor(
            root=root,
            namespace=NAMESPACE,
            allowed_namespaces={NAMESPACE},
            allow_live=True,
            oracle={"kind": "http", "service": "unused", "remote_port": 1},
            hooks={"probe": lambda phase, _manifest, probe=target["probe"]: probe(phase)},
            poll_interval=0.5,
            injection_timeout=45.0,
            recovery_timeout=180.0,
            kube_context=CONTEXT,
        )
        print(f"[start] {target['id']} action={action_id}")
        try:
            result = executor.run(manifest, action_id=action_id)
            result_summary = {
                "target": target["id"],
                "action_id": action_id,
                "status": result.get("status"),
                "outcome_status": result.get("outcome_status"),
                "attestation": result.get("attestation"),
                "errors": result.get("errors") or [],
                "result_file": str(root / "runtime" / f"{action_id}.json"),
            }
        except Exception as exc:  # Keep later targets from being skipped.
            result_summary = {
                "target": target["id"],
                "action_id": action_id,
                "status": "runner_error",
                "errors": [f"{type(exc).__name__}: {exc}"],
            }
            result = {"status": "runner_error", "errors": result_summary["errors"]}
        service_target = {
            "plugin-daemon": "dify-k8s-plugin-daemon",
            "sandbox": "dify-k8s-sandbox",
            "redis": "dify-k8s-redis-master",
            "postgresql": "dify-k8s-postgresql",
            "weaviate": "weaviate",
        }.get(target["id"], target["id"])
        closed_loop = record_canary_trial(
            root=root,
            profile=profile,
            candidate={
                "candidate_id": f"service:{service_target}:{args.fault_family}",
                "target": service_target,
                "target_kind": "statefulset" if target["id"] in {"redis", "postgresql", "weaviate"} else "deployment",
                "fault_family": args.fault_family,
                "parameters": {"mode": "one", "duration": "30s"},
                "parameter_level": "baseline",
            },
            result=result,
            project_inventory={"namespace": NAMESPACE},
            repetition=1,
        )
        result_summary["closed_loop"] = closed_loop
        results.append(result_summary)
        print(json.dumps(result_summary, ensure_ascii=True))

    passed = [
        item
        for item in results
        if item.get("status") == "executed"
        and (item.get("attestation") or {}).get("valid") is True
    ]
    summary = {
        "schema_version": "chaosatlas-dify-k8s-service-canaries-v1",
        "status": "passed" if len(passed) == len(results) else "failed",
        "started_at": _now(),
        "context": CONTEXT,
        "namespace": NAMESPACE,
        "fault_family": args.fault_family,
        "targets": results,
        "passed": len(passed),
        "total": len(results),
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": summary["status"], "passed": len(passed), "total": len(results)}))
    return 0 if summary["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
