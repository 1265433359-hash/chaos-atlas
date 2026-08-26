from __future__ import annotations

import json
from pathlib import Path

from tools.run_live_improvement import compare_live_runs, run_live_improvement, stage_history_run


def _write_run(root: Path, *, result: str, seed: int = 1001, complete: bool = True) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "run_manifest.json").write_text(
        json.dumps({"seed": seed, "run_id": "live-test", "schema_version": "test"}),
        encoding="utf-8",
    )
    execute = {
        "payload": {
            "scenario_id": "live-test",
            "scenario_hash": "hash-under-test",
            "seed": seed,
            "oracle": {"business": {"service": "front-end", "remote_port": 80}},
            "recovery": {"deadline_s": 180, "stable_samples": 2},
            "cleanup": {"owner": "chaosatlas", "required": True},
            "phases": [{"faults": [{"kind": "pod_kill", "cleanup_confirmed": True}]}],
        }
    }
    (root / "execute.json").write_text(json.dumps(execute), encoding="utf-8")
    (root / "classify.json").write_text(json.dumps({"payload": {"result": result}}), encoding="utf-8")
    (root / "cleanup_report.json").write_text(
        json.dumps({"status": "verified" if complete else "blocked"}),
        encoding="utf-8",
    )
    (root / "observe.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")
    (root / "inventory.json").write_text(
        json.dumps({"payload": {"project_id": "sock-shop", "project_commit": "a" * 40}}),
        encoding="utf-8",
    )


def test_compare_live_runs_verifies_same_contract_and_improvement(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    after = tmp_path / "after"
    _write_run(baseline, result="availability_degraded")
    _write_run(after, result="availability_defended")

    result = compare_live_runs(baseline, after)

    assert result["status"] == "improvement_verified"
    assert result["comparison"]["same_scenario_contract"] is True
    assert result["improvement_evidence"]["knowledge_update_allowed"] is True
    assert result["validation"]["valid"] is True


def test_compare_live_runs_blocks_incomplete_cleanup(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    after = tmp_path / "after"
    _write_run(baseline, result="availability_degraded")
    _write_run(after, result="availability_defended", complete=False)

    result = compare_live_runs(baseline, after)

    assert result["status"] == "deployment_blocked"
    assert result["improvement_evidence"]["knowledge_update_allowed"] is False


def test_stage_history_run_requires_complete_run_artifacts(tmp_path: Path) -> None:
    incomplete = tmp_path / "incomplete"
    incomplete.mkdir()
    history = tmp_path / "history"

    result = stage_history_run(incomplete, history, "r1")

    assert result["status"] == "rejected"
    assert result["reason"] == "missing_required_artifacts"
    assert not (history / "r1").exists()


def test_stage_history_run_preserves_inventory_revision(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _write_run(source, result="availability_defended")

    result = stage_history_run(source, tmp_path / "history", "r1")

    assert result["status"] == "staged"
    assert "inventory.json" in result["artifacts"]
    assert (tmp_path / "history" / "r1" / "inventory.json").is_file()
    assert (tmp_path / "history" / "r1" / "classify.json").is_file()


def test_improvement_dry_run_never_calls_live_apply(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "manifest.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: front-end\n  namespace: lab\nspec:\n  replicas: 1\n",
        encoding="utf-8",
    )
    baseline = tmp_path / "baseline"
    _write_run(baseline, result="availability_degraded")
    calls: list[list[str]] = []

    def runner(args: list[str]) -> dict:
        calls.append(args)
        return {"return_code": 0, "stdout": "dry-run", "stderr": ""}

    result = run_live_improvement(
        profile_path=tmp_path / "profile.json",
        source_root=source,
        baseline_root=baseline,
        proposal={"source_ref": "manifest.yaml", "json_pointer": "/spec/replicas", "old_value": 1, "new_value": 2},
        output_root=tmp_path / "output",
        namespace="lab",
        allowed_namespaces={"lab"},
        mode="dry-run",
        runner=runner,
    )

    assert result["status"] == "dry_run_ready"
    assert calls == [["apply", "--namespace", "lab", "--dry-run=server", "-f", str(tmp_path / "output" / "patched-source" / "manifest.yaml")]]


def test_improvement_live_requires_explicit_approval(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "manifest.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: front-end\n  namespace: lab\nspec:\n  replicas: 1\n",
        encoding="utf-8",
    )
    baseline = tmp_path / "baseline"
    _write_run(baseline, result="availability_degraded")

    result = run_live_improvement(
        profile_path=tmp_path / "profile.json",
        source_root=source,
        baseline_root=baseline,
        proposal={"source_ref": "manifest.yaml", "json_pointer": "/spec/replicas", "old_value": 1, "new_value": 2},
        output_root=tmp_path / "output",
        namespace="lab",
        allowed_namespaces={"lab"},
        mode="live",
        approve_live=False,
        runner=lambda _args: {"return_code": 0, "stdout": "dry-run", "stderr": ""},
    )

    assert result["status"] == "deployment_blocked"
    assert result["reason"] == "explicit live approval is required"
