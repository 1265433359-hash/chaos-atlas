"""Shared lifecycle validation for comparable ChaosAtlas runtime reports."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


REQUIRED_LIFECYCLE_FIELDS = (
    "schema_version",
    "project_id",
    "namespace",
    "arm",
    "mutation_id",
    "replicate",
    "mutation",
    "baseline",
    "injection",
    "observation",
    "recovery",
    "cleanup",
    "washout",
    "diagnostics",
    "human_review",
    "status",
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bool_field(report: dict[str, Any], section: str, field: str) -> bool:
    value = report.get(section)
    return isinstance(value, dict) and value.get(field) is True


def _validation_errors(report: dict[str, Any]) -> list[str]:
    errors = [
        field for field in REQUIRED_LIFECYCLE_FIELDS if field not in report
    ]
    if errors:
        return errors

    if report.get("human_review") != "pending":
        errors.append("human_review")

    mutation = report.get("mutation")
    if not isinstance(mutation, dict):
        errors.append("mutation")
        return errors

    path_value = mutation.get("path")
    recorded_hash = mutation.get("sha256")
    if not isinstance(path_value, str) or not path_value:
        errors.append("mutation.path")
    if not isinstance(recorded_hash, str) or len(recorded_hash) != 64:
        errors.append("mutation.sha256")
    if isinstance(path_value, str) and path_value and isinstance(recorded_hash, str):
        path = Path(path_value)
        if path.is_file():
            if sha256_file(path) != recorded_hash:
                errors.append("mutation.sha256")

    cleanup = report.get("cleanup")
    if not isinstance(cleanup, dict):
        errors.append("cleanup")
    elif not isinstance(cleanup.get("residual_resources"), list):
        errors.append("cleanup.residual_resources")

    return sorted(set(errors))


def validate_lifecycle_report(report: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {"valid": False, "errors": ["report"]}
    errors = _validation_errors(report)
    return {"valid": not errors, "errors": errors}


def comparison_eligibility(report: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    for section, field in (
        ("baseline", "pass"),
        ("recovery", "recovered"),
        ("washout", "stable"),
    ):
        if not _bool_field(report, section, field):
            reasons.append(f"{section}.{field}")

    for field in ("applied", "injected"):
        if not _bool_field(report, "injection", field):
            reasons.append(f"injection.{field}")

    cleanup = report.get("cleanup")
    if not isinstance(cleanup, dict) or cleanup.get("absent_confirmed") is not True:
        reasons.append("cleanup.absent_confirmed")
    if not isinstance(cleanup, dict) or cleanup.get("residual_resources") != []:
        reasons.append("cleanup.residual_resources")

    validation = validate_lifecycle_report(report)
    reasons.extend(error for error in validation["errors"] if error not in reasons)
    return {"eligible": not reasons, "reasons": sorted(set(reasons))}
