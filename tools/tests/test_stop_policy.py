from tools.experiment_policy import new_policy_state
from tools.stop_policy import evaluate_stop, plan_intensity_step


def _candidate(cid: str, status: str = "eligible") -> dict:
    return {
        "candidate_id": cid,
        "target": "station",
        "target_kind": "deployment",
        "fault_family": "network_delay",
        "status": status,
        "parameters": {"latency_ms": 500},
        "causal_cluster_id": f"cluster-{cid}",
        "estimated_cost": 1.0,
        "blast_radius": 1.0,
    }


def test_resolved_candidate_stops_with_resolved_reason():
    candidate = _candidate("c1")
    state = new_policy_state("demo", "a" * 40, 1001, [candidate])
    state["candidate_states"]["c1"]["posterior"] = {"weakness": 0.95, "protected": 0.03, "below_threshold": 0.02}
    state["candidate_states"]["c1"]["status"] = "weakness"
    result = evaluate_stop([candidate], state["candidate_states"], {"minimum_value_per_cost": 0.05})
    assert result["stop_reason"] == "resolved"


def test_repetition_alone_does_not_stop_when_boundary_value_remains():
    repeated = _candidate("repeated")
    boundary = _candidate("boundary")
    state = new_policy_state("demo", "a" * 40, 1001, [repeated, boundary])
    state["candidate_states"]["repeated"].update({"run_count": 4, "status": "below_threshold"})
    result = evaluate_stop([repeated, boundary], state["candidate_states"], {"boundary_candidate_ids": {"boundary"}, "minimum_value_per_cost": 0.05})
    assert result["stop_reason"] is None
    assert result["next_candidate_id"] == "boundary"


def test_intensity_step_moves_toward_known_boundary():
    result = plan_intensity_step([100, 500, 2000], observed=[100, 500], boundary=5000)
    assert result["next_value"] == 2000
