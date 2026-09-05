import json
from pathlib import Path

import scripts.run_dify_k8s_adaptive_coverage as adaptive_runner
from tools.dify_adaptive_coverage import build_coverage_report, select_next_action


def _candidate(candidate_id, level="baseline", cluster="cluster", target="api"):
    return {
        "candidate_id": candidate_id,
        "target": target,
        "fault_family": "network_delay",
        "parameter_level": level,
        "causal_cluster_id": cluster,
    }


def _row(tmp_path, candidate_id, result, repetition=1):
    root = tmp_path / f"{candidate_id.replace(':', '-')}-{repetition}"
    root.mkdir()
    payload = {
        "payload": {
            "result": result,
            "attestation": {"valid": True},
        }
    }
    (root / "finding_report.json").write_text(json.dumps(payload), encoding="utf-8")
    return {"candidate_id": candidate_id, "output": str(root), "repetition": repetition, "status": "live_completed", "cleanup_status": "verified"}


def test_clean_baseline_does_not_escalate(tmp_path):
    candidates = [_candidate("base"), _candidate("low", "low")]
    rows = [_row(tmp_path, "base", "response_observed")]

    action = select_next_action(candidates, rows, max_unique_hypotheses=2)

    assert action["action"] is None
    assert action["stop_reason"] == "low_expected_value"


def test_parameter_audit_floor_escalates_clean_baseline_once(tmp_path):
    candidates = [
        _candidate("base"),
        _candidate("low", "low"),
        _candidate("medium", "medium"),
    ]
    rows = [_row(tmp_path, "base", "response_observed")]
    policy = {
        "parameter_audit": {
            "enabled": True,
            "min_levels_per_cluster": 1,
            "preferred_levels": ["low", "medium"],
        }
    }

    action = select_next_action(
        candidates,
        rows,
        max_unique_hypotheses=None,
        policy_config=policy,
    )
    report = build_coverage_report(candidates, rows, policy_config=policy)

    assert action["action"] == "escalate"
    assert action["selection_reason"] == "parameter_audit_floor"
    assert action["candidate"]["candidate_id"] == "low"
    assert report["budget_plan"]["parameter_audit_count"] == 1
    assert report["budget_plan"]["parameter_audit_ids"] == ["low"]


def test_parameter_audit_floor_stops_after_one_clean_parameter(tmp_path):
    candidates = [
        _candidate("base"),
        _candidate("low", "low"),
        _candidate("medium", "medium"),
    ]
    rows = [
        _row(tmp_path, "base", "response_observed"),
        _row(tmp_path, "low", "response_observed"),
    ]
    policy = {
        "parameter_audit": {
            "enabled": True,
            "min_levels_per_cluster": 1,
            "preferred_levels": ["low", "medium"],
        }
    }

    action = select_next_action(
        candidates,
        rows,
        max_unique_hypotheses=None,
        policy_config=policy,
    )
    report = build_coverage_report(candidates, rows, policy_config=policy)

    assert action["action"] is None
    assert action["stop_reason"] == "low_expected_value"
    assert report["budget_plan"]["parameter_audit_count"] == 0


def test_first_anomaly_enters_confirmation_before_escalation(tmp_path):
    candidates = [_candidate("base"), _candidate("low", "low"), _candidate("other", "baseline", "other-cluster")]
    rows = [_row(tmp_path, "base", "availability_degraded")]

    action = select_next_action(candidates, rows, max_unique_hypotheses=3)

    assert action["action"] == "confirm"
    assert action["candidate"]["candidate_id"] == "base"


def test_confirmation_is_not_blocked_by_unique_budget(tmp_path):
    candidates = [_candidate("base"), _candidate("low", "low")]
    rows = [_row(tmp_path, "base", "availability_degraded")]

    action = select_next_action(candidates, rows, max_unique_hypotheses=1)

    assert action["action"] == "confirm"
    assert action["unique_hypotheses_remaining"] == 0


def test_baseline_selection_rotates_to_uncovered_service(tmp_path):
    candidates = [
        _candidate("api-a", target="api-a"),
        _candidate("api-b", target="api-b"),
        _candidate("api-a-2", target="api-a", cluster="other"),
    ]
    rows = [_row(tmp_path, "api-a", "response_observed")]

    action = select_next_action(candidates, rows, max_unique_hypotheses=3)

    assert action["action"] == "screen"
    assert action["candidate"]["candidate_id"] == "api-b"


def test_auto_budget_is_derived_from_remaining_baseline_work(tmp_path):
    candidates = [_candidate("base"), _candidate("low", "low"), _candidate("other", target="worker", cluster="other")]
    rows = [_row(tmp_path, "base", "response_observed")]

    action = select_next_action(candidates, rows, max_unique_hypotheses=None)

    assert action["action"] == "screen"
    assert action["candidate"]["candidate_id"] == "other"
    assert action["budget_mode"] == "auto"
    assert action["budget_snapshot"]["remaining_unique_work"] == 1


