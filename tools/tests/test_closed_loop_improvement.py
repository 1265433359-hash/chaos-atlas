from __future__ import annotations

import json
from pathlib import Path

import yaml

from tools.compile_scenario_node import compile_scenario
from tools.deployment_improvement import run_improvement_retest
from tools.deployment_capability import scenario_signature
from tools.tests.test_deployment_capability import scenario


def _baseline(value: dict) -> dict:
    value["seed"] = 17
    value["scenario_signature"] = scenario_signature(value)
    compiled = compile_scenario(value)
    return {
        "scenario_id": value["scenario_id"],
        "scenario_hash": compiled["scenario_hash"],
        "seed": 17,
        "oracle": value["oracle"],
        "recovery": value["recovery"],
        "cleanup": value["cleanup"],
        "verdict": "availability_degraded",
    }


def test_retest_reuses_contract_and_allows_only_structured_improvement(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    output_root = tmp_path / "patched"
    source_root.mkdir()
    manifest = source_root / "manifest.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": "front-end"},
                "spec": {"replicas": 1},
            }
        ),
        encoding="utf-8",
    )
    value = scenario()
    baseline = _baseline(value)
    proposal = {
        "source_ref": "manifest.yaml",
        "json_pointer": "/spec/replicas",
        "old_value": 1,
        "new_value": 2,
    }
    seen_context: dict[str, str] = {}

    def server_side_dry_run(**kwargs):
        seen_context["validated_root"] = str(kwargs["source_root"])
        return {"status": "dry_run_ready"}

    def executor(manifest_doc, phase, fault):
        seen_context["patched_root"] = manifest_doc["chaosatlas_execution_context"]["patched_root"]
        return {
            "status": "ok",
            "injection_confirmed": True,
            "verdict": "availability_defended",
            "cleanup_confirmed": True,
        }

    result = run_improvement_retest(
        scenario=value,
        source_root=source_root,
        output_root=output_root,
        proposal=proposal,
        baseline_result=baseline,
        executor=executor,
        dry_run=False,
        server_side_dry_run=server_side_dry_run,
    )

    assert result["status"] == "improvement_verified"
    assert result["defense_conclusion_allowed"] is True
    assert result["improvement_evidence"]["knowledge_update_allowed"] is True
    assert result["comparison"]["same_scenario_contract"] is True
    assert result["comparison"]["seed"] == 17
    assert seen_context["patched_root"] == str(output_root)
    assert seen_context["validated_root"] == str(output_root)
    assert yaml.safe_load(manifest.read_text(encoding="utf-8"))["spec"]["replicas"] == 1
    assert yaml.safe_load(
        (output_root / "manifest.yaml").read_text(encoding="utf-8")
    )["spec"]["replicas"] == 2


def test_retest_rejects_unstructured_patch_without_running(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "manifest.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: front-end\n",
        encoding="utf-8",
    )
    value = scenario()
    result = run_improvement_retest(
        scenario=value,
        source_root=source_root,
        output_root=tmp_path / "patched",
        proposal={
            "source_ref": "manifest.yaml",
            "json_pointer": "/metadata/name",
            "old_value": "front-end",
            "new_value": "changed",
        },
        baseline_result=_baseline(value),
        executor=lambda *_: {"status": "ok", "injection_confirmed": True},
        dry_run=False,
    )

    assert result["status"] == "not_run"
    assert result["defense_conclusion_allowed"] is False
    assert not (tmp_path / "patched").exists()


def test_blocked_retest_cannot_create_defense(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "manifest.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nspec:\n  replicas: 1\n",
        encoding="utf-8",
    )
    value = scenario()
    result = run_improvement_retest(
        scenario=value,
        source_root=source_root,
        output_root=tmp_path / "patched",
        proposal={
            "source_ref": "manifest.yaml",
            "json_pointer": "/spec/replicas",
            "old_value": 1,
            "new_value": 2,
        },
        baseline_result=_baseline(value),
        executor=lambda *_: {
            "status": "environment_blocked",
            "injection_confirmed": False,
        },
        dry_run=False,
    )

    assert result["status"] == "deployment_blocked"
    assert result["defense_conclusion_allowed"] is False
    assert result["after"]["verdict"] != "availability_defended"


def test_server_side_dry_run_block_blocks_retest_before_executor(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "manifest.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nspec:\n  replicas: 1\n",
        encoding="utf-8",
    )
    value = scenario()
    calls: list[str] = []

    result = run_improvement_retest(
        scenario=value,
        source_root=source_root,
        output_root=tmp_path / "patched",
        proposal={"source_ref": "manifest.yaml", "json_pointer": "/spec/replicas", "old_value": 1, "new_value": 2},
        baseline_result=_baseline(value),
        executor=lambda *_: calls.append("executor") or {"verdict": "availability_defended"},
        dry_run=False,
        server_side_dry_run=lambda *_: {"status": "deployment_blocked", "reason": "api unavailable"},
    )

    assert result["status"] == "deployment_blocked"
    assert calls == []
    assert result["defense_conclusion_allowed"] is False
