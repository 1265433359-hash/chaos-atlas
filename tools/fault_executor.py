"""Shared lifecycle contract for fault executors.

The contract is deliberately small: runtime adapters own collection and
recovery, while this module decides whether a result is complete enough for
comparison, RCA and knowledge feedback.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AttestationResult:
    """Validation result for one runtime lifecycle attestation."""

    valid: bool
    missing: tuple[str, ...]


class LifecycleAttestation:
    """Required evidence gates shared by all runtime fault executors."""

    REQUIRED = (
        "baseline",
        "injection",
        "observation",
        "recovery",
        "cleanup",
        "independent_oracle",
        "comparison_eligible",
    )


def validate_attestation(value: dict[str, Any] | None) -> AttestationResult:
    """Return whether every lifecycle gate is explicitly true.

    Missing keys and false values are treated identically. Truthy-but-not-true
    values are rejected so serialized evidence cannot accidentally bypass a
    gate with strings such as ``"yes"``.
    """

    payload = value if isinstance(value, dict) else {}
    missing = tuple(key for key in LifecycleAttestation.REQUIRED if payload.get(key) is not True)
    return AttestationResult(valid=not missing, missing=missing)


def observation_verdict(
    observation: dict[str, Any] | None,
    execution_status: str | None = None,
    outcome_status: str | None = None,
) -> str:
    """Normalize a completed business observation into a terminal verdict."""
    payload = observation if isinstance(observation, dict) else {}
    outcome = str(outcome_status or "").strip()
    if outcome in {"rate_limit_observed", "dependency_unreachable_observed"}:
        return outcome
    status = str(payload.get("status") or "").strip()
    if status in {"pass", "degraded", "business_unreachable"}:
        return status
    if status in {"business_not_reachable", "not_reachable"}:
        return "business_unreachable"
    if status:
        return "observation_inconclusive"
    return "observation_pending" if execution_status in {"executed", "observed"} else str(execution_status or "unknown")
