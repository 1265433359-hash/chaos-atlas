from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.run_p09_dual_arm_selection import (
    BudgetError,
    build_records,
    ensure_budget,
    parse_selection,
    prepare_output_dir,
)


ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "artifacts" / "experiments" / "chaosatlas_10_projects"


def test_build_records_is_exactly_two_arms_by_three_registered_seeds() -> None:
    records = build_records(EXP)

    assert [(row["arm"], row["seed"]) for row in records] == [
        ("ChaosAtlas-KB", 1001),
        ("ChaosAtlas-noKB", 1001),
        ("ChaosAtlas-KB", 1002),
        ("ChaosAtlas-noKB", 1002),
        ("ChaosAtlas-KB", 1003),
        ("ChaosAtlas-noKB", 1003),
    ]
    assert all(row["project_id"] == "P09" and row["k"] == 8 for row in records)
    assert all(len(row["candidates"]) == 16 for row in records)


def test_paired_arms_share_identical_common_input() -> None:
    records = build_records(EXP)

    for seed in (1001, 1002, 1003):
        paired = [row for row in records if row["seed"] == seed]
        assert paired[0]["common"] == paired[1]["common"]
        assert [item["candidate_id"] for item in paired[0]["candidates"]] == [
            item["candidate_id"] for item in paired[1]["candidates"]
        ]


def test_parse_selection_requires_exact_budget_and_pool_membership() -> None:
    allowed = {f"P09-candidate-{index}" for index in range(1, 9)}
    raw = json.dumps(
        {
            "selected": [
                {"candidate_id": candidate_id, "rank": rank, "rationale": "bounded"}
                for rank, candidate_id in enumerate(sorted(allowed), 1)
            ]
        }
    )
    assert len(parse_selection(raw, allowed, 8)) == 8

    duplicate = json.dumps(
        {"selected": [{"candidate_id": "P09-candidate-1", "rank": rank} for rank in range(1, 9)]}
    )
    with pytest.raises(ValueError, match="duplicate"):
        parse_selection(duplicate, allowed, 8)


def test_prepare_output_dir_refuses_nonempty_directory(tmp_path: Path) -> None:
    output = tmp_path / "result"
    output.mkdir()
    (output / "existing.json").write_text("{}", encoding="utf-8")

    with pytest.raises(FileExistsError, match="nonempty"):
        prepare_output_dir(output)


def test_budget_rejects_nonpositive_ceiling_and_projected_token_overrun() -> None:
    with pytest.raises(BudgetError, match="positive"):
        ensure_budget(current_tokens=0, hard_token_ceiling=1_200_000, run_token_ceiling=0)
    with pytest.raises(BudgetError, match="exceed"):
        ensure_budget(
            current_tokens=1_190_000,
            hard_token_ceiling=1_200_000,
            run_token_ceiling=20_000,
        )
