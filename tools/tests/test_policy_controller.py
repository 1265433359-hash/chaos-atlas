from __future__ import annotations

from tools.experiment_policy import new_policy_state
from tools.policy_controller import PolicyController, normalize_runtime_feedback


def _candidate(candidate_id: str) -> dict:
    return {
        "candidate_id": candidate_id,
        "target": "front-end",
        "target_kind": "deployment",
        "fault_family": "pod_kill",
        "status": "eligible",
        "estimated_cost": 1.0,
        "blast_radius": 0.0,
        "canonical_signature": f"sig-{candidate_id}",
    }


def test_guarded_controller_selects_one_round_then_excludes_attempted_candidate():
    candidates = [_candidate("candidate-a"), _candidate("candidate-b")]
    state = new_policy_state("demo", "a" * 40, 1001, candidates)
    controller = PolicyController(candidates, state, mode="guarded", budget=1)

    first = controller.next_decision()
    assert first["candidate_id"] == "candidate-a"
    assert first["stop_reason"] is None

    second = controller.next_decision(attempted_candidate_ids={"candidate-a"})
    assert second["candidate_id"] == "candidate-b"
    assert second["stop_reason"] is None


def test_guarded_controller_stops_before_executor_when_policy_reports_stop():
    candidate = _candidate("candidate-a")
    state = new_policy_state("demo", "a" * 40, 1001, [candidate])
    state["candidate_states"]["candidate-a"]["status"] = "blocked"
    controller = PolicyController([candidate], state, mode="guarded", budget=1)

    decision = controller.next_decision()

    assert decision["candidate_id"] is None
    assert decision["stop_reason"] == "blocked"
    assert decision["execution_candidate_ids"] == []


def test_shadow_controller_records_policy_stop_but_keeps_legacy_candidate_execution():
    candidate = _candidate("candidate-a")
    state = new_policy_state("demo", "a" * 40, 1001, [candidate])
    state["candidate_states"]["candidate-a"]["status"] = "blocked"
    controller = PolicyController([candidate], state, mode="shadow", budget=1)

    decision = controller.next_decision()

    assert decision["stop_reason"] == "blocked"
    assert decision["candidate_id"] == "candidate-a"
    assert decision["execution_candidate_ids"] == ["candidate-a"]


def test_normalize_runtime_feedback_requires_verified_cleanup_and_complete_evidence():
    feedback = normalize_runtime_feedback(
        {
            "candidate_id": "candidate-a",
            "project_id": "demo",
            "project_commit": "a" * 40,
            "round_id": "round-1",
            "canonical_signature": "sig-candidate-a",
            "status": "live_completed",
            "cleanup_status": "failed",
            "classification": "availability_degraded",
            "rca_status": "confirmed",
            "evidence_quality": "complete",
        }
    )

    assert feedback["classification"] == "unsupported"
    assert feedback["eligible"] is False
    assert feedback["eligibility_reason"] == "cleanup_not_verified"


def test_normalize_runtime_feedback_does_not_promote_environment_blocked():
    feedback = normalize_runtime_feedback(
        {
            "candidate_id": "candidate-a",
            "status": "environment_blocked",
            "error": "namespace unavailable",
        }
    )

    assert feedback["classification"] == "environment_blocked"
    assert feedback["eligible"] is False
