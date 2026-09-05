"""Read-only cluster and workload probe for provisional extension faults."""

from __future__ import annotations

import json
import re
import subprocess
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable


Runner = Callable[..., tuple[int, str, str]]
CRDS = {
    "extension.io_delay": "iochaos.chaos-mesh.org",
    "extension.io_error": "iochaos.chaos-mesh.org",
    "extension.time_offset": "timechaos.chaos-mesh.org",
    "extension.jvm_gc_pause": "jvmchaos.chaos-mesh.org",
}


def _default_runner(args: list[str], timeout: int = 30) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(["kubectl", *args], capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, "", str(exc)
    return completed.returncode, completed.stdout or "", completed.stderr or ""


def _run(runner: Runner, args: list[str], *, context: str | None = None, timeout: int = 30) -> tuple[int, str, str]:
    command = (["--context", context, *args] if context else list(args))
    try:
        return runner(command, timeout=timeout)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return 1, "", f"{type(exc).__name__}: {exc}"


def _json(runner: Runner, args: list[str], *, context: str | None = None) -> tuple[Any | None, str | None]:
    code, stdout, stderr = _run(runner, [*args, "-o", "json"], context=context)
    if code != 0:
        return None, (stderr or stdout).strip() or f"kubectl exit {code}"
    try:
        return json.loads(stdout), None
    except json.JSONDecodeError as exc:
        return None, f"invalid kubectl JSON: {exc}"


def _ready(pod: dict[str, Any]) -> bool:
    return any(item.get("type") == "Ready" and item.get("status") == "True" for item in (pod.get("status") or {}).get("conditions") or [])


def _workload_facts(value: dict[str, Any]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for deployment in value.get("items") or []:
        if not isinstance(deployment, dict):
            continue
        metadata = deployment.get("metadata") or {}
        spec = deployment.get("spec") or {}
        template = spec.get("template") or {}
        pod_spec = template.get("spec") or {}
        containers = []
        for container in pod_spec.get("containers") or []:
            if not isinstance(container, dict):
                continue
            containers.append({
                "name": str(container.get("name") or ""),
                "image": str(container.get("image") or ""),
                "volume_mounts": [
                    {"name": str(mount.get("name") or ""), "path": str(mount.get("mountPath") or ""), "read_only": bool(mount.get("readOnly"))}
                    for mount in (container.get("volumeMounts") or []) if isinstance(mount, dict)
                ],
            })
        volumes = []
        for volume in pod_spec.get("volumes") or []:
            if not isinstance(volume, dict):
                continue
            name = str(volume.get("name") or "")
            if not name:
                continue
            kind = next((key for key in ("emptyDir", "persistentVolumeClaim", "hostPath", "configMap", "secret") if isinstance(volume.get(key), dict)), "unknown")
            volumes.append({"name": name, "kind": kind})
        facts.append({"name": str(metadata.get("name") or ""), "labels": deepcopy(metadata.get("labels") or {}), "containers": containers, "volumes": volumes})
    return facts


def _has_jvm(workloads: list[dict[str, Any]]) -> bool:
    pattern = re.compile(r"(?:java|jvm|openjdk|temurin|jetty|tomcat)", re.IGNORECASE)
    return any(pattern.search(str(container.get("image") or "")) for workload in workloads for container in workload.get("containers") or [])


def _disposable_target_config(profile: dict[str, Any], workloads: list[dict[str, Any]]) -> dict[str, Any]:
    runtime = profile.get("extension_runtime") if isinstance(profile.get("extension_runtime"), dict) else {}
    for target in runtime.get("disposable_targets") or []:
        if not isinstance(target, dict):
            continue
        selector = target.get("selector") if isinstance(target.get("selector"), dict) else {}
        for workload in workloads:
            labels = workload.get("labels") if isinstance(workload, dict) else {}
            if selector and all(str(labels.get(key)) == str(value) for key, value in selector.items()):
                return target
    return {}


def probe_extension_environment(
    profile: dict[str, Any],
    *,
    runner: Runner | None = None,
    kube_context: str | None = None,
) -> dict[str, Any]:
    """Return a deterministic, read-only extension applicability report."""
    runner = runner or _default_runner
    namespace_values = ((profile.get("namespace_policy") or {}).get("allowed_namespaces") or [])
    namespace = str(namespace_values[0]).strip() if len(namespace_values) == 1 else ""
    crd_checks: dict[str, Any] = {}
    for resource in sorted(set(CRDS.values())):
        code, stdout, stderr = _run(runner, ["get", "crd", resource], context=kube_context)
        crd_checks[resource] = {"status": "available" if code == 0 else "unavailable", "error": None if code == 0 else (stderr or stdout).strip()}
    mesh_namespace = None
    mesh_errors: list[str] = []
    mesh_pods: list[dict[str, Any]] = []
    for candidate_namespace in ("chaos-testing", "chaos-mesh"):
        mesh, mesh_error = _json(runner, ["get", "pods", "-n", candidate_namespace], context=kube_context)
        if mesh_error:
            mesh_errors.append(f"{candidate_namespace}: {mesh_error}")
            continue
        candidate_pods = [item for item in (mesh or {}).get("items") or [] if isinstance(item, dict)] if isinstance(mesh, dict) else []
        candidate_ready = bool(candidate_pods) and all(
            str((item.get("status") or {}).get("phase") or "") == "Running" and _ready(item)
            for item in candidate_pods
        )
        if candidate_ready:
            mesh_namespace = candidate_namespace
            mesh_pods = candidate_pods
            break
        if candidate_pods and not mesh_pods:
            mesh_namespace = candidate_namespace
            mesh_pods = candidate_pods
        if candidate_pods:
            mesh_errors.append(f"{candidate_namespace}: Chaos Mesh Pods are not Ready")
    mesh_ready = bool(mesh_pods) and all(
        str((item.get("status") or {}).get("phase") or "") == "Running" and _ready(item)
        for item in mesh_pods
    )
    deployments, deployment_error = _json(runner, ["get", "deployments", "-n", namespace], context=kube_context) if namespace else (None, "profile must declare one allowed namespace")
    workloads = _workload_facts(deployments) if isinstance(deployments, dict) else []
    cluster = {"context": kube_context, "namespace": namespace, "chaos_mesh_namespace": mesh_namespace, "chaos_mesh_ready": mesh_ready, "chaos_mesh_error": None if mesh_ready else "; ".join(mesh_errors), "crds": crd_checks, "workloads": workloads, "workload_error": deployment_error}
    dedicated_paths = ((profile.get("extension_runtime") or {}).get("io_test_paths") or [])
    disposable = bool((profile.get("extension_runtime") or {}).get("disposable_target"))
    disposable_config = _disposable_target_config(profile, workloads)
    if disposable_config:
        dedicated_paths = list(dedicated_paths) + [str(item) for item in disposable_config.get("io_test_paths") or [] if str(item).strip()]
        disposable = True
    target_capabilities = disposable_config.get("capabilities") if isinstance(disposable_config.get("capabilities"), dict) else {}
    results: list[dict[str, Any]] = []
    for extension_id, crd in CRDS.items():
        if crd_checks[crd]["status"] != "available":
            status, reason = "blocked", f"required CRD {crd} is unavailable"
        elif not mesh_ready:
            status, reason = "blocked", "Chaos Mesh controller/daemon is not Ready"
        elif extension_id in {"extension.io_delay", "extension.io_error"}:
            if not dedicated_paths or (disposable_config and target_capabilities.get("iochaos") is not True):
                status, reason = "blocked", "project profile has no dedicated disposable IO test path or test volume"
            elif not disposable:
                status, reason = "blocked", "IO mutation requires an explicitly disposable target"
            else:
                status, reason = "supported", "IOChaos and a dedicated disposable test path are declared"
        elif extension_id == "extension.time_offset":
            if not disposable or (disposable_config and target_capabilities.get("timechaos") is not True):
                status, reason = "blocked", "TimeChaos requires an explicitly disposable Pod target"
            else:
                status, reason = "supported", "TimeChaos and a disposable Pod target are available"
        elif not _has_jvm(workloads):
            status, reason = "inapplicable", "no JVM image was discovered in the target workloads"
        elif not disposable:
            status, reason = "blocked", "JVM mutation requires an explicitly disposable target"
        else:
            status, reason = "supported", "JVM image, JVMChaos and disposable target are available"
        results.append({"extension_id": extension_id, "category": {"extension.io_delay": "storage_io", "extension.io_error": "storage_io", "extension.time_offset": "time_clock", "extension.jvm_gc_pause": "runtime_jvm"}[extension_id], "status": status, "reason": reason, "crd": crd})
    native_agents = (profile.get("extension_runtime") or {}).get("native_agents") or {}
    for extension_id, category, agent_key in (
        ("extension.queue_backlog", "runtime_queue", "queue_agent"),
        ("extension.connection_pool_exhaustion", "connection_pool", "connection_pool_agent"),
        ("extension.runtime_pause", "runtime_generic", "pause_agent"),
    ):
        if not (native_agents.get(agent_key) is True or target_capabilities.get(agent_key) is True):
            status, reason = "blocked", f"{agent_key} is not declared by the project adapter"
        elif not disposable:
            status, reason = "blocked", "native runtime mutation requires an explicitly disposable target"
        else:
            status, reason = "supported", f"{agent_key} and a disposable target are declared"
        results.append({"extension_id": extension_id, "category": category, "status": status, "reason": reason, "backend": "ChaosAtlasNativeExtension"})
    return {"schema_version": "chaosatlas-extension-runtime-probe-v1", "checked_at": datetime.now(timezone.utc).isoformat(), "project_id": profile.get("project_id"), "cluster": cluster, "extensions": results, "read_only": True, "injection_performed": False}
