import sys
import types

import pytest

from tools.chaosatlas_hypothesis import (
    build_hypotheses_with_advisory,
    parse_advisory_output,
    rank_candidates,
)


@pytest.fixture
def candidate_space():
    return {
        "candidate_count": 2,
        "candidates": [
            {"candidate_id": "candidate-a", "fault_family": "pod_kill", "target": "frontend"},
            {"candidate_id": "candidate-b", "fault_family": "network_loss", "target": "payment"},
        ],
    }


def test_cards_do_not_change_candidate_count_but_can_change_order(candidate_space):
    plain = rank_candidates(candidate_space, cards=[])
    informed = rank_candidates(
        candidate_space,
        cards=[{"status": "local_reusable", "test_node": {"family": "network_loss"}}],
    )

    assert plain["candidate_count"] == informed["candidate_count"]
    assert plain["candidate_ids"] != informed["candidate_ids"]
    assert {"candidate-a", "candidate-b"} == set(informed["candidate_ids"])


def test_advisory_rejects_final_verdict_fields():
    raw = '{"hypotheses": [], "weakness_status": "confirmed"}'

    with pytest.raises(ValueError, match="forbidden"):
        parse_advisory_output(raw, allowed_candidate_ids={"candidate-a"})


def test_no_provider_uses_deterministic_fallback(candidate_space):
    result = build_hypotheses_with_advisory(
        rank_candidates(candidate_space, cards=[]),
        {"candidate_space": candidate_space},
    )

    assert result["advisory_status"] == "deterministic_fallback"
    assert result["hypotheses"]
    assert all("weakness_status" not in item for item in result["hypotheses"])


def test_ranked_candidates_records_knowledge_snapshot(candidate_space):
    result = rank_candidates(
        candidate_space,
        cards=[{"id": "FA-1", "status": "local_reusable", "test_node": {"family": "pod_kill"}}],
    )

    assert result["knowledge_card_ids"] == ["FA-1"]
    assert result["knowledge_view_sha256"]


def test_rank_candidates_falls_back_when_legacy_registry_is_missing(monkeypatch, candidate_space):
    legacy_engine = types.ModuleType("tools.decision_engine")

    def missing_registry(*_args, **_kwargs):
        raise ModuleNotFoundError("No module named 'project_registry'", name="project_registry")

    legacy_engine.rank = missing_registry
    monkeypatch.setitem(sys.modules, "tools.decision_engine", legacy_engine)

    result = rank_candidates(candidate_space, cards=[], rca_snapshot={"schema_version": 1})

    assert result["runtime_retrieval"] is False
    assert result["ranking_fallback"] is True
    assert result["ranking_fallback_reason"] == "missing_legacy_dependency:project_registry"
    assert result["candidate_count"] == 2
