"""Target-scoped, side-effect-free assessment of the 32 core fault intents."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from chaosatlas.capabilities.contracts import normalize_capability_status
from tools.fault_catalog import fault_catalog


POD_BACKENDS = {"pod_kill", "container_kill"}
STRESS_BACKENDS = {"stress_cpu", "stress_memory"}
NETWORK_BACKENDS = {
    "network_loss",
    "network_partition",
    "network_delay",
    "network_bandwidth",
    "network_duplicate",
    "network_corrupt",
}
DNS_BACKENDS = {"dns_failure", "dns_delay"}
HTTP_CHAOS_BACKENDS = {
    "http_delay",
    "http_abort",
    "http_status_error",
    "http_response_corrupt",
    "dependency_error",
    "connection_reset",
}
NATIVE_HTTP_BACKENDS = {"http_rate_limit", "business_dependency_unreachable"}
NATIVE_RESOURCE_BACKENDS = {
    "disk_pressure",
    "file_descriptor_exhaustion",
    "process_exhaustion",
}
KUBERNETES_API_L1 = {
    "replica_reduction",
    "config_reload",
    "config_drift",
    "env_misconfiguration",
    "rollout_pause",
}
KUBERNETES_API_L2 = {"secret_rotation", "image_pull_failure", "pod_unschedulable"}


def isolation_for_core_fault(fault_id: str) -> str:
    if fault_id == "api_server_delay":
        return "L3"
    if fault_id in NATIVE_RESOURCE_BACKENDS | NATIVE_HTTP_BACKENDS | KUBERNETES_API_L2:
        return "L2"
    return "L1"


def _profile_boundary(profile: dict[str, Any], fault_id: str) -> tuple[str | None, str, str]:
    overrides = profile.get("fault_support") if isinstance(profile.get("fault_support"), dict) else {}
    override = overrides.get(fault_id) if isinstance(overrides.get(fault_id), dict) else None
    if not override:
        return None, "", ""
    status, raw = normalize_capability_status(override.get("status"))
    return status, raw, str(override.get("reason") or "profile capability declaration")


def _record(
    *,
    profile: dict[str, Any],
    fault_id: str,
    spec: dict[str, Any],
    node: dict[str, Any] | None,
    status: str,
    reason_code: str,
    reason: str,
    prerequisites: list[str] | None = None,
    evidence_grade: str = "E0",
    original_status: str | None = None,
) -> dict[str, Any]:
    deployment = (node or {}).get("deployment") if isinstance((node or {}).get("deployment"), dict) else {}
    target = str(deployment.get("name") or "") or None
    target_kind = str(deployment.get("workload_kind") or "") or None
    oracle_ids = [
        str(item.get("id"))
        for item in profile.get("business_oracles") or []
        if isinstance(item, dict) and item.get("id")
    ]
    result = {
        "project_id": str(profile.get("project_id") or ""),
        "project_revision": str(profile.get("project_commit") or ""),
        "target_id": str((node or {}).get("node_id") or "") or None,
        "target": target,
        "target_kind": target_kind,
        "fault_id": fault_id,
        "catalog_scope": "core",
        "category": str(spec.get("category") or ""),
        "backend": str(spec.get("backend") or ""),
        "risk_level": str(spec.get("risk_level") or ""),
        "required_isolation": isolation_for_core_fault(fault_id),
        "capability_status": status,
        "original_status": original_status,
        "evidence_grade": evidence_grade,
        "reason_code": reason_code,
        "reason": reason,
        "candidate_eligible": status in {"canary_required", "supported"},
        "prerequisites": sorted(set(prerequisites or [])),
        "oracle_ids": oracle_ids,
        "recovery_contract_id": "project-default" if profile.get("recovery") else None,
        "evidence_refs": [],
    }
    return result


def _backend_available(runtime: dict[str, Any], backend: str) -> bool:
    mesh = runtime.get("chaos_mesh") if isinstance(runtime.get("chaos_mesh"), dict) else {}
    crds = runtime.get("crds") if isinstance(runtime.get("crds"), dict) else {}
    crd = crds.get(backend) if isinstance(crds.get(backend), dict) else {}
    return bool(mesh.get("ready")) and crd.get("available") is True


def _assess_target(
    profile: dict[str, Any],
    fault_id: str,
    spec: dict[str, Any],
    node: dict[str, Any],
    runtime: dict[str, Any],
) -> dict[str, Any]:
    boundary, original, boundary_reason = _profile_boundary(profile, fault_id)
    if boundary in {"inapplicable", "blocked", "unsupported"}:
        return _record(
            profile=profile,
            fault_id=fault_id,
            spec=spec,
            node=node,
            status=boundary,
            original_status=original,
            reason_code="profile_boundary",
            reason=boundary_reason,
        )

    deployment = node.get("deployment") if isinstance(node.get("deployment"), dict) else {}
    extensions = node.get("extensions") if isinstance(node.get("extensions"), dict) else {}
    capabilities = extensions.get("capabilities") if isinstance(extensions.get("capabilities"), dict) else {}
    resources = extensions.get("resource_facts") if isinstance(extensions.get("resource_facts"), dict) else {}
    workload_kind = str(deployment.get("workload_kind") or "Deployment")
    containers = [str(item) for item in deployment.get("containers") or [] if str(item)]
    has_oracle = any(isinstance(item, dict) and item.get("id") for item in profile.get("business_oracles") or [])
    has_recovery = isinstance(profile.get("recovery"), dict) and bool(profile.get("cleanup"))
    disposable = bool(resources.get("disposable_target") or capabilities.get("disposable_target"))
    prerequisites: list[str] = []

    if not containers:
        return _record(profile=profile, fault_id=fault_id, spec=spec, node=node, status="inapplicable", reason_code="container_target_missing", reason="workload has no discoverable container")
    if fault_id == "rollout_pause" and workload_kind != "Deployment":
        return _record(profile=profile, fault_id=fault_id, spec=spec, node=node, status="inapplicable", reason_code="target_kind_inapplicable", reason="rollout pause requires a Deployment target")
    if fault_id in HTTP_CHAOS_BACKENDS | NATIVE_HTTP_BACKENDS and not node.get("service"):
        return _record(profile=profile, fault_id=fault_id, spec=spec, node=node, status="inapplicable", reason_code="service_target_missing", reason="HTTP boundary fault requires a selected Service")
    if not has_oracle:
        prerequisites.append("business_oracle")
    if not has_recovery:
        prerequisites.append("recovery_contract")

    backend = str(spec.get("backend") or "")
    if fault_id in POD_BACKENDS | STRESS_BACKENDS | NETWORK_BACKENDS | DNS_BACKENDS | HTTP_CHAOS_BACKENDS:
        if not _backend_available(runtime, backend):
            prerequisites.append(backend)
    if fault_id in HTTP_CHAOS_BACKENDS and runtime.get("httpchaos_runtime_verified") is not True:
        prerequisites.append("httpchaos_tproxy_positive_evidence")
    if fault_id in NATIVE_RESOURCE_BACKENDS:
        prerequisites.extend([] if disposable else ["disposable_target"])
        if capabilities.get("native_resource") is not True:
            prerequisites.append("native_resource_capability")
    if fault_id in NATIVE_HTTP_BACKENDS:
        if not disposable:
            prerequisites.append("disposable_target")
        if capabilities.get("native_http") is not True:
            prerequisites.append("native_http_control_contract")
    if fault_id in KUBERNETES_API_L2:
        if not disposable:
            prerequisites.append("disposable_target")
        if fault_id == "secret_rotation" and int(resources.get("secret_count") or 0) < 1:
            prerequisites.append("test_secret")
    if fault_id in {"replica_reduction", "config_reload", "config_drift", "env_misconfiguration", "image_pull_failure", "pod_unschedulable"} and workload_kind not in {"Deployment", "StatefulSet"}:
        prerequisites.append("patchable_workload")

    if prerequisites:
        code = "runtime_backend_unavailable" if backend.endswith("Chaos") else "safety_prerequisite_missing"
        if "httpchaos_tproxy_positive_evidence" in prerequisites:
            code = "http_runtime_prerequisite_unverified"
        return _record(
            profile=profile,
            fault_id=fault_id,
            spec=spec,
            node=node,
            status="blocked",
            reason_code=code,
            reason="required runtime, Oracle, recovery or isolation prerequisites are not confirmed",
            prerequisites=prerequisites,
            original_status=original or None,
        )

    return _record(
        profile=profile,
        fault_id=fault_id,
        spec=spec,
        node=node,
        status="canary_required",
        reason_code="live_canary_required",
        reason="target and read-only runtime prerequisites are available; live lifecycle evidence is required",
        evidence_grade="E1",
        original_status=original or None,
    )


def assess_core_capabilities(
    profile: dict[str, Any],
    nodes: list[dict[str, Any]],
    runtime: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return target records for every core capability without mutations."""
    records: list[dict[str, Any]] = []
    catalog = fault_catalog()
    for fault_id, spec in catalog.items():
        if fault_id == "api_server_delay":
            disposable_cluster = bool(((profile.get("isolation") or {}).get("disposable_cluster")))
            runtime_verified = runtime.get("api_server_delay_runtime_verified") is True
            status = "canary_required" if disposable_cluster or runtime_verified else "blocked"
            records.append(_record(
                profile=profile,
                fault_id=fault_id,
                spec=spec,
                node=None,
                status=status,
                reason_code="live_canary_required" if disposable_cluster or runtime_verified else "disposable_cluster_required",
                reason=("verified disposable control-plane canary is available; project-specific canary is still required" if runtime_verified and not disposable_cluster else "disposable control-plane environment is available" if disposable_cluster else "API-server delay requires a disposable cluster"),
                prerequisites=[] if disposable_cluster or runtime_verified else ["disposable_cluster"],
                evidence_grade="E1" if disposable_cluster or runtime_verified else "E0",
            ))
            continue
        if not nodes:
            records.append(_record(
                profile=profile,
                fault_id=fault_id,
                spec=spec,
                node=None,
                status="inapplicable",
                reason_code="target_missing",
                reason="no workload target was discovered",
            ))
            continue
        records.extend(_assess_target(profile, fault_id, spec, node, runtime) for node in nodes)
    return sorted(records, key=lambda item: (item["fault_id"], str(item.get("target") or ""), str(item.get("target_id") or "")))
