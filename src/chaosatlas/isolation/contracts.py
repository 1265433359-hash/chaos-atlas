"""Stable JSON contracts for isolation plans, leases and audits."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any


ISOLATION_LEVELS = ("L1", "L2", "L3")
LEASE_STATES = (
    "planned",
    "preparing",
    "ready",
    "prepare_failed",
    "releasing",
    "cleanup_failed",
    "expired",
    "released",
)
ACTIVE_LEASE_STATES = set(LEASE_STATES) - {"released"}
TRANSITIONS = {
    "planned": {"preparing", "expired", "releasing"},
    "preparing": {"ready", "prepare_failed", "expired", "releasing"},
    "ready": {"expired", "releasing"},
    "prepare_failed": {"releasing"},
    "releasing": {"released", "cleanup_failed"},
    "cleanup_failed": {"releasing"},
    "expired": {"releasing"},
    "released": set(),
}
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9.-]{0,62}$")
SENSITIVE_KEY = re.compile(r"(?:password|passwd|secret|token|authorization|cookie|api[_-]?key|private[_-]?key)", re.IGNORECASE)
SENSITIVE_VALUE = re.compile(r"(?:-----BEGIN [A-Z ]*PRIVATE KEY-----|\bBearer\s+[A-Za-z0-9._~+/=-]{8,})", re.IGNORECASE)


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def with_hash(value: dict[str, Any], field: str) -> dict[str, Any]:
    result = deepcopy(value)
    result.pop(field, None)
    result[field] = canonical_hash(result)
    return result


def verify_hash(value: dict[str, Any], field: str) -> bool:
    expected = str(value.get(field) or "")
    payload = deepcopy(value)
    payload.pop(field, None)
    return bool(expected) and expected == canonical_hash(payload)


def sensitive_paths(value: Any, path: str = "$") -> list[str]:
    """Return locations of likely credential material without returning values."""
    matches: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}"
            if SENSITIVE_KEY.search(str(key)) and item not in (None, False, "", [], {}):
                matches.append(child)
            matches.extend(sensitive_paths(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            matches.extend(sensitive_paths(item, f"{path}[{index}]"))
    elif isinstance(value, str) and SENSITIVE_VALUE.search(value):
        matches.append(path)
    return sorted(set(matches))


def transition_lease(lease: dict[str, Any], state: str) -> dict[str, Any]:
    current = str(lease.get("state") or "")
    if state not in TRANSITIONS.get(current, set()):
        raise ValueError(f"invalid lease transition: {current}->{state}")
    result = deepcopy(lease)
    result["state"] = state
    return with_hash(result, "lease_sha256")


def validate_plan(plan: dict[str, Any]) -> list[str]:
    required = (
        "schema_version", "plan_id", "project_id", "project_revision", "capability_id",
        "requested_isolation", "effective_isolation", "provider", "mode", "synthetic_data_only",
        "required_checks", "status", "blockers", "plan_sha256",
    )
    errors = [f"missing {key}" for key in required if key not in plan]
    if plan.get("schema_version") != "chaosatlas-isolation-plan-v1":
        errors.append("unknown isolation plan schema")
    if plan.get("requested_isolation") not in ISOLATION_LEVELS or plan.get("effective_isolation") not in ISOLATION_LEVELS:
        errors.append("isolation level must be L1, L2 or L3")
    elif ISOLATION_LEVELS.index(plan["effective_isolation"]) < ISOLATION_LEVELS.index(plan["requested_isolation"]):
        errors.append("effective isolation cannot be lower than requested isolation")
    if plan.get("status") not in {"ready", "blocked"}:
        errors.append("plan status must be ready or blocked")
    if plan.get("synthetic_data_only") is not True:
        errors.append("synthetic_data_only must be true")
    if not isinstance(plan.get("blockers"), list) or not isinstance(plan.get("required_checks"), list):
        errors.append("blockers and required_checks must be lists")
    exposed = sensitive_paths({"config": plan.get("config"), "blueprint": plan.get("blueprint"), "target": plan.get("target")})
    if exposed:
        errors.append("sensitive material detected at " + ",".join(exposed))
    if not verify_hash(plan, "plan_sha256"):
        errors.append("plan hash mismatch")
    return errors


def validate_lease(lease: dict[str, Any]) -> list[str]:
    required = (
        "schema_version", "lease_id", "plan_id", "project_id", "provider", "isolation_level",
        "state", "created_at", "expires_at", "owner_labels", "resources", "external_profiles",
        "cleanup_attempts", "lease_sha256",
    )
    errors = [f"missing {key}" for key in required if key not in lease]
    if lease.get("schema_version") != "chaosatlas-environment-lease-v1":
        errors.append("unknown environment lease schema")
    if lease.get("state") not in LEASE_STATES:
        errors.append("unknown lease state")
    if lease.get("isolation_level") not in ISOLATION_LEVELS:
        errors.append("invalid lease isolation level")
    if not SAFE_ID.fullmatch(str(lease.get("lease_id") or "")):
        errors.append("unsafe lease_id")
    if not isinstance(lease.get("resources"), list) or not isinstance(lease.get("external_profiles"), list):
        errors.append("resources and external_profiles must be lists")
    if not verify_hash(lease, "lease_sha256"):
        errors.append("lease hash mismatch")
    return errors


def validate_audit(audit: dict[str, Any]) -> list[str]:
    required = ("schema_version", "lease_id", "status", "checks", "errors", "audit_sha256")
    errors = [f"missing {key}" for key in required if key not in audit]
    if audit.get("schema_version") != "chaosatlas-isolation-audit-v1":
        errors.append("unknown isolation audit schema")
    if not verify_hash(audit, "audit_sha256"):
        errors.append("audit hash mismatch")
    return errors
