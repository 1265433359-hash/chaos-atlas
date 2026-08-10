import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from heldout_v12_runner import build_plan, load_adapters, load_registry  # noqa: E402


REGISTRY = ROOT / "artifacts" / "experiments" / "heldout" / "heldout_v12_candidate_registry.json"
ADAPTERS = ROOT / "artifacts" / "experiments" / "heldout" / "heldout_v12_adapter_freeze.json"


def test_dry_run_validates_frozen_candidate_and_never_executes():
    registry = load_registry(REGISTRY)
    adapters = load_adapters(ADAPTERS)
    candidate_id = next(item["candidate_id"] for item in registry["candidates"] if item["project_id"] == "HOTEL")
    plan = build_plan(registry, adapters, "HOTEL", "Ours-full-pre", "formal", 0, candidate_id)
    assert plan["status"] == "planned_no_execute"
    assert plan["execution_started"] is False
    assert plan["kubectl_called"] is False
    assert plan["chaos_mesh_called"] is False
    assert plan["candidate"]["chaos_kind"] in {"NetworkChaos", "PodChaos"}
    assert plan["lifecycle"][-2:] == ["assert_cleanup", "write_ledger"]


def test_runner_rejects_cross_project_candidate():
    registry = load_registry(REGISTRY)
    adapters = load_adapters(ADAPTERS)
    candidate = next(item for item in registry["candidates"] if item["project_id"] == "TEASTORE")
    with pytest.raises(ValueError, match="candidate/project mismatch"):
        build_plan(registry, adapters, "HOTEL", "Random", "pilot", 3001, candidate["candidate_id"])


def test_static_adapters_load_for_all_projects():
    adapters = load_adapters(ADAPTERS)
    assert set(adapters["projects"]) == {"HOTEL", "SOCIALNET", "TEASTORE"}
    assert all(item["static_adapter_validated"] for item in adapters["projects"].values())
    assert all(not item["execution_ready"] for item in adapters["projects"].values())


def test_plan_contains_evidence_backed_adapter():
    registry = load_registry(REGISTRY)
    adapters = load_adapters(ADAPTERS)
    candidate = registry["candidates"][0]
    plan = build_plan(registry, adapters, candidate["project_id"], "Random", "pilot", 3001, candidate["candidate_id"])
    assert plan["adapter"]["business_oracle"]["kind"] == "http_contract"
    assert plan["adapter"]["business_oracle"]["evidence"]["commit"]
    assert plan["adapter"]["cleanup_argv"][0] == "kubectl"
