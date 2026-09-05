import json
from pathlib import Path

import scripts.run_dify_k8s_adaptive_coverage as adaptive_runner
from tools.dify_adaptive_coverage import select_next_action
from tools.llm_policy import build_policy_input, guard_policy_decision, parse_policy_output


def _candidate(candidate_id, level="baseline", cluster="cluster", target="api"):
    return {
        "candidate_id": candidate_id,
        "target": target,
        "fault_family": "network_delay",
        "parameter_level": level,
        "causal_cluster_id": cluster,
        "parameters": {"latency_ms": 100},
    }


def _row(tmp_path, candidate_id, result, repetition=1):
    root = tmp_path / f"{candidate_id}-{repetition}"
    root.mkdir()
    (root / "finding_report.json").write_text(
        json.dumps({"payload": {"result": result, "attestation": {"valid": True}}}),
        encoding="utf-8",
    )
    return {
        "candidate_id": candidate_id,
        "output": str(root),
        "repetition": repetition,
        "status": "live_completed",
        "cleanup_status": "verified",
    }


def _decision(action, candidate_id, reason="information value"):
    return {
        "action": action,
        "candidate_id": candidate_id,
        "reason": reason,
        "hypothesis": {
            "mechanism": "bounded mechanism",
            "expected_observations": ["oracle changes"],
            "missing_evidence": ["recovery"],
            "next_actions": ["run the candidate"],
        },
    }


def test_policy_input_contains_state_and_reusable_experience():
    candidates = [_candidate("base")]
    states = {"base": {"status": "untested", "valid_trials": 0}}
    request = build_policy_input(
        candidates,
        states,
        [],
        {"dynamic_unique_budget": 1},
        knowledge_cards=[{
            "id": "KB-1",
            "knowledge_status": "local_reusable",
            "target": "api",
            "test_node": {"family": "network_delay"},
            "mechanism_claim": "latency affects the business path",
        }],
        project_context={"project_id": "generic-project"},
    )

    assert request["project_context"]["project_id"] == "generic-project"
    assert request["candidates"][0]["state"]["status"] == "untested"
    assert request["candidates"][0]["required_action"] == "screen"
    assert request["knowledge_cards"][0]["id"] == "KB-1"


def test_policy_parser_rejects_unknown_candidate_and_final_claim():
    with __import__("pytest").raises(ValueError, match="unknown candidate_id"):
        parse_policy_output(json.dumps(_decision("screen", "unknown")), allowed_candidate_ids={"base"})

    invalid = _decision("screen", "base")
    invalid["runtime_verdict"] = "confirmed"
    with __import__("pytest").raises(ValueError, match="unsupported policy fields"):
        parse_policy_output(json.dumps(invalid), allowed_candidate_ids={"base"})


def test_guard_rejects_stop_until_baseline_and_confirmation_requirements_are_done():
    candidates = [_candidate("base"), _candidate("medium", level="medium")]
    states = {
        "base": {"status": "confirmation_pending", "anomaly_trials": 1, "valid_trials": 1},
        "medium": {"status": "untested", "anomaly_trials": 0, "valid_trials": 0},
    }
    decision = parse_policy_output(
        json.dumps({"action": "stop", "candidate_id": None, "reason": "stop"}),
        allowed_candidate_ids={"base", "medium"},
    )
    result = guard_policy_decision(
        decision,
        candidates,
        states,
        unique_used=1,
        effective_budget=2,
        min_repetitions=3,
        anomaly_results=set(),
        near_boundary_results=set(),
    )
    assert result["allowed"] is False
    assert result["reason"] == "confirmation_required"


def test_guard_prioritizes_pending_confirmation_over_escalation():
    candidates = [_candidate("base"), _candidate("medium", level="medium")]
    states = {
        "base": {"status": "confirmation_pending", "anomaly_trials": 1, "valid_trials": 1},
        "medium": {"status": "untested", "anomaly_trials": 0, "valid_trials": 0},
    }
    decision = parse_policy_output(
        json.dumps(_decision("confirm", "base")),
        allowed_candidate_ids={"base", "medium"},
    )
    result = guard_policy_decision(
        decision,
        candidates,
        states,
        unique_used=1,
        effective_budget=2,
        min_repetitions=3,
        anomaly_results=set(),
        near_boundary_results=set(),
    )
    assert result == {"allowed": True, "reason": "accepted"}


