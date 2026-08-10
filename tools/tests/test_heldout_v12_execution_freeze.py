import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FREEZE = ROOT / "artifacts" / "experiments" / "heldout" / "heldout_v12_execution_freeze.json"


def _load():
    return json.loads(FREEZE.read_text(encoding="utf-8"))


def test_execution_methods_and_seed_counts_are_frozen():
    data = _load()
    assert data["status"] == "config_frozen_runner_implementation_pending"
    assert [item["method_id"] for item in data["methods"]] == [
        "Ours-full-pre",
        "Ours-generic",
        "ChaosEater-official",
        "ChaosEater-adapter",
        "Random",
    ]
    assert len(data["methods"][2]["seed_values"]["formal"]) == 3
    assert len(data["methods"][4]["seed_values"]["formal"]) == 20
    assert data["budgets"]["formal_k"] == 10


def test_runner_blocker_is_explicit_and_no_execution_started():
    data = _load()
    assert data["runner_contract"]["status"] == "not_implemented"
    assert data["execution_state"] == {
        "cluster_started": False,
        "deployment_started": False,
        "selection_started": False,
        "injection_started": False,
        "pilot_started": False,
        "formal_started": False,
    }
