from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.build_same_pool_fair_inputs import write_freeze
from tools.run_same_pool_selection import parse_selection_output
from tools.run_same_pool_selection import run_selection


def test_parse_selection_output_accepts_budgeted_candidate_ids() -> None:
    raw = json.dumps(
        {
            "selected_candidates": [
                {"candidate_id": "p:a:network_loss:111", "rank": 1, "reason": "core path"},
                {"candidate_id": "p:b:pod_kill:222", "rank": 2, "reason": "single replica"},
            ]
        }
    )

    result = parse_selection_output(raw, allowed_ids={"p:a:network_loss:111", "p:b:pod_kill:222"}, budget=4)

    assert [item["candidate_id"] for item in result["selected_candidates"]] == [
        "p:a:network_loss:111",
        "p:b:pod_kill:222",
    ]


def test_parse_selection_output_rejects_pool_escape_and_result_labels() -> None:
    outside = json.dumps(
        {
            "selected_candidates": [
                {"candidate_id": "outside", "rank": 1, "reason": "core path"}
            ]
        }
    )
    with pytest.raises(ValueError, match="outside candidate"):
        parse_selection_output(outside, allowed_ids={"inside"}, budget=4)

    leaked = json.dumps(
        {
            "selected_candidates": [
                {"candidate_id": "inside", "rank": 1, "reason": "weakness_observed"}
            ]
        }
    )
    with pytest.raises(ValueError, match="forbidden"):
        parse_selection_output(leaked, allowed_ids={"inside"}, budget=4)


def test_parse_selection_output_rejects_duplicates_and_over_budget() -> None:
    duplicate = json.dumps(
        {
            "selected_candidates": [
                {"candidate_id": "a", "rank": 1, "reason": "one"},
                {"candidate_id": "a", "rank": 2, "reason": "two"},
            ]
        }
    )
    with pytest.raises(ValueError, match="duplicate"):
        parse_selection_output(duplicate, allowed_ids={"a"}, budget=4)

    too_many = json.dumps(
        {"selected_candidates": [{"candidate_id": str(i), "rank": i, "reason": "x"} for i in range(5)]}
    )
    with pytest.raises(ValueError, match="budget"):
        parse_selection_output(too_many, allowed_ids={str(i) for i in range(5)}, budget=4)


def test_run_selection_preflight_accepts_absolute_freeze_root(tmp_path) -> None:
    freeze = tmp_path / "freeze"
    write_freeze(freeze)

    output = tmp_path / "selection"
    result = run_selection(freeze_root=freeze, output=output, key_path=None, execute=False)

    assert result["status"] == "preflight_passed"
    assert result["calls"] == 27
    assert (output / "preflight.json").is_file()


def test_run_selection_preflight_accepts_relative_freeze_root(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    write_freeze(Path("freeze"))

    result = run_selection(freeze_root=Path("freeze"), output=Path("selection"), key_path=None, execute=False)

    assert result["status"] == "preflight_passed"
    assert result["calls"] == 27
