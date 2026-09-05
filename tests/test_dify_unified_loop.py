import json
from pathlib import Path

from tools.dify_chatflow_oracle import DifyChatflowOracle
from chaosatlas.orchestration.batch import build_live_batch_plan
from tools.experiment_policy import new_policy_state
from tools.experiment_policy_feedback import ingest_runtime_result
from tools.feedback_protocol import classify_outcome
from tools.policy_controller import normalize_runtime_feedback
from tools.rca_loop import evaluate_knowledge_promotion
from tools.stop_policy import evaluate_stop
from chaosatlas.orchestration.batch import summarize_batch_results
from tools.run_chaos_experiment import wait_for_container_ready, wait_for_target_ready


def test_chatflow_oracle_keeps_response_text_out_of_sample():
    ok, sample = DifyChatflowOracle._success({
        "status_code": 200,
        "latency_ms": 12,
        "body": json.dumps({
            "answer": "private answer text",
            "message_id": "message-1",
            "mode": "blocking",
        }),
    })

    assert ok is True
    assert sample["response_shape"] is True
    assert "answer" not in sample
    assert "private answer text" not in json.dumps(sample)


def test_dify_business_path_oracle_covers_all_discovered_candidates():
    profile = {
        "project_id": "dify-kubernetes",
        "project_commit": "test-commit",
        "namespace_policy": {"allowed_namespaces": ["lab"]},
        "business_oracles": [{
            "id": "chatflow",
            "kind": "dify_chatflow",
            "service": "dify-k8s",
            "remote_port": 80,
            "entrypoint": "/v1/chat-messages",
            "success_contract": "dify_chatflow_response",
            "candidate_scope": "business_path",
        }],
        "runtime_contract": {"supported_fault_families": ["pod_kill"]},
    }

    class Adapter:
        def inventory(self):
            return {
                "project_id": "dify-kubernetes",
                "project_commit": "test-commit",
                "namespace": "lab",
                "deployments": [],
                "services": [],
                "dependencies": [],
            }

        def detect_server_deployment(self, inventory):
            return {"status": "verified", "deployment_nodes": [], "candidates": []}

        def map_test_nodes(self, detection):
            return {
                "status": "verified",
                "candidates": [
                    {"candidate_id": "c-api", "target": "dify-k8s-api", "service_target": "dify-k8s-api", "fault_family": "pod_kill"},
                    {"candidate_id": "c-worker", "target": "dify-k8s-worker", "service_target": "dify-k8s-worker", "fault_family": "pod_kill"},
                ],
            }

    result = build_live_batch_plan(profile=profile, adapter=Adapter())

    assert result["status"] == "ready"
    assert result["oracle"]["candidate_scope"] == "business_path"
    assert result["candidate_ids"] == ["c-api", "c-worker"]


def test_stop_policy_uses_posterior_and_budget_selection():
    candidates = [
        {"candidate_id": "candidate-a", "estimated_cost": 1, "decision_impact": 1},
        {"candidate_id": "candidate-b", "estimated_cost": 1, "decision_impact": 1},
    ]
    state = new_policy_state("project", "commit", 1, candidates)

    decision = evaluate_stop(candidates, state["candidate_states"], {})
    assert decision["stop_reason"] is None
    assert decision["next_candidate_id"] in {"candidate-a", "candidate-b"}

    resolved = {
        key: {
            **value,
            "posterior": {"weakness": 0.95, "protected": 0.03, "below_threshold": 0.02},
        }
        for key, value in state["candidate_states"].items()
    }
    assert evaluate_stop(candidates, resolved, {})["stop_reason"] == "resolved"


def test_complete_bounded_chat_observation_updates_policy_posterior():
    candidate = {
        "candidate_id": "candidate-chat-observed",
        "estimated_cost": 1,
        "decision_impact": 1,
    }
    state = new_policy_state("dify-kubernetes", "commit", 1, [candidate])
    feedback = normalize_runtime_feedback({
        "project_id": "dify-kubernetes",
        "project_commit": "commit",
        "candidate_id": candidate["candidate_id"],
        "status": "live_completed",
        "classification": "response_observed",
        "rca_status": "bounded",
        "cleanup_status": "verified",
        "evidence_refs": ["runtime/business/chat.json"],
        "evidence_available_count": 1,
        "attestation": {
            "valid": True,
            "comparison_eligible": True,
            "independent_oracle": True,
            "baseline": True,
            "injection": True,
            "observation": True,
            "recovery": True,
            "cleanup": True,
        },
    })

    assert feedback["classification"] == "latent_risk"
    assert feedback["eligible"] is True

    updated = ingest_runtime_result(state, feedback)
    row = updated["candidate_states"][candidate["candidate_id"]]
    assert row["status"] == "below_threshold"
    assert row["run_count"] == 1
    assert row["posterior"]["below_threshold"] > row["posterior"]["weakness"]