def test_failed_trial_does_not_consume_budget_or_repeat_failed_candidate(tmp_path):
    candidates = [_candidate("base"), _candidate("other", target="worker", cluster="other")]
    failed_root = tmp_path / "failed"
    failed_root.mkdir()
    rows = [{
        "candidate_id": "base",
        "output": str(failed_root),
        "repetition": 1,
        "status": "apply_failed",
        "cleanup_status": "blocked",
    }]

    action = select_next_action(candidates, rows, max_unique_hypotheses=None)

    assert action["action"] == "screen"
    assert action["candidate"]["candidate_id"] == "other"
    assert action["budget_snapshot"]["unique_hypotheses_seen"] == 0


def test_exhausted_environment_block_is_quarantined_without_consuming_budget(tmp_path):
    candidates = [_candidate("blocked"), _candidate("other", target="worker", cluster="other")]
    root = tmp_path / "blocked"
    root.mkdir()
    rows = [{
        "candidate_id": "blocked",
        "output": str(root),
        "repetition": 1,
        "attempt": 3,
        "status": "injection_not_confirmed",
        "cleanup_status": "verified",
    }]

    action = select_next_action(candidates, rows, max_unique_hypotheses=None)
    report = build_coverage_report(candidates, rows)

    assert action["action"] == "screen"
    assert action["candidate"]["candidate_id"] == "other"
    assert report["candidate_states"]["blocked"]["status"] == "environment_blocked"
    assert report["budget_plan"]["unique_hypotheses_seen"] == 0


def test_only_exhausted_environment_blocks_stop_explicitly(tmp_path):
    candidates = [_candidate("blocked")]
    root = tmp_path / "blocked"
    root.mkdir()
    rows = [{
        "candidate_id": "blocked",
        "output": str(root),
        "repetition": 1,
        "attempt": 3,
        "status": "injection_not_confirmed",
        "cleanup_status": "verified",
    }]

    action = select_next_action(candidates, rows, max_unique_hypotheses=None)

    assert action["action"] is None
    assert action["stop_reason"] == "environment_blocked"


def test_apply_failure_is_terminal_for_candidate_selection(tmp_path):
    candidates = [_candidate("failed"), _candidate("other", target="worker", cluster="other")]
    root = tmp_path / "failed"
    root.mkdir()
    rows = [{
        "candidate_id": "failed",
        "output": str(root),
        "repetition": 1,
        "attempt": 1,
        "status": "apply_failed",
        "cleanup_status": "verified",
    }]

    action = select_next_action(candidates, rows, max_unique_hypotheses=None)

    assert action["action"] == "screen"
    assert action["candidate"]["candidate_id"] == "other"


def test_reusable_experience_never_skips_an_untested_baseline(tmp_path):
    candidates = [_candidate("base"), _candidate("low", "low")]
    cards = [{
        "id": "KB-weak",
        "status": "local_reusable",
        "knowledge_status": "local_reusable",
        "target": "api",
        "test_node": {"family": "network_delay", "target": "api"},
        "weakness_status": "confirmed",
        "valid_reproductions": 3,
    }]

    action = select_next_action(candidates, [], max_unique_hypotheses=None, knowledge_cards=cards)

    assert action["action"] == "screen"
    assert action["candidate"]["candidate_id"] == "base"


def test_reusable_experience_keeps_one_parameter_audit_then_defers_rest(tmp_path):
    candidates = [_candidate("base"), _candidate("low", "low"), _candidate("medium", "medium")]
    cards = [{
        "id": "KB-weak",
        "status": "local_reusable",
        "knowledge_status": "local_reusable",
        "target": "api",
        "test_node": {"family": "network_delay", "target": "api"},
        "weakness_status": "confirmed",
        "valid_reproductions": 3,
    }]
    rows = [
        _row(tmp_path, "base", "availability_degraded", 1),
        _row(tmp_path, "base", "availability_degraded", 2),
        _row(tmp_path, "base", "availability_degraded", 3),
        _row(tmp_path, "low", "response_observed", 1),
    ]

    action = select_next_action(candidates, rows, max_unique_hypotheses=None, knowledge_cards=cards)
    report = build_coverage_report(candidates, rows, cards)

    assert action["action"] is None
    assert action["stop_reason"] == "low_expected_value"
    assert report["candidate_states"]["medium"]["experience_disposition"] == "deferred_by_experience"
    assert report["budget_plan"]["triggered_parameter_count"] == 0
    assert report["experience_summary"]["deferred_parameter_candidates"] == 1


