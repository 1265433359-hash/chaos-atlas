from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.run_p09_open_discovery import (
    BudgetError,
    OPEN_ARMS,
    build_prompt,
    build_open_records,
    ensure_open_budget,
    parse_open_output,
    prepare_open_output,
    write_utf8_bytes,
)


ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "artifacts" / "experiments" / "chaosatlas_10_projects"


def test_build_open_records_is_four_arms_by_three_seeds() -> None:
    records = build_open_records(EXP)

    assert len(records) == 12
    assert {(row["arm"], row["seed"]) for row in records} == {
        (arm, seed) for arm, _ in OPEN_ARMS for seed in (1001, 1002, 1003)
    }
    assert all(row["project_id"] == "P09" for row in records)
    assert all(row["namespace"] == "chaosatlas-p09" for row in records)
    assert all(row["max_hypotheses"] == 8 for row in records)


def test_open_records_hide_candidate_pool_and_preserve_topology_hash() -> None:
    records = build_open_records(EXP)
    assert all(not row["candidate_pool_visible"] for row in records)
    assert len({row["topology_hash"] for row in records}) == 1
    assert all(row["topology_hash"] for row in records)


def test_build_prompt_uses_frozen_prompt_with_full_output_schema() -> None:
    records = build_open_records(EXP)
    hashes: dict[tuple[int, str], str] = {}
    for record in records:
        system, user = build_prompt(record)
        frozen = record["prompt_path"].read_text(encoding="utf-8")
        assert system + "\n===== USER =====\n" + user == frozen
        assert "OUTPUT SCHEMA" in user
        assert '"project_id": "..."' in user
        assert '"call_chain"' in user
        hashes[(record["seed"], record["arm"])] = record["prompt_sha256"]
    assert len(set(hashes.values())) == 3
    for arm, _ in OPEN_ARMS:
        assert len({hashes[(seed, arm)] for seed in (1001, 1002, 1003)}) == 1
    assert hashes[(1001, "ChaosEater-adapter-open")] == hashes[(1001, "ChaosEater-open")]


def test_parse_open_output_requires_object_and_rejects_forbidden_keys() -> None:
    payload = {
        "method_id": "ChaosAtlas-KB-open",
        "project_id": "P09",
        "project_commit": "c" * 40,
        "hypotheses": [],
        "no_safe_hypothesis_reason": "no bounded hypothesis found",
    }
    assert parse_open_output(json.dumps(payload)) == payload

    forbidden = dict(payload)
    forbidden["hypotheses"] = [{"mutation_path": "secret"}]
    with pytest.raises(ValueError, match="forbidden"):
        parse_open_output(json.dumps(forbidden))


def test_prepare_open_output_refuses_nonempty_directory(tmp_path: Path) -> None:
    output = tmp_path / "open"
    output.mkdir()
    (output / "existing.json").write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError, match="nonempty"):
        prepare_open_output(output)


def test_open_budget_includes_prior_billed_tokens() -> None:
    ensure_open_budget(295_011, 1_200_000, 530_304)
    with pytest.raises(BudgetError, match="exceed"):
        ensure_open_budget(700_000, 1_200_000, 530_304)


def test_write_utf8_bytes_preserves_lf_hash_on_windows(tmp_path: Path) -> None:
    path = tmp_path / "raw.txt"
    text = "first\nsecond\n"
    write_utf8_bytes(path, text)
    assert path.read_bytes() == text.encode("utf-8")
