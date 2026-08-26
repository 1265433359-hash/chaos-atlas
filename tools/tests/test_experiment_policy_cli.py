from tools.experiment_policy_cli import select_handoff_hypotheses
from tools.experiment_policy import new_policy_state


def _static(candidate_id: str, target: str) -> dict:
    return {
        "candidate_id": candidate_id,
        "target": target,
        "target_kind": "deployment",
        "fault_family": "pod_kill",
        "status": "eligible",
        "parameters": {"mode": "one"},
        "causal_cluster_id": f"cluster-{candidate_id}",
        "estimated_cost": 1.0,
    }


def _hypothesis(hypothesis_id: str, target: str) -> dict:
    return {
        "hypothesis_id": hypothesis_id,
        "target": target,
        "target_kind": "deployment",
        "fault_family": "pod_kill",
        "parameters": {"mode": "one"},
        "hypothesis": "bounded availability claim",
        "expected_invariant": "business remains available",
        "expected_steady_state": "availableReplicas >= 1",
        "validation_plan": "baseline, inject, observe, recover, cleanup",
        "recovery_expectation": "replacement becomes Ready",
        "call_chain": [{"source": target, "target": target, "relation": "self", "evidence_ref": "topology"}],
        "weakness_surface": "availability",
    }


def test_shadow_preserves_legacy_hypotheses_and_records_policy_selection():
    static = [_static("candidate-a", "deployment:api"), _static("candidate-b", "deployment:db")]
    hypotheses = [_hypothesis("h-a", "deployment:api"), _hypothesis("h-b", "deployment:db")]
    state = new_policy_state("demo", "a" * 40, 1001, static)
    result = select_handoff_hypotheses(static, hypotheses, state, mode="shadow", budget=1)
    assert result["compiled_hypotheses"] == hypotheses
    assert result["policy_selected_hypothesis_ids"]
    assert result["policy_mode"] == "shadow"


def test_guarded_returns_only_allow_listed_policy_hypotheses():
    static = [_static("candidate-a", "deployment:api"), _static("candidate-b", "deployment:db")]
    hypotheses = [_hypothesis("h-a", "deployment:api"), _hypothesis("h-b", "deployment:db")]
    state = new_policy_state("demo", "a" * 40, 1001, static)
    result = select_handoff_hypotheses(static, hypotheses, state, mode="guarded", budget=1)
    assert len(result["compiled_hypotheses"]) == 1
    assert result["compiled_hypotheses"][0]["hypothesis_id"] in {"h-a", "h-b"}


def test_unknown_hypothesis_target_fails_closed_in_guarded_mode():
    static = [_static("candidate-a", "deployment:api")]
    hypotheses = [_hypothesis("h-unknown", "deployment:missing")]
    state = new_policy_state("demo", "a" * 40, 1001, static)
    result = select_handoff_hypotheses(static, hypotheses, state, mode="guarded", budget=1)
    assert result["compiled_hypotheses"] == []
    assert result["stop_reason"] == "blocked"
    assert result["unmatched_hypothesis_ids"] == ["h-unknown"]


def test_blocked_candidate_is_reported_as_blocked_not_low_value():
    static = [_static("candidate-a", "deployment:api")]
    static[0]["status"] = "blocked"
    hypotheses = [_hypothesis("h-a", "deployment:api")]
    state = new_policy_state("demo", "a" * 40, 1001, static)
    result = select_handoff_hypotheses(static, hypotheses, state, mode="guarded", budget=1)
    assert result["compiled_hypotheses"] == []
    assert result["stop_reason"] == "blocked"
