"""Controlled executor contracts for RCA actions.

This module provides a deterministic mock executor for offline closed-loop
tests. A live executor can implement the same callable contract later without
changing RCA state or promotion logic.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


EXECUTION_REQUIRED_FIELDS = {
    "namespace",
    "project_snapshot_sha256",
    "baseline_contract",
    "budget",
    "cleanup_contract",
}
ATTESTATION_FIELDS = (
    "baseline",
    "injection",
    "observation",
    "recovery",
    "cleanup",
    "independent_oracle",
)
ATTESTATION_SCHEMA_VERSION = "chaosatlas-runtime-result-v1"


def _attestation(*, valid: bool, comparison_eligible: bool) -> dict[str, Any]:
    return {
        "schema_version": ATTESTATION_SCHEMA_VERSION,
        "valid": valid,
        "comparison_eligible": comparison_eligible,
        **{field: valid for field in ATTESTATION_FIELDS},
    }


class MockRCAExecutor:
    """Return deterministic executor responses for offline RCA tests."""

    def __init__(self, responses: dict[str, dict[str, Any]] | None = None) -> None:
        self._responses = deepcopy(responses or {})

    def __call__(self, action: dict[str, Any]) -> dict[str, Any]:
        missing = sorted(
            field
            for field in EXECUTION_REQUIRED_FIELDS
            if not action.get(field)
        )
        if missing:
            return {
                "outcome_status": "environment_blocked",
                "missing_contract_fields": missing,
                "attestation": _attestation(valid=False, comparison_eligible=False),
                "evidence": [],
            }

        response = deepcopy(self._responses.get(str(action.get("action_id")), {}))
        response.setdefault("outcome_status", "observed")
        response.setdefault(
            "attestation",
            _attestation(valid=True, comparison_eligible=True),
        )
        response.setdefault("evidence", [])
        return response
