"""Build an auditable per-project matrix for the canonical fault catalog."""

from __future__ import annotations

from typing import Any

from tools.fault_catalog import fault_catalog


MATRIX_STATUSES = (
    "supported",
    "planned",
    "inapplicable",
    "blocked_by_platform_prerequisite",
    "not_reachable",
    "unsupported",
)


def build_fault_matrix(profile: dict[str, Any]) -> dict[str, Any]:
    project_id = str(profile.get("project_id") or "")
    runtime = profile.get("runtime_contract") or {}
    runtime_supported = {str(item) for item in runtime.get("supported_fault_families") or []}
    overrides = profile.get("fault_support") or {}
    faults: list[dict[str, Any]] = []
    for fault_id, spec in fault_catalog().items():
        override = overrides.get(fault_id) if isinstance(overrides, dict) else None
        if isinstance(override, dict):
            status = str(override.get("status") or "planned")
            reason = str(override.get("reason") or "profile support declaration")
        elif fault_id in runtime_supported and spec.get("status") == "implemented":
            status = "supported"
            reason = "declared by runtime_contract"
        elif spec.get("status") == "implemented":
            status = "inapplicable"
            reason = "implemented globally but not declared by this project profile"
        else:
            status = "planned"
            reason = "executor contract is not implemented"
        if status not in MATRIX_STATUSES:
            status = "inapplicable"
            reason = f"invalid profile status: {status}"
        faults.append({
            "fault_id": fault_id,
            "category": spec.get("category"),
            "backend": spec.get("backend"),
            "risk_level": spec.get("risk_level"),
            "status": status,
            "reason": reason,
            "execution_eligible": status == "supported",
        })
    return {
        "schema_version": "chaosatlas-fault-matrix-v1",
        "project_id": project_id,
        "fault_count": len(faults),
        "faults": faults,
        "status_counts": {status: sum(1 for item in faults if item["status"] == status) for status in MATRIX_STATUSES},
    }
