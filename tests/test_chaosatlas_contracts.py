import json

import pytest

from tools.chaosatlas_contracts import (
    RunContext,
    StageResult,
    write_checkpoint,
    write_stage_artifact,
)


def test_run_context_exposes_stable_serializable_payload(tmp_path):
    context = RunContext.create(
        profile_path="profile.json",
        mode="dry-run",
        seed=7,
        output_root=tmp_path / "run",
    )

    payload = context.to_dict()

    assert payload["run_id"] == context.run_id
    assert payload["input_snapshot_sha256"] == context.input_snapshot_sha256
    assert payload["output_root"].endswith("run")
    assert json.loads(json.dumps(payload, sort_keys=True))["seed"] == 7


def test_stage_artifact_contains_hash_and_claim_scope(tmp_path):
    result = StageResult.completed("inventory", {"project_id": "sock-shop"})

    path = write_stage_artifact(tmp_path, result)
    saved = json.loads(path.read_text(encoding="utf-8"))

    assert saved["stage"] == "inventory"
    assert saved["status"] == "completed"
    assert saved["output_sha256"]
    assert saved["claim_scope"] == "static"


def test_checkpoint_rejects_unknown_stage(tmp_path):
    with pytest.raises(ValueError, match="unknown stage"):
        write_checkpoint(tmp_path, next_stage="unknown", completed_stages=[])
