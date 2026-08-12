from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analyze_chaosatlas_statistics import analyze, normalize_record


def _row(project: str, arm: str, seed: int, token_cost: int) -> dict:
    return {
        "project_id": project,
        "arm": arm,
        "seed": seed,
        "submitted": 8,
        "valid_outputs": 8,
        "generated": 8,
        "compiler_accepted": 6 if arm == "ChaosAtlas-KB" else 4,
        "executable": 5 if arm == "ChaosAtlas-KB" else 3,
        "confirmed_weaknesses": 2 if arm == "ChaosAtlas-KB" else 1,
        "protected_targets": 1,
        "method_invalid": 1,
        "environment_blocked": 0,
        "recovery_successes": 3,
        "recovery_attempts": 3,
        "token_cost": token_cost,
        "call_chain_coverage": 0.5,
        "call_chain_depth": 3,
        "human_review_minutes": 2,
    }


def test_seeds_are_repeated_within_project_and_paired_at_project_mean():
    rows = [_row("P01", arm, seed, 100 + seed) for arm in ("ChaosAtlas-KB", "ChaosAtlas-noKB") for seed in (1, 2, 3)]
    report = analyze(rows, expected_projects=10)
    assert len(report["project_summaries"]) == 2
    assert {row["n_seeds"] for row in report["project_summaries"]} == {3}
    paired = report["paired_differences"][0]
    assert paired["kb_minus_noKB"]["compiler_acceptance_rate"] == 0.25
    assert paired["kb_minus_noKB"]["token_cost"] == 0
    assert report["paired_difference_distributions"]["compiler_acceptance_rate"]["n_projects"] == 1


def test_missing_denominator_is_null_and_never_zero():
    row = normalize_record({"project_id": "P01", "arm": "ChaosAtlas-KB", "seed": 1, "confirmed_weaknesses": 2})
    assert row["metrics"]["confirmed_weakness_yield"] is None
    assert row["metrics"]["compiler_acceptance_rate"] is None


def test_explicit_compiled_status_is_one_discovery_output():
    row = normalize_record({"project_id": "P01", "arm": "ChaosAtlas-KB-open", "seed": 1, "compiled_status": "valid"})
    assert row["metrics"]["valid_output_rate"] == 1.0


def test_runtime_repetitions_do_not_become_executable_hypotheses():
    row = normalize_record({
        "project_id": "P02", "arm": "ChaosAtlas-KB-open", "seed": 1001,
        "compiled_status": "valid", "accepted": 2, "generated": 2,
        "valid_runs": 3, "invalid_runs": 7,
    })
    assert row["metrics"]["valid_output_rate"] == 1.0
    assert row["metrics"]["compiler_acceptance_rate"] == 1.0
    assert row["metrics"]["executable_rate"] is None