def test_guard_rejects_stop_until_parameter_audit_floor_is_done():
    candidates = [_candidate("base"), _candidate("low", level="low")]
    states = {
        "base": {"status": "screened_clean", "anomaly_trials": 0, "valid_trials": 1},
        "low": {"status": "untested", "anomaly_trials": 0, "valid_trials": 0},
    }
    decision = parse_policy_output(
        json.dumps({"action": "stop", "candidate_id": None, "reason": "stop"}),
        allowed_candidate_ids={"base", "low"},
    )

    result = guard_policy_decision(
        decision,
        candidates,
        states,
        unique_used=1,
        effective_budget=2,
        min_repetitions=3,
        anomaly_results=set(),
        near_boundary_results=set(),
        parameter_audit_ids={"low"},
    )

    assert result["allowed"] is False
    assert result["reason"] == "parameter_audit_required"


def test_guarded_llm_decision_controls_next_candidate(tmp_path):
    candidates = [_candidate("base"), _candidate("other", target="worker", cluster="other")]
    rows = [_row(tmp_path, "base", "response_observed")]

    def provider(request):
        assert request["knowledge_cards"]
        return _decision("screen", "other", "experience card leaves worker untested")

    result = select_next_action(
        candidates,
        rows,
        max_unique_hypotheses=2,
        policy_provider=provider,
        policy_mode="guarded",
        knowledge_cards=[{"id": "KB-1", "knowledge_status": "local_reusable"}],
    )

    assert result["decision_source"] == "llm"
    assert result["candidate"]["candidate_id"] == "other"
    assert result["action"] == "screen"
    assert result["llm_decision"]["hypothesis"]["mechanism"] == "bounded mechanism"


def test_shadow_records_llm_without_changing_executable_decision(tmp_path):
    candidates = [_candidate("base"), _candidate("other", target="worker", cluster="other")]
    rows = [_row(tmp_path, "base", "response_observed")]

    result = select_next_action(
        candidates,
        rows,
        max_unique_hypotheses=2,
        policy_provider=lambda _: _decision("screen", "other"),
        policy_mode="shadow",
    )

    assert result["decision_source"] == "deterministic_shadow"
    assert result["candidate"]["candidate_id"] == "other"
    assert result["llm_selected_candidate_id"] == "other"


def test_live_trial_persists_policy_after_run_engine_accepts_empty_output(tmp_path, monkeypatch):
    profile = tmp_path / "profile.json"
    profile.write_text("{}", encoding="utf-8")
    candidate = _candidate("base")

    monkeypatch.setattr(
        adaptive_runner,
        "_wait_for_environment",
        lambda *args, **kwargs: {"status": "ready_for_injection"},
    )

    def fake_candidate(_self, request):
        attempt_root = Path(request.output_root)
        assert list(attempt_root.iterdir()) == []
        return {"status": "live_completed", "cleanup_status": "verified"}

    monkeypatch.setattr(adaptive_runner.RunEngine, "run_candidate", fake_candidate)
    decision = {
        "action": "screen",
        "decision_source": "llm",
        "candidate": candidate,
    }

    result = adaptive_runner._live_trial(
        profile=profile,
        candidate=candidate,
        output_root=tmp_path / "adaptive",
        action="screen",
        repetition=1,
        seed=1001,
        kube_context="test",
        preflight_timeout=0,
        preflight_interval=0.01,
        max_trial_attempts=1,
        knowledge_root=tmp_path / "knowledge",
        policy_decision=decision,
    )

    policy_path = Path(result["output"]) / "policy_decision.json"
    assert result["status"] == "live_completed"
    assert json.loads(policy_path.read_text(encoding="utf-8"))["decision_source"] == "llm"
