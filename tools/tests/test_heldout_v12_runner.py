import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from heldout_v12_runner import build_plan, load_registry  # noqa: E402


REGISTRY = ROOT / "artifacts" / "experiments" / "heldout" / "heldout_v12_candidate_registry.json"


def test_dry_run_validates_frozen_candidate_and_never_executes():
    registry = load_registry(REGISTRY)
    candidate_id = next(item["candidate_id"] for item in registry["candidates"] if item["project_id"] == "HOTEL")
    plan = build_plan(registry, "HOTEL", "Ours-full-pre", "formal", 0, candidate_id)
    assert plan["status"] == "planned_no_execute"
    assert plan["execution_started"] is False
    assert plan["kubectl_called"] is False
    assert plan["chaos_mesh_called"] is False
    assert plan["candidate"]["chaos_kind"] in {"NetworkChaos", "PodChaos"}
    assert plan["lifecycle"][-2:] == ["assert_cleanup", "write_ledger"]


def test_runner_rejects_cross_project_candidate():
    registry = load_registry(REGISTRY)
    candidate = next(item for item in registry["candidates"] if item["project_id"] == "TEASTORE")
    with pytest.raises(ValueError, match="candidate/project mismatch"):
        build_plan(registry, "HOTEL", "Random", "pilot", 3001, candidate["candidate_id"])
