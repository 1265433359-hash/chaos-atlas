from __future__ import annotations

from tools.experiment_policy import new_policy_state
from tools.policy_selection_gate import select_candidates_with_policy


def _candidate(candidate_id: str) -> dict:
    return {
        "candidate_id": candidate_id,
        "target": candidate_id,
        "target_kind": "deployment",
        "fault_family": "pod_kill",
        "status": "eligible",
        "estimated_cost": 1.0,
        "blast_radius": 0.0,
    }


def _state(candidates: list[dict]) -> dict:
    return new_policy_state("demo", "a" * 40, 1001, candidates)


def test_legacy_mode_preserves_the_existing_candidate_order():
    candidates = [_candidate("candidate-a"), _candidate("candidate-b")]
    result = select_candidates_with_policy(candidates, _state(candidates), mode="legacy", budget=1)

    assert result["execution_candidate_ids"] == ["candidate-a"]
    assert result["policy_selected_candidate_ids"] == []
    assert result["fallback_used"] is False


def test_shadow_mode_records_policy_choice_but_keeps_legacy_execution():
    candidates = [_candidate("candidate-a"), _candidate("candidate-b")]
    result = select_candidates_with_policy(
        candidates,
        _state(candidates),
        mode="shadow",
        budget=1,
        context={"boundary_candidate_ids": ["candidate-b"]},
    )

    assert result["execution_candidate_ids"] == ["candidate-a"]
    assert result["policy_selected_candidate_ids"] == ["candidate-b"]
    assert result["policy_mode"] == "shadow"
    assert result["decision_changed"] is True


def test_guarded_mode_converts_policy_selection_to_allowlisted_execution():
    candidates = [_candidate("candidate-a"), _candidate("candidate-b")]
    result = select_candidates_with_policy(
        candidates,
        _state(candidates),
        mode="guarded",
        budget=1,
        context={"boundary_candidate_ids": ["candidate-b"]},
    )

    assert result["execution_candidate_ids"] == ["candidate-b"]
    assert result["policy_selected_candidate_ids"] == ["candidate-b"]
    assert result["fallback_used"] is False


def test_policy_error_falls_back_to_legacy_without_unbounded_selection():
    candidates = [_candidate("candidate-a"), _candidate("candidate-b")]
    result = select_candidates_with_policy(candidates, {"candidate_states": {}}, mode="guarded", budget=1)

    assert result["execution_candidate_ids"] == ["candidate-a"]
    assert result["policy_selected_candidate_ids"] == []
    assert result["fallback_used"] is True
    assert result["fallback_reason"]
