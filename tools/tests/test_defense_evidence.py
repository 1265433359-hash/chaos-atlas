from __future__ import annotations

import pytest

from tools.classify_runtime_result import classify
from tools.feedback_protocol import build_feedback_card, classify_outcome


def _run_with_defense(defense_evidence: dict) -> dict:
    return {
        "claim_scope": "frontend->catalogue",
        "mutation": "runtime/run.json",
        "preflight": {"decision": "ready_for_injection"},
        "lifecycle": {
            "injected": True,
            "injected_status": {"injected_count": 1},
            "recovered": True,
            "cleanup": {"resource_absent_after_delete": True},
        },
        "requests": [{"status_code": 200, "latency_ms": 20, "body": {"ok": True}}],
        "defense_evidence": defense_evidence,
    }


def test_complete_bounded_timeout_evidence_can_create_specific_defense_claim() -> None:
    run = _run_with_defense(
        {
            "claim_type": "bounded_timeout",
            "mechanism_evidence": True,
            "independent_oracle": True,
            "observation_window": True,
        }
    )
    result = classify(run, {"requests": [{"status_code": 200, "latency_ms": 20, "body": {"ok": True}}]})

    assert result["result_contract"]["result"] == "defended"
    assert result["result_contract"]["valid"] is True
    assert result["result_contract"]["defense_claim_type"] == "bounded_timeout"
    assert result["interpretation"]["defense_claim"] == "bounded_timeout"
    assert result["result_contract"]["defense_claim_allowed"] is True


def test_response_preserved_without_matching_mechanism_stays_boundary_only() -> None:
    result = classify(
        _run_with_defense(
            {
                "claim_type": "bounded_timeout",
                "mechanism_evidence": False,
                "independent_oracle": True,
                "observation_window": True,
            }
        ),
        {"requests": [{"status_code": 200, "latency_ms": 20, "body": {"ok": True}}]},
    )

    assert result["result_contract"]["result"] == "response_preserved"
    assert result["result_contract"]["defense_claim_allowed"] is False


@pytest.mark.parametrize(
    "claim_type",
    ["bounded_timeout", "retry", "fallback", "circuit_breaker", "redundancy", "graceful_degradation", "probe_restart_escape"],
)
def test_supported_defense_claim_types_share_the_same_evidence_gate(claim_type: str) -> None:
    result = classify(
        _run_with_defense(
            {
                "claim_type": claim_type,
                "mechanism_evidence": True,
                "independent_oracle": True,
                "observation_window": True,
            }
        ),
        {"requests": [{"status_code": 200, "latency_ms": 20, "body": {"ok": True}}]},
    )

    assert result["result_contract"]["result"] == "defended"
    assert result["result_contract"]["defense_claim_type"] == claim_type


def test_feedback_protected_claim_requires_matching_mechanism_evidence() -> None:
    result = {
        "project_id": "sock-shop",
        "project_commit": "a" * 40,
        "round_id": "r1",
        "canonical_signature": "front-end-pod-kill",
        "target": "front-end",
        "target_kind": "deployment",
        "fault_family": "pod_kill",
        "oracle_label": "protected",
        "availability_label": "availability_defended",
        "defense_claim_type": "redundancy",
        "valid_reproductions": 1,
        "evidence": {
            "baseline": True,
            "injection": True,
            "observation": True,
            "observation_window": True,
            "recovery": True,
            "cleanup": True,
            "independent_oracle": True,
            "mechanism_evidence": True,
        },
    }

    assert classify_outcome(result) == "protected"
    card = build_feedback_card(result, review_status="human_reviewed")
    assert card["abstraction"]["defense_claim_type"] == "redundancy"

    result["evidence"]["mechanism_evidence"] = False
    assert classify_outcome(result) == "unsupported"
