from __future__ import annotations

import pytest

from tools.chaosatlas_two_arm_protocol import (
    METHODS,
    PROJECTS,
    REPETITIONS,
    SEEDS,
    canonical_sha256,
    enumerate_matrix,
    pair_input_hashes,
    select_execution_hypotheses,
    validate_matrix_entry,
)


def test_matrix_is_exactly_three_projects_two_methods_three_seeds() -> None:
    matrix = enumerate_matrix()
    assert len(matrix) == 18
    assert {row["project_id"] for row in matrix} == set(PROJECTS)
    assert {row["method_id"] for row in matrix} == set(METHODS)
    assert {row["seed"] for row in matrix} == set(SEEDS)
    assert all(row["repetitions"] == REPETITIONS for row in matrix)


def test_matrix_rejects_unknown_identity() -> None:
    with pytest.raises(ValueError, match="unknown project"):
        validate_matrix_entry("P09", "ChaosAtlas-full", 1001)
    with pytest.raises(ValueError, match="unknown method"):
        validate_matrix_entry("online-boutique", "ChaosEater-full", 1001)
    with pytest.raises(ValueError, match="seed"):
        validate_matrix_entry("online-boutique", "ChaosAtlas-full", 7)


def test_paired_inputs_require_byte_identical_common_view() -> None:
    full = {"common_input": {"project_id": "online-boutique", "seed": 1001}, "knowledge_view": {"facts": []}}
    ablation = {"common_input": {"project_id": "online-boutique", "seed": 1001}, "knowledge_view": None}
    pair = pair_input_hashes(full, ablation)
    assert pair["common_equal"] is True
    assert pair["common_sha256"] == canonical_sha256(full["common_input"])

    altered = {**ablation, "common_input": {"project_id": "online-boutique", "seed": 1002}}
    with pytest.raises(ValueError, match="common input"):
        pair_input_hashes(full, altered)


def test_budget_selection_preserves_compiled_output_order_and_marks_remainder() -> None:
    hypotheses = [
        {"hypothesis_id": f"H{i}", "compile_status": "accepted" if i != 2 else "rejected"}
        for i in range(1, 8)
    ]
    result = select_execution_hypotheses(hypotheses)
    assert [item["hypothesis_id"] for item in result["selected"]] == ["H1", "H3", "H4", "H5"]
    assert result["budget_not_executed"] == ["H6", "H7"]
    assert result["rejected"] == ["H2"]


def test_two_repetitions_are_required_for_confirmed_weakness() -> None:
    assert REPETITIONS == 2
