"""Read-only Kubernetes backend discovery used by capability bootstrap."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable


Runner = Callable[..., tuple[int, str, str]]
CHAOS_MESH_NAMESPACES = ("chaos-testing", "chaos-mesh")
CORE_CRDS = {
    "PodChaos": "podchaos.chaos-mesh.org",
    "StressChaos": "stresschaos.chaos-mesh.org",
    "NetworkChaos": "networkchaos.chaos-mesh.org",
    "DNSChaos": "dnschaos.chaos-mesh.org",
    "HTTPChaos": "httpchaos.chaos-mesh.org",
    "IOChaos": "iochaos.chaos-mesh.org",
    "TimeChaos": "timechaos.chaos-mesh.org",
    "JVMChaos": "jvmchaos.chaos-mesh.org",
}


def _run(runner: Runner, args: list[str], *, context: str | None, timeout: int = 30) -> tuple[int, str, str]:
    command = ["--context", context, *args] if context else list(args)
    try:
        return runner(command, timeout=timeout)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return 1, "", f"{type(exc).__name__}: {exc}"


def _ready(pod: dict[str, Any]) -> bool:
    metadata = pod.get("metadata") if isinstance(pod.get("metadata"), dict) else {}
    status = pod.get("status") if isinstance(pod.get("status"), dict) else {}
    return not metadata.get("deletionTimestamp") and any(
        item.get("type") == "Ready" and item.get("status") == "True"
        for item in status.get("conditions") or []
        if isinstance(item, dict)
    )


def probe_runtime_backends(*, runner: Runner, kube_context: str | None) -> dict[str, Any]:
    crds: dict[str, dict[str, Any]] = {}
    for backend, resource in CORE_CRDS.items():
        code, stdout, stderr = _run(runner, ["get", "crd", resource], context=kube_context)
        crds[backend] = {
            "resource": resource,
            "available": code == 0,
            "error": None if code == 0 else (stderr or stdout).strip(),
        }

    selected_namespace = None
    mesh_ready = False
    mesh_error: list[str] = []
    mesh_pods: list[str] = []
    partial_mesh: tuple[str, list[str]] | None = None
    for namespace in CHAOS_MESH_NAMESPACES:
        code, stdout, stderr = _run(
            runner,
            ["get", "pods", "-n", namespace, "-o", "json"],
            context=kube_context,
        )
        if code != 0:
            mesh_error.append(f"{namespace}: {(stderr or stdout).strip()}")
            continue
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            mesh_error.append(f"{namespace}: invalid JSON: {exc}")
            continue
        pods = [item for item in payload.get("items") or [] if isinstance(item, dict)] if isinstance(payload, dict) else []
        components = [
            item for item in pods
            if str((item.get("metadata") or {}).get("name") or "").startswith(("chaos-controller-manager", "chaos-daemon"))
        ]
        if not components:
            continue
        names = [str((item.get("metadata") or {}).get("name") or "") for item in components]
        has_controller = any(name.startswith("chaos-controller-manager") for name in names)
        has_daemon = any(name.startswith("chaos-daemon") for name in names)
        ready = has_controller and has_daemon and all(_ready(item) for item in components)
        if ready:
            selected_namespace = namespace
            mesh_pods = names
            mesh_ready = True
            break
        if partial_mesh is None:
            partial_mesh = (namespace, names)
        mesh_error.append(f"{namespace}: Chaos Mesh controller/daemon components are not Ready")
    if selected_namespace is None and partial_mesh is not None:
        selected_namespace, mesh_pods = partial_mesh

    return {
        "schema_version": "chaosatlas-runtime-capability-probe-v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "kube_context": kube_context,
        "chaos_mesh": {
            "namespace": selected_namespace,
            "ready": mesh_ready,
            "pods": mesh_pods,
            "errors": [] if mesh_ready else mesh_error,
        },
        "crds": crds,
        # HTTPChaos still requires its execution-time tproxy/ebtables gate.
        "httpchaos_runtime_verified": False,
        "read_only": True,
        "injection_performed": False,
    }
