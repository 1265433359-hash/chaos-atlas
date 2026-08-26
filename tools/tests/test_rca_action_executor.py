from __future__ import annotations

from pathlib import Path

from tools.rca_action_executor import MockRCAExecutor
from tools.rca_runtime_loop import execute_selected_action


def _action() -> dict:
    return {
        "action_id": "A-MOCK-001",
        "kind": "business_replay",
        "target_scope": "catalogue-db",
        "hypotheses_separated": 2,
        "evidence_gain": 3,
        "cost": 1,
        "risk": 0,
        "environment_uncertainty": 0,
        "preconditions": ["baseline_pass"],
        "cleanup": ["none"],
        "output_schema": "runtime",
        "stop_conditions": ["stop after recovery"],
        "namespace": "rca-test",
        "project_snapshot_sha256": "a" * 64,
        "baseline_contract": "catalogue business path is available",
        "budget": {"max_seconds": 30, "max_retries": 0},
        "cleanup_contract": ["none"],
    }


def test_mock_executor_returns_complete_attestation_for_observed_action() -> None:
    executor = MockRCAExecutor()

    result = executor(_action())

    assert result["outcome_status"] == "observed"
    assert result["attestation"]["valid"] is True
    assert result["attestation"]["comparison_eligible"] is True
    assert all(
        result["attestation"][field]
        for field in (
            "baseline",
            "injection",
            "observation",
            "recovery",
            "cleanup",
            "independent_oracle",
        )
    )


def test_mock_executor_fails_closed_when_execution_contract_is_incomplete() -> None:
    action = _action()
    del action["namespace"]

    result = MockRCAExecutor()(action)

    assert result["outcome_status"] == "environment_blocked"
    assert result["attestation"]["valid"] is False
    assert "namespace" in result["missing_contract_fields"]


def test_runtime_executor_persists_attestation_and_result(tmp_path: Path) -> None:
    result = execute_selected_action(
        case={"weakness_id": "WS-test"},
        action=_action(),
        output_root=tmp_path / "round-r2",
        available_preconditions={"baseline_pass"},
        executor=MockRCAExecutor(),
        dry_run=False,
        allow_live=True,
    )

    assert result["status"] == "executed"
    assert result["outcome_status"] == "observed"
    assert result["attestation"]["comparison_eligible"] is True
    assert (tmp_path / "round-r2" / "actions" / "A-MOCK-001.json").is_file()
