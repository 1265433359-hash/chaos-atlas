from __future__ import annotations

import json

import pytest

from tools.chaosatlas_hypothesis import (
    build_hypothesis_input,
    parse_advisory_output,
    rank_candidates,
)


INVENTORY = {"project_id": "sock-shop", "services": ["front-end"], "claim_scope": "static"}
DETECTION = {"capability_name": "server_deployment_detection", "status": "verified"}
CANDIDATE_SPACE = {
    "candidate_count": 2,
    "candidates": [
        {"candidate_id": "candidate-1", "fault_family": "pod_kill", "target": "front-end", "static_prior": None},
        {"candidate_id": "candidate-2", "fault_family": "stress_cpu", "target": "front-end", "static_prior": "singleton_availability_risk"},
    ],
}
LOCAL_CARD = {
    "id": "KB-singleton",
    "status": "local_reusable",
    "test_node": {"family": "pod_kill"},
    "hypothesis": "singleton workload may lose availability",
}


def test_retrieval_happens_after_project_mapping() -> None:
    result = build_hypothesis_input(INVENTORY, DETECTION, CANDIDATE_SPACE, cards=[])

    assert result["candidate_space"]
    assert result["knowledge_view"] == []


def test_experience_cards_can_change_order_but_not_candidate_truth() -> None:
    plain = rank_candidates(CANDIDATE_SPACE, cards=[])
    informed = rank_candidates(CANDIDATE_SPACE, cards=[LOCAL_CARD])

    assert plain["candidate_count"] == informed["candidate_count"] == 2
    assert set(plain["candidate_ids"]) == set(informed["candidate_ids"])
    assert plain["candidate_ids"] != informed["candidate_ids"]
    assert informed["candidate_ids"][0] == "candidate-1"


def test_advisory_output_cannot_set_final_status() -> None:
    raw = json.dumps(
        {
            "hypotheses": [{"candidate_id": "candidate-1", "mechanism": "singleton replacement gap", "expected_observations": ["pod identity changes"], "missing_evidence": ["business probe"]}],
            "weakness_status": "confirmed",
        }
    )

    with pytest.raises(ValueError, match="forbidden"):
        parse_advisory_output(raw, allowed_candidate_ids={"candidate-1"})


def test_advisory_output_accepts_only_bounded_fields() -> None:
    raw = json.dumps(
        {
            "hypotheses": [{"candidate_id": "candidate-1", "mechanism": "singleton replacement gap", "expected_observations": ["pod identity changes"], "missing_evidence": ["business probe"]}],
            "global_missing_evidence": ["independent business probe"],
        }
    )

    result = parse_advisory_output(raw, allowed_candidate_ids={"candidate-1"})

    assert result["hypotheses"][0]["candidate_id"] == "candidate-1"
    assert "rca_status" not in result

