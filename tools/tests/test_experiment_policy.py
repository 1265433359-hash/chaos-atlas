from tools.experiment_policy import (
    new_policy_state,
    posterior_entropy,
    score_experiment,
    select_next_experiment,
    update_candidate_state,
)


def _candidate(cid: str, *, status: str = "eligible", family: str = "network_delay", value: int = 0) -> dict:
    return {
        "candidate_id": cid,
        "target": "station",
        "target_kind": "deployment",
        "fault_family": family,
        "status": status,
        "parameters": {"latency_ms": 500},
        "base_score": value,
        "causal_cluster_id": f"cluster-{cid}",
        "causal_identity": {"target": "station", "fault_family": family},
        "estimated_cost": 1.0,
        "blast_radius": 1.0,
    }


def test_new_state_has_one_unknown_row_per_candidate():
    state = new_policy_state("demo", "a" * 40, 1001, [_candidate("c1"), _candidate("c2")])
    assert set(state["candidate_states"]) == {"c1", "c2"}
    assert all(item["status"] == "unknown" for item in state["candidate_states"].values())


def test_deterministic_outcome_updates_state_without_llm_verdict():
    state = new_policy_state("demo", "a" * 40, 1001, [_candidate("c1")])
    updated = update_candidate_state(state, {"candidate_id": "c1", "classification": "confirmed_weakness", "result_sha256": "c" * 64})
    assert updated["candidate_states"]["c1"]["status"] == "weakness"
    assert updated["candidate_states"]["c1"]["run_count"] == 1


def test_repeated_same_outcome_increases_decision_confidence():
    state = new_policy_state("demo", "a" * 40, 1001, [_candidate("c1")])
    update_candidate_state(state, {"candidate_id": "c1", "classification": "confirmed_weakness", "result_sha256": "1" * 64})
    update_candidate_state(state, {"candidate_id": "c1", "classification": "confirmed_weakness", "result_sha256": "2" * 64})

    posterior = state["candidate_states"]["c1"]["posterior"]
    assert posterior["weakness"] > 0.90
    assert state["candidate_states"]["c1"]["run_count"] == 2


def test_boundary_uncertainty_outranks_repeated_low_value_candidate():
    candidates = [_candidate("boundary"), _candidate("repeated")]
    states = new_policy_state("demo", "a" * 40, 1001, candidates)["candidate_states"]
    states["repeated"].update({"run_count": 3, "status": "below_threshold", "evidence_quality": "complete"})
    states["boundary"].update({"status": "unknown", "evidence_quality": "partial"})
    context = {"boundary_candidate_ids": {"boundary"}, "seen_cluster_ids": {"cluster-repeated"}, "budget_remaining": 2}
    selected = select_next_experiment(candidates, states, context, budget=2)
    assert selected["candidate_id"] == "boundary"


def test_entropy_is_zero_for_certain_distribution():
    assert posterior_entropy({"weakness": 1.0, "protected": 0.0, "below_threshold": 0.0}) == 0.0


def test_registry_bonus_is_optional_and_bounded():
    candidate = _candidate("c1")
    state = new_policy_state("demo", "a" * 40, 1001, [candidate])["candidate_states"]["c1"]
    plain = score_experiment(candidate, state)
    informed = score_experiment(candidate, state, {"registry_priority_bonus": {"c1": 0.9}, "registry_priority_bonus_cap": 0.25})

    assert plain["components"].get("registry_priority_bonus") == 0.0
    assert informed["components"]["registry_priority_bonus"] == 0.25
    assert informed["value"] - plain["value"] == 0.25


def test_registry_bonus_ignores_unknown_negative_and_nonfinite_values():
    candidate = _candidate("c1")
    state = new_policy_state("demo", "a" * 40, 1001, [candidate])["candidate_states"]["c1"]
    result = score_experiment(
        candidate,
        state,
        {"registry_priority_bonus": {"unknown": 0.5, "c1": -1}, "registry_priority_bonus_cap": 0.25},
    )
    assert result["components"]["registry_priority_bonus"] == 0.0
