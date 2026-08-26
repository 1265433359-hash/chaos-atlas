"""Schemas and fail-closed validation for the experiment policy artifacts."""

from __future__ import annotations

import math
import re
from typing import Any


STATE_SCHEMA = "chaosatlas-experiment-policy-state-v1"
DECISION_SCHEMA = "chaosatlas-experiment-policy-decision-v1"
POLICY_VERSION = "ig-stop-v1"
# ``budget_exhausted`` is an orchestration guard, not a scoring outcome.  It
# records that the caller's explicit round budget prevented another mutation.
STOP_REASONS = {"resolved", "decision_irrelevant", "blocked", "low_expected_value", "budget_exhausted"}
STATUSES = {"unknown", "below_threshold", "weakness", "defended", "blocked"}
POSTERIOR_KEYS = {"weakness", "protected", "below_threshold"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def _required(doc: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    return [key for key in keys if key not in doc]


def validate_policy_state(doc: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(doc, dict):
        return {"valid": False, "errors": ["root_not_object"]}
    if doc.get("schema_version") != STATE_SCHEMA:
        errors.append("invalid_schema_version")
    if not str(doc.get("policy_version") or "").strip():
        errors.append("policy_version_required")
    if not str(doc.get("project_id") or "").strip():
        errors.append("project_id_required")
    if not _COMMIT.fullmatch(str(doc.get("project_commit") or "")):
        errors.append("project_commit_invalid")
    if not isinstance(doc.get("seed"), int):
        errors.append("seed_required")
    if not _SHA256.fullmatch(str(doc.get("input_sha256") or "")):
        errors.append("input_sha256_invalid")
    rows = doc.get("candidate_states")
    if not isinstance(rows, dict):
        errors.append("candidate_states_required")
        rows = {}
    for candidate_id, row in rows.items():
        if not isinstance(row, dict):
            errors.append(f"candidate_state_not_object:{candidate_id}")
            continue
        if row.get("status") not in STATUSES:
            errors.append(f"invalid_status:{candidate_id}")
        posterior = row.get("posterior")
        if not isinstance(posterior, dict) or set(posterior) != POSTERIOR_KEYS:
            errors.append(f"posterior_keys_invalid:{candidate_id}")
            continue
        values = [posterior.get(key) for key in POSTERIOR_KEYS]
        if any(not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1 for value in values):
            errors.append("posterior_out_of_range")
        elif abs(sum(values) - 1.0) > 1e-6:
            errors.append(f"posterior_not_normalized:{candidate_id}")
        if not isinstance(row.get("run_count"), int) or row["run_count"] < 0:
            errors.append(f"run_count_invalid:{candidate_id}")
        if not isinstance(row.get("observed_outcomes"), list):
            errors.append(f"observed_outcomes_invalid:{candidate_id}")
    return {"valid": not errors, "errors": errors}


def validate_policy_decision(doc: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(doc, dict):
        return {"valid": False, "errors": ["root_not_object"]}
    if doc.get("schema_version") != DECISION_SCHEMA:
        errors.append("invalid_schema_version")
    if not str(doc.get("project_id") or "").strip():
        errors.append("project_id_required")
    if not _SHA256.fullmatch(str(doc.get("input_sha256") or "")):
        errors.append("input_sha256_invalid")
    stop_reason = doc.get("stop_reason")
    if stop_reason is not None and stop_reason not in STOP_REASONS:
        errors.append("invalid_stop_reason")
    if not isinstance(doc.get("scores"), list):
        errors.append("scores_required")
    return {"valid": not errors, "errors": errors}