def test_policy_knowledge_normalizes_profile_commit_for_retrieval(tmp_path):
    profile = {
        "project_id": "dify-kubernetes",
        "project_commit": "dify-k8s-minikube-20260901",
    }
    card = {
        "id": "KB-WEAK",
        "project": "dify-kubernetes",
        "project_commit": "37f2f83d6c058c86545fab11d1ad07ac09e0af1a",
        "knowledge_status": "local_reusable",
        "status": "local_reusable",
        "target": "api",
        "test_node": {"family": "network_delay", "target": "api"},
        "weakness_status": "confirmed",
        "valid_reproductions": 3,
    }
    root = tmp_path / "knowledge"
    root.mkdir()
    (root / "KB-WEAK.json").write_text(json.dumps(card), encoding="utf-8")

    from scripts.run_dify_k8s_adaptive_coverage import _policy_knowledge

    cards = _policy_knowledge(profile, [_candidate("base")], root)

    assert [item["id"] for item in cards] == ["KB-WEAK"]


def test_stable_anomalous_baseline_escalates_parameter_ladder(tmp_path):
    candidates = [_candidate("base"), _candidate("low", "low"), _candidate("other", "baseline", "other-cluster")]
    rows = [
        _row(tmp_path, "base", "availability_degraded", 1),
        _row(tmp_path, "base", "availability_degraded", 2),
        _row(tmp_path, "base", "availability_degraded", 3),
    ]

    action = select_next_action(candidates, rows, max_unique_hypotheses=3)

    assert action["action"] == "escalate"
    assert action["candidate"]["candidate_id"] == "low"


def test_coverage_reports_base_parameter_and_stable_rates(tmp_path):
    candidates = [_candidate("base"), _candidate("low", "low")]
    rows = [_row(tmp_path, "base", "availability_degraded", 1), _row(tmp_path, "base", "availability_degraded", 2), _row(tmp_path, "base", "availability_degraded", 3)]

    report = build_coverage_report(candidates, rows)

    assert report["base_coverage"] == {"total": 1, "covered": 1, "rate": 1.0}
    assert report["parameter_coverage"] == {"total": 1, "covered": 0, "rate": 0.0}
    assert report["stable_reproduction_coverage"]["stable"] == 1
    assert report["causal_clusters"]["cluster"]["status"] == "stable_weakness"


def test_live_loop_reuses_history_and_only_confirms_pending_anomaly(tmp_path, monkeypatch):
    profile = Path("projects/dify-kubernetes/profile.json")
    candidates = [_candidate("base"), _candidate("low", "low")]
    history_root = tmp_path / "history"
    history_root.mkdir()
    (history_root / "finding_report.json").write_text(
        json.dumps({"payload": {"result": "availability_degraded", "attestation": {"valid": True}}}),
        encoding="utf-8",
    )
    history = [{
        "candidate_id": "base",
        "output": str(history_root),
        "repetition": 1,
        "status": "live_completed",
        "cleanup_status": "verified",
    }]
    calls = []

    def fake_trial(**kwargs):
        calls.append(kwargs["candidate"]["candidate_id"])
        root = tmp_path / f"live-{len(calls)}"
        root.mkdir()
        (root / "finding_report.json").write_text(
            json.dumps({"payload": {"result": "availability_degraded", "attestation": {"valid": True}}}),
            encoding="utf-8",
        )
        return {
            "action": kwargs["action"],
            "candidate_id": kwargs["candidate"]["candidate_id"],
            "status": "live_completed",
            "output": str(root),
            "cleanup_status": "verified",
            "repetition": kwargs["repetition"],
        }

    monkeypatch.setattr(adaptive_runner, "_candidate_list", lambda profile, context, target: candidates)
    monkeypatch.setattr(adaptive_runner, "_live_trial", fake_trial)

    result = adaptive_runner._run_adaptive_live(
        profile_path=profile,
        history_rows=history,
        output_root=tmp_path / "adaptive",
        knowledge_root=tmp_path / "knowledge",
        kube_context="test",
        target="all",
        max_unique_hypotheses=1,
        max_actions=5,
        approve_live=True,
        preflight_timeout=0,
        preflight_interval=0.01,
        max_trial_attempts=1,
    )

    assert calls == ["base", "base"]
    assert result["action_count"] == 2
    assert result["stop_reason"] == "budget_exhausted"
    assert result["coverage"]["candidate_states"]["base"]["anomaly_trials"] == 3


def test_history_candidate_ids_are_aligned_across_rollouts():
    rows = [{
        "candidate_id": "server:deployment:old-hash:config_drift",
        "target": "api",
        "fault_family": "config_drift",
        "parameter_level": "baseline",
    }]
    candidates = [{
        "candidate_id": "server:deployment:new-hash:config_drift",
        "target": "api",
        "fault_family": "config_drift",
        "parameter_level": "baseline",
    }]

    aligned = adaptive_runner._align_history_rows(rows, candidates)

    assert aligned[0]["candidate_id"] == "server:deployment:new-hash:config_drift"
    assert aligned[0]["historical_candidate_id"] == "server:deployment:old-hash:config_drift"
