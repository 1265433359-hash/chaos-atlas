import pytest

from tools.rca_policy_adapter import select_rca_action


def _action(action_id: str, gain: int, cost: int) -> dict:
    return {
        "action_id": action_id,
        "kind": "log_lookup",
        "hypotheses_separated": gain,
        "evidence_gain": 1,
        "cost": cost,
        "risk": 0,
        "environment_uncertainty": 0,
        "preconditions": [],
        "cleanup": {"required": False},
        "output_schema": {"type": "json"},
    }


def test_rca_action_selection_is_separate_from_fault_candidate_ids():
    result = select_rca_action(
        [_action("action-a", 3, 1), _action("action-b", 1, 1)],
        rca_status="bounded",
        discovery_candidate_ids={"action-b"},
    )
    assert result["selected_action_id"] == "action-a"
    assert result["action_kind"] == "rca_evidence"


def test_resolved_rca_stops_without_selecting_an_action():
    result = select_rca_action([_action("action-a", 3, 1)], rca_status="confirmed")
    assert result["selected_action_id"] is None
    assert result["stop_reason"] == "resolved"


def test_id_collision_fails_closed():
    with pytest.raises(ValueError, match="collision"):
        select_rca_action([_action("candidate-a", 1, 1)], rca_status="bounded", discovery_candidate_ids={"candidate-a"})
