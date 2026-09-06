"""Read-only Kubernetes backend discovery used by capability bootstrap."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
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


def _load_httpchaos_evidence(root: str | Path | None, kube_context: str | None) -> dict[str, Any]:
    """Load a separately produced, secret-free HTTPChaos canary attestation.

    Discovery remains read-only and conservative: the runtime flag becomes true
    only when an external artifact explicitly records a verified canary in the
    same Kubernetes context.  A CRD/controller probe alone is never sufficient.
    """
    if root is None:
        return {"verified": False, "reason": "no external HTTPChaos evidence root"}
    evidence_root = Path(root).expanduser().resolve()
    path = evidence_root / "httpchaos-runtime-evidence.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {"verified": False, "reason": f"evidence unavailable: {type(exc).__name__}"}
    if not isinstance(payload, dict):
        return {"verified": False, "reason": "evidence root must be an object"}
    if payload.get("schema_version") != "chaosatlas-httpchaos-runtime-evidence-v1":
        return {"verified": False, "reason": "unsupported HTTPChaos evidence schema"}
    if str(payload.get("kube_context") or "") != str(kube_context or ""):
        return {"verified": False, "reason": "evidence Kubernetes context mismatch"}
    canaries = payload.get("canaries")
    if not isinstance(canaries, list) or not canaries:
        return {"verified": False, "reason": "evidence has no canary records"}
    valid = []
    for item in canaries:
        if not isinstance(item, dict):
            continue
        attestation = item.get("attestation") if isinstance(item.get("attestation"), dict) else {}
        effect = item.get("effect") if isinstance(item.get("effect"), dict) else {}
        if attestation.get("valid") is True and effect.get("confirmed") is True:
            valid.append(item)
    return {
        "verified": bool(valid),
        "reason": "verified live HTTPChaos canary evidence" if valid else "no canary has valid lifecycle and effect evidence",
        "canary_count": len(canaries),
        "valid_canary_count": len(valid),
        "evidence_ref": str(path),
    }


def _load_platform_evidence(root: str | Path | None, kube_context: str | None) -> dict[str, Any]:
    """Load verified disposable control-plane canary evidence."""
    if root is None:
        return {"verified": False, "reason": "no external platform evidence root"}
    path = Path(root).expanduser().resolve() / "platform-runtime-evidence.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {"verified": False, "reason": f"evidence unavailable: {type(exc).__name__}"}
    if not isinstance(payload, dict) or payload.get("schema_version") != "chaosatlas-platform-runtime-evidence-v1":
        return {"verified": False, "reason": "unsupported platform evidence schema"}
    record = payload.get("api_server_delay") if isinstance(payload.get("api_server_delay"), dict) else {}
    evidence_context = str(payload.get("kube_context") or "")
    context_matches = evidence_context == str(kube_context or "")
    platform_scope = payload.get("scope") == "platform" and payload.get("disposable_cluster") is True and evidence_context.startswith("chaosatlas-")
    if not context_matches and not platform_scope:
        return {"verified": False, "reason": "evidence Kubernetes context mismatch"}
    verified = record.get("verified") is True and (record.get("attestation") or {}).get("valid") is True
    return {
        "verified": verified,
        "reason": "verified disposable api_server_delay canary" if verified else "api_server_delay canary is not verified",
        "evidence_ref": str(path),
        "attestation_valid": (record.get("attestation") or {}).get("valid") is True,
    }


def probe_runtime_backends(*, runner: Runner, kube_context: str | None, evidence_root: str | Path | None = None) -> dict[str, Any]:
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

    http_evidence = _load_httpchaos_evidence(evidence_root, kube_context)
    platform_evidence = _load_platform_evidence(evidence_root, kube_context)
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
        "httpchaos_runtime_verified": http_evidence.get("verified") is True,
        "httpchaos_runtime_evidence": http_evidence,
        "api_server_delay_runtime_verified": platform_evidence.get("verified") is True,
        "platform_runtime_evidence": platform_evidence,
        "read_only": True,
        "injection_performed": False,
    }