def test_bounded_observation_without_valid_oracle_cannot_update_policy():
    feedback = normalize_runtime_feedback({
        "candidate_id": "candidate-chat-invalid-oracle",
        "status": "live_completed",
        "classification": "response_observed",
        "rca_status": "bounded",
        "cleanup_status": "verified",
        "evidence_refs": ["runtime/business/chat.json"],
        "evidence_available_count": 1,
    })

    assert feedback["classification"] == "unsupported"
    assert feedback["eligible"] is False
    assert feedback["eligibility_reason"] == "lifecycle_incomplete"


def test_cli_script_bootstraps_repository_root_for_batch_imports():
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "tools/chaosatlas.py", "--help"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
        check=False,
    )

    assert result.returncode == 0
    assert "Evidence-constrained ChaosAtlas orchestration" in result.stdout


def test_weakness_requires_three_reproductions():
    evidence = {key: True for key in (
        "baseline", "injection", "observation", "recovery", "cleanup", "independent_oracle"
    )}
    result = {
        "oracle_label": "weakness",
        "evidence": evidence,
        "valid_reproductions": 2,
    }

    assert classify_outcome(result) == "unsupported"
    result["valid_reproductions"] = 3
    assert classify_outcome(result) == "confirmed_weakness"


def test_knowledge_promotion_requires_three_reproductions_without_counterfactual_bypass():
    common = {
        "current": "provisional",
        "weakness_status": "confirmed",
        "rca_status": "confirmed",
        "valid_counterfactuals": 1,
        "lifecycle_complete": True,
        "direct_evidence": True,
        "applicability_complete": True,
        "regression_complete": True,
        "contradiction": False,
    }

    two = evaluate_knowledge_promotion(**common, valid_reproductions=2)
    three = evaluate_knowledge_promotion(**common, valid_reproductions=3)

    assert two["allowed"] is False
    assert two["reason"] == "reproduction_gate_incomplete"
    assert three["allowed"] is True


def test_policy_controller_does_not_confirm_two_degradations():
    feedback = normalize_runtime_feedback({
        "candidate_id": "candidate-degraded",
        "status": "live_completed",
        "classification": "availability_degraded",
        "rca_status": "bounded",
        "cleanup_status": "verified",
        "valid_reproductions": 2,
        "evidence_refs": ["runtime/business/chat.json"],
        "evidence_available_count": 1,
        "attestation": {
            "valid": True,
            "comparison_eligible": True,
            "independent_oracle": True,
            "baseline": True,
            "injection": True,
            "observation": True,
            "recovery": True,
            "cleanup": True,
        },
    })

    assert feedback["classification"] == "unsupported"
    assert feedback["eligible"] is False
    assert feedback["eligibility_reason"] == "reproduction_gate_incomplete"


def test_batch_summary_requires_three_reproductions_for_findings_and_rca():
    attestation = {
        "valid": True,
        "comparison_eligible": True,
        "independent_oracle": True,
        "baseline": True,
        "injection": True,
        "observation": True,
        "recovery": True,
        "cleanup": True,
    }
    results = [
        {
            "candidate_id": "candidate-two",
            "status": "live_completed",
            "cleanup_status": "verified",
            "classification": "availability_degraded",
            "rca_status": "confirmed",
            "valid_reproductions": 2,
            "evidence_refs": ["runtime/business/candidate-two.json"],
            "evidence_available_count": 1,
            "attestation": attestation,
        },
        {
            "candidate_id": "candidate-three",
            "status": "live_completed",
            "cleanup_status": "verified",
            "classification": "availability_degraded",
            "rca_status": "confirmed",
            "valid_reproductions": 3,
            "evidence_refs": ["runtime/business/candidate-three.json"],
            "evidence_available_count": 1,
            "attestation": attestation,
        },
    ]

    summary = summarize_batch_results(results, planned_count=2)

    assert summary["confirmed_finding_count"] == 1
    assert summary["rca_confirmed_count"] == 1
    assert summary["stable_reproduction_required"] == 3
    assert summary["stable_reproduction_verified_count"] == 1
    assert summary["reproduction_gate_incomplete_count"] == 1


def test_recovery_probe_defaults_to_three_stable_checks():
    import inspect

    assert inspect.signature(wait_for_target_ready).parameters["stable_checks"].default == 3
    assert inspect.signature(wait_for_container_ready).parameters["stable_checks"].default == 3
