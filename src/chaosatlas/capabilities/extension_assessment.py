"""Normalize all nine provisional extensions into target-scoped records."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from tools.dependency_fault_capability import DEPENDENCY_EXTENSIONS, assess_dependency_capability
from tools.extension_capability import assess_extension_capability
from tools.extension_fault_catalog import extension_catalog


NON_DEPENDENCY_EXTENSIONS = tuple(
    extension_id for extension_id in extension_catalog() if extension_id not in DEPENDENCY_EXTENSIONS
)


def isolation_for_extension(extension_id: str) -> str:
    return "L1" if extension_id in DEPENDENCY_EXTENSIONS else "L2"


def _parameters(extension_id: str, node: dict[str, Any]) -> dict[str, Any]:
    facts = node.get("extensions") if isinstance(node.get("extensions"), dict) else {}
    runtime = facts.get("runtime") if isinstance(facts.get("runtime"), dict) else {}
    paths = [str(item) for item in facts.get("writable_paths") or [] if str(item)]
    return {
        "extension.io_delay": {"path": paths[0] if paths else "", "latency_ms": 100, "percent": 25, "duration_s": 10},
        "extension.io_error": {"path": paths[0] if paths else "", "errno": 5, "percent": 10, "duration_s": 10},
        "extension.time_offset": {"offset_ms": 500, "duration_s": 10},
        "extension.jvm_gc_pause": {"target_process": str(runtime.get("process_name") or ""), "pause_ms": 100, "duration_s": 10},
        "extension.queue_backlog": {"queue_name": "chaosatlas-test-queue", "depth": 100, "duration_s": 10},
        "extension.connection_pool_exhaustion": {"pool_name": "chaosatlas-test-pool", "connections": 20, "duration_s": 10},
        "extension.runtime_pause": {"target_process": str(runtime.get("process_name") or "python"), "pause_ms": 100, "duration_s": 10},
    }[extension_id]


def _record(
    *,
    profile: dict[str, Any],
    extension_id: str,
    spec: dict[str, Any],
    target_id: str | None,
    target: str | None,
    target_kind: str | None,
    assessment: dict[str, Any],
    oracle_id: str | None = None,
) -> dict[str, Any]:
    raw_status = str(assessment.get("status") or "inapplicable")
    status = "canary_required" if raw_status == "supported" else raw_status
    grade = "E1" if status == "canary_required" else "E0"
    requirements = [str(item) for item in assessment.get("requirements") or [] if str(item)]
    reason_code = {
        "canary_required": "live_canary_required",
        "blocked": "extension_prerequisite_missing",
        "inapplicable": "extension_target_inapplicable",
    }.get(status, "extension_assessment")
    oracle_ids = [oracle_id] if oracle_id else [
        str(item.get("id"))
        for item in profile.get("business_oracles") or []
        if isinstance(item, dict) and item.get("id")
    ]
    return {
        "project_id": str(profile.get("project_id") or ""),
        "project_revision": str(profile.get("project_commit") or ""),
        "target_id": target_id,
        "target": target,
        "target_kind": target_kind,
        "fault_id": extension_id,
        "catalog_scope": "extension",
        "category": str(spec.get("category") or ""),
        "backend": str(spec.get("backend") or ""),
        "risk_level": str(spec.get("risk_level") or ""),
        "required_isolation": isolation_for_extension(extension_id),
        "capability_status": status,
        "original_status": raw_status,
        "evidence_grade": grade,
        "reason_code": reason_code,
        "reason": str(assessment.get("reason") or "extension capability assessment"),
        "candidate_eligible": status in {"canary_required", "supported"},
        "prerequisites": sorted(set(requirements)),
        "oracle_ids": [item for item in oracle_ids if item],
        "recovery_contract_id": "project-default" if profile.get("recovery") else None,
        "evidence_refs": [],
        "assessment_evidence": deepcopy(assessment.get("evidence") or {}),
    }


def assess_extension_capabilities(
    profile: dict[str, Any],
    nodes: list[dict[str, Any]],
    dependencies: list[dict[str, Any]],
    runtime: dict[str, Any],
) -> list[dict[str, Any]]:
    catalog = extension_catalog()
    records: list[dict[str, Any]] = []
    for node in nodes:
        deployment = node.get("deployment") if isinstance(node.get("deployment"), dict) else {}
        for extension_id in NON_DEPENDENCY_EXTENSIONS:
            backend = str(catalog[extension_id].get("backend") or "")
            crd = (runtime.get("crds") or {}).get(backend) if isinstance(runtime.get("crds"), dict) else {}
            runtime_backend_ready = bool((runtime.get("chaos_mesh") or {}).get("ready")) and isinstance(crd, dict) and crd.get("available") is True
            effective_node = deepcopy(node)
            facts = effective_node.get("extensions") if isinstance(effective_node.get("extensions"), dict) else {}
            capabilities = facts.get("capabilities") if isinstance(facts.get("capabilities"), dict) else {}
            capability_key = {"IOChaos": "iochaos", "TimeChaos": "timechaos", "JVMChaos": "jvmchaos"}.get(backend)
            if capability_key:
                capabilities[capability_key] = runtime_backend_ready
                facts["capabilities"] = capabilities
                effective_node["extensions"] = facts
            assessment = assess_extension_capability(extension_id, effective_node, _parameters(extension_id, effective_node))
            if backend.endswith("Chaos") and not runtime_backend_ready:
                assessment = {
                    "status": "blocked",
                    "reason": f"required runtime backend {backend} is unavailable",
                    "requirements": [backend],
                }
            records.append(_record(
                profile=profile,
                extension_id=extension_id,
                spec=catalog[extension_id],
                target_id=str(node.get("node_id") or "") or None,
                target=str(deployment.get("name") or "") or None,
                target_kind=str(deployment.get("workload_kind") or "") or None,
                assessment=assessment,
            ))

    network_ready = bool((runtime.get("chaos_mesh") or {}).get("ready")) and bool(((runtime.get("crds") or {}).get("NetworkChaos") or {}).get("available"))
    for edge in dependencies:
        if not isinstance(edge, dict) or not edge.get("id") or not edge.get("source_selector") or not edge.get("target_selector"):
            continue
        edge_id = str(edge.get("id") or "")
        for extension_id in DEPENDENCY_EXTENSIONS:
            assessment = assess_dependency_capability(extension_id, edge, networkchaos_available=network_ready)
            records.append(_record(
                profile=profile,
                extension_id=extension_id,
                spec=catalog[extension_id],
                target_id=f"dependency:{edge_id}" if edge_id else None,
                target=f"{edge.get('source')}->{edge.get('target')}",
                target_kind="dependency_edge",
                assessment=assessment,
                oracle_id=str(edge.get("oracle_id") or "") or None,
            ))

    present = {item["fault_id"] for item in records}
    for extension_id, spec in catalog.items():
        if extension_id in present:
            continue
        records.append(_record(
            profile=profile,
            extension_id=extension_id,
            spec=spec,
            target_id=None,
            target=None,
            target_kind=None,
            assessment={
                "status": "inapplicable",
                "reason": "no matching workload or dependency target was discovered",
                "requirements": list(spec.get("required_capabilities") or []),
            },
        ))
    return sorted(records, key=lambda item: (item["fault_id"], str(item.get("target") or ""), str(item.get("target_id") or "")))
