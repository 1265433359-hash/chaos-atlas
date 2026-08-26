import pytest

from tools.experiment_policy_schema import (
    STOP_REASONS,
    validate_policy_decision,
    validate_policy_state,
)


def _state() -> dict:
    return {
        "schema_version": "chaosatlas-experiment-policy-state-v1",
        "policy_version": "ig-stop-v1",
        "project_id": "demo",
        "project_commit": "a" * 40,
        "seed": 1001,
        "candidate_states": {
            "c1": {
                "causal_cluster_id": "cluster-1",
                "status": "unknown",
                "posterior": {"weakness": 0.33, "protected": 0.33, "below_threshold": 0.34},
                "evidence_quality": "none",
                "run_count": 0,
                "observed_outcomes": [],
                "last_result_sha256": None,
            }
        },
        "history": [],
        "input_sha256": "b" * 64,
    }


def test_valid_policy_state_is_accepted():
    assert validate_policy_state(_state())["valid"] is True


def test_invalid_probability_is_rejected():
    state = _state()
    state["candidate_states"]["c1"]["posterior"]["weakness"] = 1.2
    result = validate_policy_state(state)
    assert result["valid"] is False
    assert "posterior_out_of_range" in result["errors"]


def test_policy_decision_rejects_unknown_stop_reason():
    decision = {
        "schema_version": "chaosatlas-experiment-policy-decision-v1",
        "policy_version": "ig-stop-v1",
        "project_id": "demo",
        "seed": 1001,
        "input_sha256": "b" * 64,
        "selected_candidate_id": None,
        "stop_reason": "repeated",
        "scores": [],
    }
    result = validate_policy_decision(decision)
    assert result["valid"] is False
    assert "invalid_stop_reason" in result["errors"]
    assert "resolved" in STOP_REASONS
