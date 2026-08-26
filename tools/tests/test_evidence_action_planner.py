from __future__ import annotations

import json

from tools.evidence_action_planner import build_evidence_plan


def _inventory() -> dict:
    return {
        "project_id": "demo",
        "project_commit": "commit-1",
        "namespace": "demo-lab",
        "business_oracles": [{"id": "homepage", "service": "front-end", "remote_port": 80}],
    }


def _candidate(candidate_id: str = "candidate-1", *, recovery: dict | None = None) -> dict:
    return {
        "candidate_id": candidate_id,
        "target": "front-end",
        "target_kind": "deployment",
        "fault_family": "pod_kill",
        "operation": "pod_kill",
        "namespace": "demo-lab",
        "recovery_contract": recovery if recovery is not None else {
            "replacement_identity_required": True,
            "ready_required": True,
            "business_probe_required": True,
            "cleanup_required": True,
        },
    }


def _hypotheses(*, candidate_id: str = "candidate-1") -> dict:
    return {
        "candidate_ids": [candidate_id],
        "advisory_status": "completed",
        "advisory": {
            "hypotheses": [{
                "candidate_id": candidate_id,
                "mechanism": "singleton replacement may interrupt availability",
                "expected_observations": ["business oracle response"],
                "missing_evidence": ["deployment replicas", "pod events", "unknown model phrase"],
                "next_actions": ["collect scoped logs"],
            }],
            "global_missing_evidence": ["independent evidence"],
        },
    }


def test_build_evidence_plan_is_bounded_and_deterministic() -> None:
    candidates = {"status": "verified", "candidates": [_candidate(), _candidate("candidate-2")]}

    first = build_evidence_plan(_inventory(), candidates, _hypotheses(), candidate_budget=1)
    second = build_evidence_plan(_inventory(), candidates, _hypotheses(), candidate_budget=1)

    assert first["status"] == "planned"
    assert first["selection"]["candidate_ids"] == ["candidate-1"]
    assert first["input_sha256"] == second["input_sha256"]
    assert [item["action_id"] for item in first["actions"]] == [item["action_id"] for item in second["actions"]]
    assert all(item["read_only"] is True for item in first["actions"])
    assert first["actions"][0]["action_kind"] == "deployment_facts"
    assert "unknown model phrase" in first["unmapped_advisory"]
    assert first["runtime_experiment"]["admissible"] is True


def test_invalid_advisory_candidate_blocks_without_actions() -> None:
    candidates = {"status": "verified", "candidates": [_candidate()]}

    result = build_evidence_plan(_inventory(), candidates, _hypotheses(candidate_id="candidate-unknown"), candidate_budget=1)

    assert result["status"] == "blocked"
    assert result["actions"] == []
    assert result["runtime_experiment"]["admissible"] is False
    assert any("unknown candidate" in item for item in result["blocked_reasons"])


def test_missing_recovery_contract_fails_closed() -> None:
    candidates = {"status": "verified", "candidates": [_candidate(recovery={})]}

    result = build_evidence_plan(_inventory(), candidates, _hypotheses(), candidate_budget=1)

    assert result["status"] == "blocked"
    assert result["actions"] == []
    assert any("recovery contract" in item for item in result["blocked_reasons"])


def test_container_kill_accepts_container_restart_contract() -> None:
    candidate = _candidate()
    candidate["fault_family"] = "container_kill"
    candidate["recovery_contract"] = {
        "replacement_identity_required": False,
        "ready_required": True,
        "business_probe_required": True,
        "cleanup_required": True,
        "recovery_mode": "container_restart",
        "container_restart_required": True,
    }
    result = build_evidence_plan(
        {"status": "verified", "project_id": "p", "project_commit": "c"},
        {"status": "verified", "candidates": [candidate]},
        {"candidate_ids": [candidate["candidate_id"]]},
        candidate_budget=1,
    )
    assert result["status"] == "planned"
    assert result["runtime_experiment"]["admissible"] is True


def test_forbidden_advisory_action_text_is_never_executable() -> None:
    candidates = {"status": "verified", "candidates": [_candidate()]}
    hypotheses = _hypotheses()
    hypotheses["advisory"]["hypotheses"][0]["next_actions"] = ["kubectl delete namespace demo-lab"]

    result = build_evidence_plan(_inventory(), candidates, hypotheses, candidate_budget=1)

    assert result["status"] == "planned"
    serialized = json.dumps(result, ensure_ascii=True).lower()
    assert "kubectl delete" not in serialized
    assert all(item["action_kind"] in {
        "deployment_facts", "service_facts", "pod_state", "pod_events",
        "pod_logs", "business_baseline", "mechanism_evidence",
    } for item in result["actions"])


def test_service_action_keeps_service_target_separate_from_deployment_target() -> None:
    candidate = _candidate()
    candidate["service_target"] = "front-end-http"

    result = build_evidence_plan(
        _inventory(),
        {"status": "verified", "candidates": [candidate]},
        _hypotheses(),
        candidate_budget=1,
    )

    service_action = next(item for item in result["actions"] if item["action_kind"] == "service_facts")
    assert service_action["target"] == "front-end-http"
    assert service_action["deployment_target"] == "front-end"
