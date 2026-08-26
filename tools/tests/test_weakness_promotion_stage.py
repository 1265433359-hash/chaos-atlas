from __future__ import annotations

import json

from tools.weakness_promotion_stage import (
    promote_from_history,
    select_history_children,
)


def _write_run(
    root,
    *,
    run_id: str,
    target: str = "front-end",
    family: str = "pod_kill",
    result: str = "availability_degraded",
    rca_status: str = "confirmed",
    project_commit: str = "a" * 40,
    seed: int = 1001,
    contradiction: bool = False,
) -> None:
    root.mkdir(parents=True)
    (root / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "project_id": "sock-shop",
                "project_commit": project_commit,
                "seed": seed,
            }
        ),
        encoding="utf-8",
    )
    (root / "classify.json").write_text(
        json.dumps(
            {
                "payload": {
                    "result": result,
                    "attestation": {
                        "baseline": True,
                        "injection": True,
                        "observation": True,
                        "recovery": True,
                        "cleanup": True,
                        "independent_oracle": True,
                        "valid": True,
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    (root / "rca_report.json").write_text(
        json.dumps(
            {
                "payload": {
                    "project_id": "sock-shop",
                    "project_commit": project_commit,
                    "case_family": "native_deployment_pod_kill",
                    "weakness_id": "WS-sock-shop-front-end-pod-kill-intent",
                    "weakness_status": "candidate",
                    "rca_status": rca_status,
                    "evidence_refs": [f"runtime/{run_id}/business.json"],
                    "symptom": {"oracle": "HTTP / on front-end"},
                    "test_node": {
                        "target": target,
                        "target_kind": "deployment",
                        "target_role": target,
                        "family": family,
                        "operation": family,
                        "parameters": {},
                    },
                    "hypotheses": [
                        {
                            "hypothesis_id": "server:deployment:front-end:pod_kill",
                            "status": "confirmed",
                            "claim": "single replica leaves the service unavailable during replacement",
                            "mechanism_level": "service_boundary",
                            "required_evidence": ["baseline_oracle", "observation", "recovery", "cleanup"],
                            "evidence_for": ["runtime/live-r1/business.json"],
                            "unsupported_claims": [],
                            "evidence_against": ["counter"] if contradiction else [],
                        }
                    ],
                    "rca_audit": [
                        {
                            "transition": {"allowed": True, "next_status": "confirmed"},
                            "hypotheses": [
                                {
                                    "hypothesis_id": "server:deployment:front-end:pod_kill",
                                    "high_severity_contradiction": contradiction,
                                    "required_evidence_complete": True,
                                    "transition": {"allowed": True, "next_status": "confirmed"},
                                }
                            ]
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    (root / "knowledge_draft.json").write_text(
        json.dumps(
            {
                "payload": {
                    "id": "KB-RCA-sock-shop-front-end-pod-kill-intent",
                    "knowledge_status": "provisional",
                    "applicability_conditions": ["same project and commit"],
                    "exclusion_conditions": ["cross_project_transfer_requires_existing_feedback_protocol"],
                    "next_evidence": ["repeat_business_oracle", "verify_recovery"],
                }
            }
        ),
        encoding="utf-8",
    )
    (root / "observe.json").write_text(
        json.dumps({"payload": {"observation": {"status": "pass", "samples": [{"status_code": 200}]}}}),
        encoding="utf-8",
    )
    (root / "cleanup_report.json").write_text(
        json.dumps({"payload": {"status": "verified", "errors": []}}),
        encoding="utf-8",
    )


def test_promotes_two_independent_availability_runs_to_local_reusable(tmp_path) -> None:
    history = tmp_path / "history"
    _write_run(history / "r1", run_id="live-r1", seed=1001)
    _write_run(history / "r2", run_id="live-r2", seed=1002)

    result = promote_from_history(
        history_root=history,
        output_root=tmp_path / "out",
        knowledge_write_root=tmp_path / "knowledge",
    )

    assert result["status"] == "promoted"
    assert result["knowledge_status"] == "local_reusable"
    assert result["classification"] == "availability_weakness"
    assert result["valid_reproductions"] == 2
    assert len(result["regression"]["intents"]) == 2
    assert all(intent["weakness_id"] == "WS-sock-shop-front-end-pod-kill-intent" for intent in result["regression"]["intents"])
    assert (tmp_path / "knowledge" / "weakness_card.json").is_file()
    assert (tmp_path / "knowledge" / "regression_intents.json").is_file()


def test_rejects_defense_or_non_weakness_results(tmp_path) -> None:
    history = tmp_path / "history"
    _write_run(history / "r1", run_id="live-r1")
    _write_run(history / "r2", run_id="live-r2", result="availability_defended")

    result = promote_from_history(history_root=history, output_root=tmp_path / "out")

    assert result["status"] == "contested"
    assert "availability_degraded" in result["reason"]
    assert (tmp_path / "out" / "knowledge_conflict.json").is_file()


def test_requires_same_causal_identity_and_preserves_existing_card_on_conflict(tmp_path) -> None:
    history = tmp_path / "history"
    _write_run(history / "r1", run_id="live-r1")
    _write_run(history / "r2", run_id="live-r2", target="catalogue")
    existing = tmp_path / "knowledge" / "weakness_card.json"
    existing.parent.mkdir()
    existing.write_text(json.dumps({"id": "old", "knowledge_status": "local_reusable"}), encoding="utf-8")

    result = promote_from_history(
        history_root=history,
        output_root=tmp_path / "out",
        knowledge_write_root=existing.parent,
    )

    assert result["status"] == "contested"
    assert result["reusable_card_preserved"] is True
    assert json.loads(existing.read_text(encoding="utf-8"))["id"] == "old"


def test_selection_requires_complete_weakness_artifacts(tmp_path) -> None:
    valid = tmp_path / "valid"
    _write_run(valid, run_id="live-r1")
    invalid = tmp_path / "invalid"
    invalid.mkdir()
    (invalid / "run_manifest.json").write_text("{}", encoding="utf-8")

    result = select_history_children(tmp_path)

    assert [item.name for item in result["selected"]] == ["valid"]
    assert result["rejected"] == [{"path": "invalid", "reason": "missing_required_artifacts"}]


def test_rejects_confirmed_status_without_a_valid_confirmed_hypothesis(tmp_path) -> None:
    history = tmp_path / "history"
    _write_run(history / "r1", run_id="live-r1", seed=1001)
    _write_run(history / "r2", run_id="live-r2", seed=1002)
    rca_path = history / "r2" / "rca_report.json"
    report = json.loads(rca_path.read_text(encoding="utf-8"))
    report["payload"]["hypotheses"] = []
    rca_path.write_text(json.dumps(report), encoding="utf-8")

    result = promote_from_history(history_root=history, output_root=tmp_path / "out")

    assert result["status"] == "contested"
    assert "hypothesis" in result["reason"]


def test_rejects_missing_project_identity(tmp_path) -> None:
    history = tmp_path / "history"
    _write_run(history / "r1", run_id="live-r1", seed=1001)
    _write_run(history / "r2", run_id="live-r2", seed=1002)
    rca_path = history / "r2" / "rca_report.json"
    report = json.loads(rca_path.read_text(encoding="utf-8"))
    report["payload"]["project_id"] = ""
    report["payload"]["project_commit"] = ""
    rca_path.write_text(json.dumps(report), encoding="utf-8")

    result = promote_from_history(history_root=history, output_root=tmp_path / "out")

    assert result["status"] == "contested"
    assert "identity" in result["reason"]


def test_preserves_different_existing_card_on_successful_identity_conflict(tmp_path) -> None:
    history = tmp_path / "history"
    _write_run(history / "r1", run_id="live-r1", seed=1001)
    _write_run(history / "r2", run_id="live-r2", seed=1002)
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    old = knowledge / "weakness_card.json"
    old.write_text(json.dumps({"id": "old-card", "knowledge_status": "local_reusable"}), encoding="utf-8")

    result = promote_from_history(
        history_root=history,
        output_root=tmp_path / "out",
        knowledge_write_root=knowledge,
    )

    assert result["status"] == "contested"
    assert result["reusable_card_preserved"] is True
    assert json.loads(old.read_text(encoding="utf-8"))["id"] == "old-card"
