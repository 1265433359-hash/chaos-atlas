from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.rca_runtime_loop import (
    advance_rca_loop,
    collect_action_evidence,
    execute_selected_action,
    ingest_action_result,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
VERDICT_PATH = REPO_ROOT / "artifacts" / "sock-shop" / "sock_shop_verdicts.json"


def _action() -> dict:
    return {
        "action_id": "A-TEST-CONFIG-001",
        "kind": "config_lookup",
        "target_scope": "catalogue deployment configuration",
        "hypotheses_separated": 1,
        "evidence_gain": 2,
        "cost": 0,
        "risk": 0,
        "environment_uncertainty": 0,
        "preconditions": ["frozen_manifest"],
        "cleanup": ["none"],
        "output_schema": "config_facts",
        "stop_conditions": ["configuration facts are complete"],
    }


def _case(*, knowledge_status: str = "provisional", rca_status: str = "bounded") -> dict:
    return {
        "schema_version": "chaosatlas-weakness-case-v1",
        "case_family": "catalogue_db_podkill",
        "weakness_id": "WS-test-catalogue-db-podchaos-pod-kill",
        "project_id": "sock-shop",
        "project_commit": "test-commit",
        "round_id": "pilot-r1",
        "test_node": {
            "family": "PodChaos",
            "operation": "pod-kill",
            "target_role": "catalogue-db deployment",
            "source_ref": "artifacts/sock-shop/sock_shop_verdicts.json",
        },
        "symptom": {
            "oracle": "catalogue business path",
            "baseline_contract": "catalogue is available",
            "injected_contract": "catalogue is unavailable",
        },
        "weakness_status": "confirmed",
        "rca_status": rca_status,
        "knowledge_status": knowledge_status,
        "evidence_refs": [],
        "hypothesis_ids": ["RCA-test-01"],
        "next_actions": [{"status": "planned", "selected": _action()}],
        "hypotheses": [
            {
                "hypothesis_id": "RCA-test-01",
                "weakness_id": "WS-test-catalogue-db-podchaos-pod-kill",
                "scope": {
                    "services": ["catalogue"],
                    "edge": "catalogue-db",
                },
                "claim": "catalogue returns an error because its database connection is unavailable",
                "mechanism_class": "database_connection_unavailable",
                "mechanism_level": "dependency",
                "expected_observations": ["connection failure appears in the action window"],
                "falsifiers": ["catalogue serves the same response without the database"],
                "required_evidence": ["scoped_catalogue_logs", "connection_failure_to_request_error_link"],
                "evidence_for": [],
                "evidence_against": [],
                "unsupported_claims": ["scoped_catalogue_logs", "connection_failure_to_request_error_link"],
                "status": "pending" if rca_status == "bounded" else rca_status,
                "confidence": 0.0,
                "next_action": "A-TEST-CONFIG-001",
            }
        ],
        "replicates": [],
        "rca_audit": [],
    }


def test_dry_run_writes_unavailable_evidence_without_calling_executor(tmp_path: Path) -> None:
    called = False

    def executor(_: dict) -> dict:
        nonlocal called
        called = True
        return {}

    result = execute_selected_action(
        case=_case(),
        action=_action(),
        output_root=tmp_path / "round-r2",
        available_preconditions={"frozen_manifest"},
        executor=executor,
        dry_run=True,
    )

    assert result["status"] == "dry_run"
    assert called is False
    assert result["evidence"][0]["polarity"] == "unavailable"
    assert (tmp_path / "round-r2" / "actions" / "A-TEST-CONFIG-001.json").is_file()


def test_runtime_loop_collects_declared_action_evidence(tmp_path: Path) -> None:
    source = tmp_path / "logs" / "catalogue.log"
    source.parent.mkdir()
    source.write_text("database connection failed\n", encoding="utf-8")

    evidence = collect_action_evidence(
        root=tmp_path,
        requests=[
            {
                "evidence_id": "EV-RUNTIME-LOG-001",
                "kind": "runtime_log",
                "claim_scope": "catalogue-db",
                "source_ref": "logs/catalogue.log",
                "interpretation": "catalogue logged a database connection failure",
                "satisfies": ["scoped_catalogue_logs"],
            },
            {
                "evidence_id": "EV-RUNTIME-TRACE-001",
                "kind": "trace",
                "claim_scope": "catalogue-db",
                "source_ref": "traces/catalogue.json",
                "interpretation": "trace backend was unavailable",
                "available": False,
                "unavailable_reason": "trace_backend_unavailable",
            },
        ],
    )

    assert [item["polarity"] for item in evidence] == ["supports", "unavailable"]
    assert evidence[0]["sha256"]
    assert evidence[1]["unavailable_reason"] == "trace_backend_unavailable"


def test_execution_fails_closed_on_missing_precondition(tmp_path: Path) -> None:
    called = False

    def executor(_: dict) -> dict:
        nonlocal called
        called = True
        return {}

    result = execute_selected_action(
        case=_case(),
        action=_action(),
        output_root=tmp_path / "round-r2",
        available_preconditions=set(),
        executor=executor,
        dry_run=False,
        allow_live=True,
    )

    assert result["status"] == "blocked"
    assert "frozen_manifest" in result["missing_preconditions"]
    assert called is False


def test_live_execution_requires_explicit_gate(tmp_path: Path) -> None:
    result = execute_selected_action(
        case=_case(),
        action=_action(),
        output_root=tmp_path / "round-r2",
        available_preconditions={"frozen_manifest"},
        executor=lambda _: {"evidence": []},
        dry_run=False,
        allow_live=False,
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "live_execution_gate_required"


def test_blocked_action_is_not_consumed_by_follow_up_planning(tmp_path: Path) -> None:
    from tools.sock_shop_rca import build_sock_shop_pilot

    source_root = tmp_path / "pilot-r1"
    build_sock_shop_pilot(
        verdict_path=VERDICT_PATH,
        output_root=source_root,
        project_commit="sock-shop-fixture-commit",
        round_id="pilot-r1",
    )
    output_root = tmp_path / "pilot-r2"
    result = advance_rca_loop(
        rca_root=source_root,
        output_root=output_root,
        available_preconditions={"frozen_manifest"},
        dry_run=False,
        allow_live=True,
    )

    assert result["status"] == "completed"
    plans = json.loads((output_root / "action_plan.json").read_text(encoding="utf-8"))
    catalogue_plan = next(
        item["plan"]
        for item in plans["case_plans"]
        if item["case_family"] == "catalogue_db_podkill"
    )
    assert catalogue_plan["result_status"] == "blocked"
    assert catalogue_plan["selected"]["action_id"] == "A-SS-CATDB-CONFIG-001"


def test_evidence_ingestion_confirms_rca_and_promotes_knowledge() -> None:
    case = _case()
    action_result = {
        "status": "executed",
        "action_id": "A-TEST-CONFIG-001",
        "discriminating_action": True,
        "valid_reproductions": 2,
        "valid_counterfactuals": 0,
        "lifecycle_complete": True,
        "direct_evidence": True,
        "applicability_complete": True,
        "regression_complete": True,
            "attestation": {
                "schema_version": "chaosatlas-runtime-result-v1",
                "valid": True,
                "comparison_eligible": True,
                "baseline": True,
                "injection": True,
                "observation": True,
                "recovery": True,
                "cleanup": True,
                "independent_oracle": True,
            },
        "evidence": [
            {
                "evidence_id": "EV-TEST-LOG-001",
                "hypothesis_id": "RCA-test-01",
                "kind": "runtime_log",
                "polarity": "supports",
                "claim_scope": "catalogue-db",
                "source_ref": "actions/A-TEST-CONFIG-001.json",
                "interpretation": "scoped catalogue logs show a database connection failure in the action window",
                "satisfies": ["scoped_catalogue_logs"],
            },
            {
                "evidence_id": "EV-TEST-LINK-001",
                "hypothesis_id": "RCA-test-01",
                "kind": "business_path_replay",
                "polarity": "supports",
                "claim_scope": "catalogue-db",
                "source_ref": "actions/A-TEST-CONFIG-001.json",
                "interpretation": "request errors start and end with the database failure window",
                "satisfies": ["connection_failure_to_request_error_link"],
            },
            {
                "evidence_id": "EV-TEST-CONFIG-001",
                "hypothesis_id": "RCA-test-01",
                "kind": "config_facts",
                "polarity": "supports",
                "claim_scope": "catalogue-db",
                "source_ref": "actions/A-TEST-CONFIG-001.json",
                "interpretation": "configuration maps catalogue to the database dependency",
                "satisfies": [],
            },
        ],
    }

    result = ingest_action_result(case=case, action_result=action_result)

    assert result["case"]["rca_status"] == "confirmed"
    assert result["case"]["knowledge_status"] == "local_reusable"
    assert result["case"]["hypotheses"][0]["status"] == "confirmed"
    assert result["promotion"]["next_status"] == "local_reusable"
    assert len(result["case"]["evidence_refs"]) == 3


def test_untrusted_executor_metadata_cannot_promote_knowledge() -> None:
    case = _case()
    result = ingest_action_result(
        case=case,
        action_result={
            "status": "executed",
            "action_id": "A-TEST-CONFIG-001",
            "discriminating_action": "false",
            "valid_reproductions": "2",
            "valid_counterfactuals": "0",
            "lifecycle_complete": "true",
            "direct_evidence": "true",
            "applicability_complete": "true",
            "regression_complete": "true",
            "evidence": [
                {
                    "evidence_id": "EV-TEST-METADATA-001",
                    "hypothesis_id": "RCA-test-01",
                    "kind": "config_facts",
                    "polarity": "supports",
                    "claim_scope": "catalogue-db",
                    "source_ref": "actions/A-TEST-CONFIG-001.json",
                    "interpretation": "configuration evidence",
                    "satisfies": [
                        "scoped_catalogue_logs",
                        "connection_failure_to_request_error_link",
                    ],
                }
            ],
        },
    )

    assert result["case"]["knowledge_status"] == "provisional"
    assert result["promotion"]["reason"] != "local_reuse_gates_passed"


def test_empty_evidence_cannot_promote_knowledge() -> None:
    case = _case()
    result = ingest_action_result(
        case=case,
        action_result={
            "status": "executed",
            "action_id": "A-TEST-CONFIG-001",
            "discriminating_action": True,
            "valid_reproductions": 2,
            "lifecycle_complete": True,
            "direct_evidence": True,
            "applicability_complete": True,
            "regression_complete": True,
            "evidence": [],
        },
    )

    assert result["case"]["knowledge_status"] == "provisional"


def test_dry_run_does_not_create_knowledge_or_bound_pending_rca() -> None:
    case = _case(knowledge_status="none", rca_status="pending")
    result = ingest_action_result(
        case=case,
        action_result={
            "status": "dry_run",
            "action_id": "A-TEST-CONFIG-001",
            "evidence": [
                {
                    "evidence_id": "EV-TEST-DRY-RUN-001",
                    "kind": "dry_run",
                    "polarity": "unavailable",
                    "claim_scope": "catalogue-db",
                    "source_ref": "actions/A-TEST-CONFIG-001.json",
                    "interpretation": "the action contract was checked without execution",
                    "satisfies": [],
                }
            ],
        },
    )

    assert result["case"]["rca_status"] == "pending"
    assert result["case"]["knowledge_status"] == "none"
    assert result["case"]["evidence_refs"] == [
        {
            "evidence_id": "EV-TEST-DRY-RUN-001",
            "kind": "dry_run",
            "polarity": "unavailable",
            "claim_scope": "catalogue-db",
            "source_ref": "actions/A-TEST-CONFIG-001.json",
            "interpretation": "the action contract was checked without execution",
            "satisfies": [],
        }
    ]


def test_runtime_outcome_injection_not_confirmed_cannot_feed_rca() -> None:
    case = _case()
    result = ingest_action_result(
        case=case,
        action_result={
            "status": "executed",
            "outcome_status": "injection_not_confirmed",
            "action_id": "A-TEST-CONFIG-001",
            "evidence": [
                {
                    "evidence_id": "EV-TEST-NO-INJECTION-001",
                    "kind": "runtime_log",
                    "polarity": "supports",
                    "claim_scope": "catalogue-db",
                    "source_ref": "actions/A-TEST-CONFIG-001.json",
                    "interpretation": "the requested fault was not confirmed by the runtime",
                    "satisfies": ["scoped_catalogue_logs"],
                }
            ],
        },
    )

    assert result["case"]["rca_status"] == "bounded"
    assert result["case"]["knowledge_status"] == "provisional"
    assert result["case"]["evidence_refs"] == []
    assert result["transition"]["reason"] == "action_result_not_accepted"


def test_bounded_hypothesis_confidence_is_limited_by_required_evidence() -> None:
    case = _case()
    result = ingest_action_result(
        case=case,
        action_result={
            "status": "executed",
            "action_id": "A-TEST-CONFIG-001",
            "evidence": [
                {
                    "evidence_id": "EV-TEST-PARTIAL-001",
                    "hypothesis_id": "RCA-test-01",
                    "kind": "runtime_log",
                    "polarity": "supports",
                    "claim_scope": "catalogue-db",
                    "source_ref": "actions/A-TEST-CONFIG-001.json",
                    "interpretation": "one required observation is present",
                    "satisfies": ["scoped_catalogue_logs"],
                }
            ],
        },
    )

    hypothesis = result["case"]["hypotheses"][0]
    assert hypothesis["status"] == "bounded"
    assert hypothesis["claim_level"] == "boundary"
    assert hypothesis["confidence"] == 0.5


def test_matching_hypothesis_id_does_not_override_claim_scope() -> None:
    case = _case()
    result = ingest_action_result(
        case=case,
        action_result={
            "status": "executed",
            "action_id": "A-TEST-CONFIG-001",
            "discriminating_action": True,
            "evidence": [
                {
                    "evidence_id": "EV-TEST-WRONG-SCOPE-001",
                    "hypothesis_id": "RCA-test-01",
                    "kind": "runtime_log",
                    "polarity": "supports",
                    "claim_scope": "orders->payment",
                    "source_ref": "actions/A-TEST-CONFIG-001.json",
                    "interpretation": "evidence from an unrelated edge",
                    "satisfies": [
                        "scoped_catalogue_logs",
                        "connection_failure_to_request_error_link",
                    ],
                }
            ],
        },
    )

    assert result["case"]["hypotheses"][0]["status"] == "pending"
    assert result["case"]["rca_status"] == "bounded"
    assert result["case"]["evidence_refs"] == []


def test_blocked_result_cannot_change_state_or_add_evidence() -> None:
    case = _case()
    result = ingest_action_result(
        case=case,
        action_result={
            "status": "blocked",
            "action_id": "A-TEST-CONFIG-001",
            "high_severity_contradiction": True,
            "evidence": [
                {
                    "evidence_id": "EV-TEST-BLOCKED-001",
                    "hypothesis_id": "RCA-test-01",
                    "kind": "counterfactual",
                    "polarity": "contradicts",
                    "claim_scope": "catalogue-db",
                    "source_ref": "actions/A-TEST-CONFIG-001.json",
                    "interpretation": "untrusted blocked output",
                    "satisfies": [],
                }
            ],
        },
    )

    assert result["case"]["rca_status"] == "bounded"
    assert result["case"]["knowledge_status"] == "provisional"
    assert result["case"]["evidence_refs"] == []


def test_action_result_is_append_only(tmp_path: Path) -> None:
    kwargs = {
        "case": _case(),
        "action": _action(),
        "output_root": tmp_path / "round-r2",
        "available_preconditions": {"frozen_manifest"},
    }
    execute_selected_action(**kwargs)
    with pytest.raises(FileExistsError):
        execute_selected_action(**kwargs)


def test_counterexample_demotes_knowledge_without_deleting_history() -> None:
    case = _case(knowledge_status="local_reusable", rca_status="confirmed")
    case["hypotheses"][0]["status"] = "confirmed"
    case["evidence_refs"] = [
        {
            "evidence_id": "EV-OLD-001",
            "kind": "manifest",
            "polarity": "supports",
            "claim_scope": "catalogue-db",
            "source_ref": "artifacts/sock-shop/sock_shop_verdicts.json",
            "interpretation": "old supporting evidence",
        }
    ]

    result = ingest_action_result(
        case=case,
        action_result={
            "status": "executed",
            "action_id": "A-TEST-CONFIG-001",
            "high_severity_contradiction": True,
            "evidence": [
                {
                    "evidence_id": "EV-TEST-CONTRA-001",
                    "hypothesis_id": "RCA-test-01",
                    "kind": "counterfactual",
                    "polarity": "contradicts",
                    "claim_scope": "catalogue-db",
                    "source_ref": "actions/A-TEST-CONFIG-001.json",
                    "interpretation": "catalogue remains healthy while the database dependency is unavailable",
                    "satisfies": [],
                }
            ],
        },
    )

    assert result["case"]["rca_status"] == "rejected"
    assert result["case"]["knowledge_status"] == "contested"
    assert "EV-OLD-001" in {item["evidence_id"] for item in result["case"]["evidence_refs"]}
    assert "EV-TEST-CONTRA-001" in {item["evidence_id"] for item in result["case"]["evidence_refs"]}


def test_advance_rca_loop_appends_a_new_round_and_rebuilds_intents(tmp_path: Path) -> None:
    from tools.sock_shop_rca import build_sock_shop_pilot

    source_root = tmp_path / "pilot-r1"
    build_sock_shop_pilot(
        verdict_path=VERDICT_PATH,
        output_root=source_root,
        project_commit="sock-shop-fixture-commit",
        round_id="pilot-r1",
    )
    output_root = tmp_path / "pilot-r2"

    result = advance_rca_loop(
        rca_root=source_root,
        output_root=output_root,
        available_preconditions={
            "frozen_manifest",
            "captured_catalogue_logs",
            "captured_ready_samples",
            "captured_window",
        },
        dry_run=True,
    )

    assert result["round_id"] == "pilot-r2"
    assert result["status"] == "completed"
    assert (output_root / "manifest.json").is_file()
    assert len(list((output_root / "actions").glob("*.json"))) == 3
    assert len(list((output_root / "cases").glob("*.json"))) == 3
    next_plans = json.loads((output_root / "action_plan.json").read_text(encoding="utf-8"))
    planned_actions = {
        item["plan"].get("selected", {}).get("action_id")
        for item in next_plans["case_plans"]
        if item["plan"].get("status") == "planned"
    }
    assert "A-SS-SINGLETON-READY-001" in planned_actions
    assert "A-SS-ABORT-LOGS-001" in planned_actions
    assert "A-SS-CATDB-LOGS-001" in planned_actions
    assert all(
        item["plan"].get("completed_action", {}).get("action_id")
        != (item["plan"].get("selected") or {}).get("action_id")
        for item in next_plans["case_plans"]
    )
    intents = json.loads(
        (output_root / "knowledge_drafts" / "regression_intents.json").read_text(encoding="utf-8")
    )
    assert len(intents["intents"]) == 3
    assert all(item["kind"] == "discriminate" for item in intents["intents"])


def test_sock_shop_round_can_execute_actions_with_mock_executor(tmp_path: Path) -> None:
    from tools.rca_action_executor import MockRCAExecutor
    from tools.sock_shop_rca import build_sock_shop_pilot

    source_root = tmp_path / "pilot-r1"
    build_sock_shop_pilot(
        verdict_path=VERDICT_PATH,
        output_root=source_root,
        project_commit="sock-shop-fixture-commit",
        round_id="pilot-r1",
    )
    output_root = tmp_path / "pilot-r2"

    result = advance_rca_loop(
        rca_root=source_root,
        output_root=output_root,
        available_preconditions={
            "frozen_manifest",
            "captured_ready_samples",
            "captured_window",
        },
        executor=MockRCAExecutor(),
        dry_run=False,
        allow_live=True,
    )

    assert result["status"] == "completed"
    action_results = list((output_root / "actions").glob("*.json"))
    assert len(action_results) == 3
    for path in action_results:
        action_result = json.loads(path.read_text(encoding="utf-8"))
        assert action_result["status"] == "executed"
        assert action_result["outcome_status"] == "observed"
        assert action_result["attestation"]["comparison_eligible"] is True


def test_sock_shop_singleton_fixture_can_confirm_and_promote_locally(tmp_path: Path) -> None:
    from tools.sock_shop_rca import build_sock_shop_pilot

    root = tmp_path / "pilot-r1"
    manifest = build_sock_shop_pilot(
        verdict_path=VERDICT_PATH,
        output_root=root,
        project_commit="sock-shop-fixture-commit",
        round_id="pilot-r1",
    )
    case = manifest["cases"][0]
    scope = case["hypotheses"][0]["scope"]["edge"]
    result = ingest_action_result(
        case=case,
        action_result={
            "status": "executed",
            "outcome_status": "observed",
            "action_id": "A-SS-SINGLETON-CONFIG-001",
            "discriminating_action": True,
            "valid_reproductions": 2,
            "valid_counterfactuals": 0,
            "lifecycle_complete": True,
            "direct_evidence": True,
            "applicability_complete": True,
            "regression_complete": True,
            "attestation": {
                "schema_version": "chaosatlas-runtime-result-v1",
                "valid": True,
                "comparison_eligible": True,
                "baseline": True,
                "injection": True,
                "observation": True,
                "recovery": True,
                "cleanup": True,
                "independent_oracle": True,
            },
            "evidence": [
                {
                    "evidence_id": "EV-SS-FIXTURE-MANIFEST-001",
                    "kind": "manifest",
                    "polarity": "supports",
                    "claim_scope": scope,
                    "source_ref": "artifacts/sock-shop/sock-shop-lab-manifest.yaml",
                    "interpretation": "the fixture confirms one replica and no disruption budget",
                    "satisfies": ["static_manifest_replica_facts"],
                },
                {
                    "evidence_id": "EV-SS-FIXTURE-READY-001",
                    "kind": "runtime_log",
                    "polarity": "supports",
                    "claim_scope": scope,
                    "source_ref": "artifacts/sock-shop/avail_frontend_kill.json",
                    "interpretation": "the fixture confirms the Ready transition during replacement",
                    "satisfies": ["ready_transition_runtime"],
                },
                {
                    "evidence_id": "EV-SS-FIXTURE-BUSINESS-001",
                    "kind": "business_path_replay",
                    "polarity": "supports",
                    "claim_scope": scope,
                    "source_ref": "artifacts/sock-shop/sock_shop_verdicts.json",
                    "interpretation": "the fixture confirms business impact during the replacement window",
                    "satisfies": ["business_impact_in_window"],
                },
            ],
        },
    )

    assert result["case"]["rca_status"] == "confirmed"
    assert result["case"]["knowledge_status"] == "local_reusable"
    assert result["case"]["hypotheses"][0]["claim_level"] == "mechanism"


def test_next_round_replans_pending_case_when_precondition_becomes_available(tmp_path: Path) -> None:
    from tools.sock_shop_rca import build_sock_shop_pilot

    source_root = tmp_path / "pilot-r1"
    build_sock_shop_pilot(
        verdict_path=VERDICT_PATH,
        output_root=source_root,
        project_commit="sock-shop-fixture-commit",
        round_id="pilot-r1",
    )
    first_round = tmp_path / "pilot-r2"
    advance_rca_loop(
        rca_root=source_root,
        output_root=first_round,
        available_preconditions={"frozen_manifest"},
        dry_run=True,
    )
    second_round = tmp_path / "pilot-r3"
    advance_rca_loop(
        rca_root=first_round,
        output_root=second_round,
        available_preconditions={
            "frozen_manifest",
            "captured_catalogue_logs",
            "captured_ready_samples",
            "captured_window",
        },
        dry_run=True,
    )

    plans = json.loads((second_round / "action_plan.json").read_text(encoding="utf-8"))
    catalogue_plan = next(
        item["plan"]
        for item in plans["case_plans"]
        if item["case_family"] == "catalogue_db_podkill"
    )
    assert catalogue_plan["completed_action"]["action_id"] == "A-SS-CATDB-LOGS-001"
    assert catalogue_plan["result_status"] == "dry_run"


def test_advance_rca_loop_refuses_non_empty_output(tmp_path: Path) -> None:
    source_root = tmp_path / "pilot-r1"
    source_root.mkdir()
    (source_root / "cases").mkdir()
    output_root = tmp_path / "pilot-r2"
    output_root.mkdir()
    (output_root / "keep.txt").write_text("preserve", encoding="utf-8")

    with pytest.raises(FileExistsError):
        advance_rca_loop(
            rca_root=source_root,
            output_root=output_root,
            available_preconditions={"frozen_manifest"},
            dry_run=True,
        )
