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
