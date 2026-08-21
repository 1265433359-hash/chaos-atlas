from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.chaosatlas_contracts import (
    RunContext,
    StageResult,
    write_checkpoint,
    write_stage_artifact,
)


def test_run_context_hash_excludes_output_directory(tmp_path: Path) -> None:
    first = RunContext.create(
        profile_path="profile.json",
        mode="dry-run",
        seed=7,
        output_root=tmp_path / "a",
    )
    second = RunContext.create(
        profile_path="profile.json",
        mode="dry-run",
        seed=7,
        output_root=tmp_path / "b",
    )

    assert first.input_snapshot_sha256 == second.input_snapshot_sha256


def test_stage_artifact_contains_status_hash_and_claim_scope(tmp_path: Path) -> None:
    result = StageResult.completed("inventory", payload={"project_id": "sock-shop"})

    path = write_stage_artifact(tmp_path, result)
    saved = json.loads(path.read_text(encoding="utf-8"))

    assert saved["stage"] == "inventory"
    assert saved["status"] == "completed"
    assert saved["output_sha256"]
    assert saved["claim_scope"] == "static"


def test_checkpoint_rejects_unknown_stage(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown stage"):
        write_checkpoint(tmp_path, next_stage="not-a-stage", completed_stages=[])

