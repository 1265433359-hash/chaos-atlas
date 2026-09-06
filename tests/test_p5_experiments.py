from __future__ import annotations

import pytest

from chaosatlas.capabilities.contracts import canonical_catalog_ids
from chaosatlas.experiments.p5 import (
    build_experiment_plan,
    build_hypothesis_record,
    build_issue_draft,
    build_knowledge_snapshot,
    build_p5_report,
    evaluate_experiment_evidence,
    P5RunCoordinator,
    summarize_cost,
)


def _bootstrap(status="blocked"):
    core, ext = canonical_catalog_ids()
    return {
        "project_capabilities": [
            {"fault_id": item, "catalog_scope": "core", "capability_status": status, "candidate_eligible": False}
            for item in core
        ] + [
            {"fault_id": item, "catalog_scope": "extension", "capability_status": status, "candidate_eligible": False}
            for item in ext
        ]
    }


def test_plan_preserves_41_denominator_and_statuses():
    bootstrap = _bootstrap()
    bootstrap["project_capabilities"][0]["capability_status"] = "canary_required"
    plan = build_experiment_plan(project_id="immich", project_revision="rev", capability_bootstrap=bootstrap)
    assert plan["catalog"] == {"core": 32, "extension": 9, "total": 41}
    assert plan["denominators"]["all_capabilities"] == 41
    assert plan["status_counts"]["blocked"] == 40
    assert plan["status_counts"]["canary_required"] == 1
    assert plan["execution_policy"]["faults_executed"] is False


def test_plan_rejects_missing_capability():
    bootstrap = _bootstrap()
    bootstrap["project_capabilities"].pop()
    with pytest.raises(ValueError, match="incomplete"):
        build_experiment_plan(project_id="x", project_revision="r", capability_bootstrap=bootstrap)


def test_hypothesis_is_falsifiable_and_advisory():
    record = build_hypothesis_record(
        hypothesis_id="h1", source_evidence_refs=["pod.json"], target_role="api", dependency_edge="api-db",
        fault_intent="pod_kill", approved_oracle_id="oracle-v3", expected_mechanism="retry gap",
        business_invariant="one object", predicted_observation="one retry creates duplicate", alternative_explanations=["queue delay"],
        falsifying_observation="exactly one object", parameter_tier="low", discriminating_next_action="read object by marker",
        knowledge_snapshot_id="snap", origin="llm_advisory",
    )
    assert record["claim_scope"] == "advisory"
    assert record["origin"] == "llm_advisory"
    assert len(record["hypothesis_sha256"]) == 64


def _attempts():
    baseline = {"role": "baseline", "status": "pass", "anomaly_observed": False}
    control = {"role": "control", "status": "pass", "anomaly_observed": False}
    reps = [
        {"role": "reproduction", "attempt_id": f"r{i}", "claim_scope": "real_runtime", "injection_confirmed": True, "anomaly_observed": True, "mechanism_status": "pass", "recovery_status": "pass", "cleanup_status": "pass", "causal_key": "k"}
        for i in range(1, 4)
    ]
    return [baseline, control, *reps]


def test_evidence_requires_three_reproductions_and_controls():
    result = evaluate_experiment_evidence(_attempts(), expected_causal_key="k", sensitive_review="passed")
    assert result["issue_eligible"] is True
    assert result["valid_reproduction_count"] == 3
    assert result["gates"]["paired_control_clean"] is True

    insufficient = evaluate_experiment_evidence(_attempts()[:-1], expected_causal_key="k", sensitive_review="passed")
    assert insufficient["issue_eligible"] is False
    assert "three_independent_reproductions" in insufficient["rejected_reason_codes"]


def test_issue_draft_is_blocked_until_all_gates_pass():
    evaluation = evaluate_experiment_evidence(_attempts(), expected_causal_key="k", sensitive_review="passed")
    draft = build_issue_draft(
        evaluation=evaluation, project_id="immich", project_revision="rev", title="candidate",
        expected="one object", actual="two objects", impact="duplicate", reproduction_command="chaosatlas run",
        run_refs=["runs/r1", "runs/r2", "runs/r3"], limitations=["candidate only"], attribution="application candidate",
    )
    assert draft["status"] == "pending_human_review"
    assert draft["submission"]["performed"] is False
    blocked = dict(evaluation, issue_eligible=False)
    with pytest.raises(ValueError, match="gate"):
        build_issue_draft(evaluation=blocked, project_id="x", project_revision="r", title="t", expected="e", actual="a", impact="i", reproduction_command="c", run_refs=["r"], limitations=["l"], attribution="a")


def test_snapshot_is_copy_and_report_is_read_only():
    cards = [{"id": "c1", "explanation": "x"}]
    snapshot = build_knowledge_snapshot(snapshot_id="s", project_id="p", project_revision="r", cards=cards)
    cards[0]["explanation"] = "mutated"
    assert snapshot["cards"][0]["explanation"] == "x"
    plan = build_experiment_plan(project_id="p", project_revision="r", capability_bootstrap=_bootstrap())
    report = build_p5_report(plans=[plan], real_evidence=False, costs=summarize_cost())
    assert report["evidence_status"] == "implementation_and_read_only_only"
    assert report["gates"]["real_fault_execution"] is False


def test_coordinator_uses_runengine_and_blocks_unapproved_live():
    class Engine:
        def __init__(self):
            self.calls = []
        def run_candidate(self, request):
            self.calls.append(request)
            return {"status": "dry_run_ready", "claim_scope": "planned", "injection_performed": False}
    class Request:
        mode = "live"
        candidate_id = "c1"
    engine = Engine()
    plan = build_experiment_plan(project_id="p", project_revision="r", capability_bootstrap=_bootstrap())
    result = P5RunCoordinator(engine).run(plan, [Request()])
    assert result["blocked_count"] == 1
    assert not engine.calls
