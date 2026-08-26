from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.rca_action_executor import MockRCAExecutor
from tools.run_closed_loop import run_closed_loop
from tools.sock_shop_rca import build_sock_shop_pilot


REPO_ROOT = Path(__file__).resolve().parents[2]
VERDICT_PATH = REPO_ROOT / "artifacts" / "sock-shop" / "sock_shop_verdicts.json"


def _pilot(tmp_path: Path) -> Path:
    root = tmp_path / "pilot-r1"
    build_sock_shop_pilot(
        verdict_path=VERDICT_PATH,
        output_root=root,
        project_commit="sock-shop-fixture-commit",
        round_id="pilot-r1",
    )
    return root


def test_closed_loop_writes_four_stage_audit_and_round_lineage(tmp_path: Path) -> None:
    source_root = _pilot(tmp_path)
    output_root = tmp_path / "pilot-r2"

    result = run_closed_loop(
        rca_root=source_root,
        output_root=output_root,
        available_preconditions={"frozen_manifest", "captured_window"},
        executor=MockRCAExecutor(),
        dry_run=False,
        allow_live=True,
    )

    audit = json.loads(
        (output_root / "closed_loop_manifest.json").read_text(encoding="utf-8")
    )
    assert result["status"] == "completed"
    assert audit["round_id"] == "pilot-r2"
    assert audit["parent_round_id"] == "pilot-r1"
    assert set(audit["stages"]) == {"onboard", "discover", "diagnose", "learn"}
    assert audit["stages"]["learn"]["knowledge_base_updated"] is False
    assert audit["stages"]["learn"]["intent_count"] == 3
    assert audit["cleanup"]["status"] == "verified"


def test_closed_loop_input_snapshot_is_stable_across_output_directories(tmp_path: Path) -> None:
    source_root = _pilot(tmp_path)
    first = run_closed_loop(
        rca_root=source_root,
        output_root=tmp_path / "pilot-r2-a",
        available_preconditions={"frozen_manifest"},
        dry_run=True,
    )
    second = run_closed_loop(
        rca_root=source_root,
        output_root=tmp_path / "pilot-r2-b",
        available_preconditions={"frozen_manifest"},
        dry_run=True,
    )

    assert first["input_snapshot_sha256"] == second["input_snapshot_sha256"]
    assert first["parent_manifest_sha256"] == second["parent_manifest_sha256"]


def test_closed_loop_refuses_non_empty_output(tmp_path: Path) -> None:
    source_root = _pilot(tmp_path)
    output_root = tmp_path / "pilot-r2"
    output_root.mkdir()
    (output_root / "keep.txt").write_text("preserve", encoding="utf-8")

    with pytest.raises(FileExistsError):
        run_closed_loop(
            rca_root=source_root,
            output_root=output_root,
            available_preconditions={"frozen_manifest"},
            dry_run=True,
        )


def test_local_reusable_feedback_changes_next_diagnostic_action(tmp_path: Path) -> None:
    source_root = _pilot(tmp_path)
    case_path = next(
        path
        for path in (source_root / "cases").glob("*.json")
        if "front-end-podchaos-pod-kill" in path.name
    )
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["knowledge_status"] = "local_reusable"
    case["knowledge_promotion_audit"] = {
        "allowed": True,
        "next_status": "local_reusable",
        "reason": "local_reuse_gates_passed",
    }
    case_path.write_text(
        json.dumps(case, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    output_root = tmp_path / "pilot-r2"
    run_closed_loop(
        rca_root=source_root,
        output_root=output_root,
        available_preconditions={
            "frozen_manifest",
            "runner_allows_replica_scaling",
        },
        dry_run=True,
    )

    action_plan = json.loads(
        (output_root / "action_plan.json").read_text(encoding="utf-8")
    )
    singleton = next(
        item
        for item in action_plan["case_plans"]
        if item["case_family"] == "single_replica_podkill"
    )
    assert (
        singleton["plan"]["completed_action"]["action_id"]
        == "A-SS-SINGLETON-COUNTERFACTUAL-001"
    )


def test_closed_loop_persists_advisory_llm_analysis_without_changing_verdict(tmp_path: Path) -> None:
    source_root = _pilot(tmp_path)

    class Backend:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, system: str, user: str, assistant: str):
            self.calls += 1
            payload = json.loads(user)
            hypothesis = payload["case"]["hypotheses"][0]
            return json.dumps({
                "hypotheses": [{
                    "hypothesis_id": hypothesis["hypothesis_id"],
                    "mechanism": "bounded service-boundary explanation",
                    "supports": [],
                    "contradicts": [],
                    "missing_evidence": ["independent mechanism evidence"],
                    "next_actions": ["collect scoped logs"],
                }],
                "global_missing_evidence": ["independent mechanism evidence"],
            }), {"backend": "test"}

    backend = Backend()
    output_root = tmp_path / "pilot-r2"
    result = run_closed_loop(
        rca_root=source_root,
        output_root=output_root,
        available_preconditions={"frozen_manifest"},
        dry_run=True,
        llm_backend=backend,
    )
    assert result["manifest"]["stages"]["llm_analysis"]["status"] == "completed"
    assert backend.calls > 0
    analysis_files = list((output_root / "analysis").glob("*.json"))
    assert analysis_files
    analysis = json.loads(analysis_files[0].read_text(encoding="utf-8"))
    assert analysis["schema_version"] == "chaosatlas-llm-rca-analysis-v1"
    assert "rca_status" not in analysis["analysis"]
    assert result["manifest"]["stages"]["diagnose"]["case_statuses"]
