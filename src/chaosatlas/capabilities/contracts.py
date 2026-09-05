"""Stable contracts shared by core and provisional capability discovery."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from tools.extension_fault_catalog import extension_catalog
from tools.fault_catalog import fault_catalog


CAPABILITY_STATUSES = (
    "supported",
    "canary_required",
    "blocked",
    "unsupported",
    "inapplicable",
)
LEGACY_STATUS_MAP = {
    "blocked_by_platform_prerequisite": "blocked",
    "not_reachable": "blocked",
    "planned": "canary_required",
}
STATUS_PRIORITY = {status: index for index, status in enumerate(CAPABILITY_STATUSES)}
EVIDENCE_GRADES = ("E0", "E1", "E2", "E3", "E4")
ISOLATION_LEVELS = ("L1", "L2", "L3")


def canonical_catalog_ids() -> tuple[tuple[str, ...], tuple[str, ...]]:
    return tuple(fault_catalog()), tuple(extension_catalog())


def normalize_capability_status(status: Any) -> tuple[str, str]:
    raw = str(status or "inapplicable").strip()
    normalized = LEGACY_STATUS_MAP.get(raw, raw)
    if normalized not in CAPABILITY_STATUSES:
        raise ValueError(f"unknown capability status: {raw}")
    return normalized, raw


def evidence_grade_rank(grade: Any) -> int:
    value = str(grade or "E0").strip().upper()
    if value not in EVIDENCE_GRADES:
        raise ValueError(f"unknown evidence grade: {grade}")
    return EVIDENCE_GRADES.index(value)


def strongest_evidence_grade(grades: Iterable[Any], *, discovery_only: bool = False) -> str:
    values = [str(item or "E0").strip().upper() for item in grades]
    strongest = max(values or ["E0"], key=evidence_grade_rank)
    if discovery_only and evidence_grade_rank(strongest) > evidence_grade_rank("E1"):
        raise ValueError("read-only discovery cannot originate evidence above E1")
    return strongest


def aggregate_capability_status(statuses: Iterable[Any]) -> str:
    normalized = [normalize_capability_status(item)[0] for item in statuses]
    if not normalized:
        return "inapplicable"
    return min(normalized, key=STATUS_PRIORITY.__getitem__)


def validate_capability_record(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = (
        "project_id",
        "project_revision",
        "fault_id",
        "catalog_scope",
        "capability_status",
        "evidence_grade",
        "risk_level",
        "required_isolation",
        "reason_code",
        "reason",
        "candidate_eligible",
        "prerequisites",
        "oracle_ids",
        "evidence_refs",
    )
    for key in required:
        if key not in record:
            errors.append(f"missing {key}")
    if record.get("catalog_scope") not in {"core", "extension"}:
        errors.append("catalog_scope must be core or extension")
    try:
        normalize_capability_status(record.get("capability_status"))
    except ValueError as exc:
        errors.append(str(exc))
    try:
        evidence_grade_rank(record.get("evidence_grade"))
    except ValueError as exc:
        errors.append(str(exc))
    if record.get("required_isolation") not in ISOLATION_LEVELS:
        errors.append("required_isolation must be L1, L2 or L3")
    for key in ("prerequisites", "oracle_ids", "evidence_refs"):
        if key in record and not isinstance(record.get(key), list):
            errors.append(f"{key} must be a list")
    if "candidate_eligible" in record and not isinstance(record.get("candidate_eligible"), bool):
        errors.append("candidate_eligible must be a boolean")
    return errors


def validate_catalog_coverage(project_capabilities: list[dict[str, Any]]) -> list[str]:
    core_ids, extension_ids = canonical_catalog_ids()
    expected = set(core_ids) | set(extension_ids)
    actual = [str(item.get("fault_id") or "") for item in project_capabilities]
    counts = Counter(actual)
    errors = [f"duplicate aggregate capability: {key}" for key, count in sorted(counts.items()) if key and count != 1]
    missing = sorted(expected - set(actual))
    unexpected = sorted(set(actual) - expected)
    if missing:
        errors.append("missing capabilities: " + ",".join(missing))
    if unexpected:
        errors.append("unexpected capabilities: " + ",".join(unexpected))
    if len(actual) != len(expected):
        errors.append(f"aggregate capability count must be {len(expected)}, got {len(actual)}")
    return errors
