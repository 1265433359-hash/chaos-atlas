from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from check_heldout_v12_feasibility import check_feasibility  # noqa: E402


POOL_ROOT = ROOT / "artifacts" / "experiments" / "heldout"


def test_pooled_feasibility_uses_current_formal_pools():
    result = check_feasibility(POOL_ROOT)
    assert result["qualification"] == "pass"
    assert result["pooled"] == {
        "protected": 16,
        "unprotected": 35,
        "unknown": 32,
        "legal_total": 83,
    }
    assert result["descriptive_only_classes"] == ["protected"]
    assert result["no_experiment_run"] is True
    assert result["no_candidate_pool_mutation"] is True


def test_v12_does_not_treat_v11_project_shortfalls_as_pool_failure():
    result = check_feasibility(POOL_ROOT)
    assert all(row["project_legal_min_pass"] for row in result["projects"])
    assert result["all_pooled_gates_pass"] is True
    assert result["all_project_minimums_pass"] is True
