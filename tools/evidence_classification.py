"""Shared evidence classification for selection metrics (round-2 finding #2).

Both ``compare_selection_methods`` and ``selection_robustness`` must agree on
which candidates are "known" (enter the metric denominator) and how a known
candidate is classified (weakness / below_threshold / invalid).

Rules (shared, single source of truth):
  - A candidate is known only when it has discovery evidence AND its conclusions
    are not invalid. Invalid classes never enter the known denominator:
    invalid_baseline, invalid_not_injected, invalid_request_configuration,
    platform_or_preflight_blocked, not_applicable, transport_or_observation_error.
  - A candidate WITHOUT ``own_conclusions`` but WITH discovery evidence keeps
    the legacy "discovered" semantics (it is known, but unclassified) so older
    registry/evidence fixtures continue to work.
  - A candidate is weakness if ANY conclusion is a weakness class; invalid if
    ANY conclusion is an invalid class (invalid wins over weakness); otherwise
    below_threshold.
"""

from __future__ import annotations

from typing import Any

INVALID_CLASSES: frozenset[str] = frozenset({
    "invalid_not_injected",
    "invalid_baseline",
    "invalid_request_configuration",
    "platform_or_preflight_blocked",
    "not_applicable",
    "transport_or_observation_error",
})

WEAKNESS_CLASSES: frozenset[str] = frozenset({
    "client_timeout_observed",
    "server_error_observed",
    "grpc_error_observed",
    "response_contract_changed",
    "response_preserved_latency_degradation",
})

# statuses returned by classify_candidate
WEAKNESS = "weakness"
BELOW_THRESHOLD = "below_threshold"
INVALID = "invalid"
UNCLASSIFIED = "unclassified"


def classify_conclusion(classification: str | None) -> str:
    """Classify a single conclusion classification string."""
    if classification in INVALID_CLASSES:
        return INVALID
    if classification in WEAKNESS_CLASSES:
        return WEAKNESS
    return BELOW_THRESHOLD


def classify_candidate(item: dict[str, Any]) -> str:
    """weakness | below_threshold | invalid | unclassified for one candidate.

    Round-3 P1-3: previously "invalid wins" over every other conclusion, so a
    single invalid repeat (e.g. one invalid_baseline among several valid
    grpc_error_observed repeats) dropped the whole candidate out of the known
    set. The correct rule: FIRST drop invalid repeats, THEN aggregate the
    remaining valid conclusions.

      - no conclusions at all            -> unclassified (legacy discovery-only)
      - every conclusion is invalid      -> invalid (no usable evidence remains)
      - any valid conclusion is weakness -> weakness
      - otherwise (valid non-weak)       -> below_threshold
    """
    conclusions = item.get("own_conclusions") or []
    if not conclusions:
        return UNCLASSIFIED
    valid = [
        c for c in conclusions
        if classify_conclusion(c.get("classification")) != INVALID
    ]
    if not valid:
        return INVALID
    if any(classify_conclusion(c.get("classification")) == WEAKNESS for c in valid):
        return WEAKNESS
    return BELOW_THRESHOLD


def is_known_candidate(item: dict[str, Any]) -> bool:
    """True when the candidate enters the known metric denominator."""
    if not item.get("own_discovery_evidence"):
        return False
    return classify_candidate(item) != INVALID


def known_candidate_ids(evidence: dict[str, Any]) -> set[str]:
    """Unified 'known' set across both selection tools."""
    return {
        str(item.get("candidate_id"))
        for item in evidence.get("candidates", [])
        if is_known_candidate(item)
    }
