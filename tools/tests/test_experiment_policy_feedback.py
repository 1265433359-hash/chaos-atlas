from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools.experiment_policy import new_policy_state
from tools.experiment_policy_feedback import ingest_runtime_result, write_policy_state
from tools.policy_calibration import new_calibration


def _candidate() -> dict:
    return {
        "candidate_id": "candidate-a",
        "target": "deployment:api",
        "target_kind": "deployment",
        "fault_family": "pod_kill",
        "status": "eligible",
        "parameters": {"mode": "one"},
        "causal_cluster_id": "cluster-a",
        "canonical_signature": "sig-a",
    }


def _classified_result() -> dict:
    return {
        "candidate_id": "candidate-a",
        "project_id": "demo",
        "project_commit": "a" * 40,
        "round_id": "round-1",
        "canonical_signature": "sig-a",
        "classification": "confirmed_weakness",
        "evidence_quality": "complete",
        "result_sha256": "c" * 64,
        "policy_input_sha256": "__STATE_HASH__",
    }


def test_ingest_runtime_result_updates_only_matching_candidate(tmp_path: Path):
    state = new_policy_state("demo", "a" * 40, 1001, [_candidate()])
    result = _classified_result()
    result["policy_input_sha256"] = state["input_sha256"]
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps(result), encoding="utf-8")
    updated = ingest_runtime_result(state, result_path)
    assert updated["candidate_states"]["candidate-a"]["status"] == "weakness"
    assert updated["candidate_states"]["candidate-a"]["run_count"] == 1


def test_ingest_can_update_calibration_without_changing_static_state(tmp_path: Path):
    state = new_policy_state("demo", "a" * 40, 1001, [_candidate()])
    result = _classified_result()
    result["policy_input_sha256"] = state["input_sha256"]
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps(result), encoding="utf-8")
    calibration = new_calibration("demo", "round-1")
    ingest_runtime_result(state, result_path, calibration=calibration, decision={"policy_selected_candidate_ids": ["candidate-a"]})
    assert calibration["metrics"]["confirmed_weaknesses"] == 1


def test_ingest_runtime_result_rejects_signature_mismatch(tmp_path: Path):
    state = new_policy_state("demo", "a" * 40, 1001, [_candidate()])
    result = _classified_result()
    result["policy_input_sha256"] = state["input_sha256"]
    result["canonical_signature"] = "other"
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(ValueError, match="signature"):
        ingest_runtime_result(state, result_path)


def test_policy_state_writer_uses_atomic_replace(tmp_path: Path):
    state = new_policy_state("demo", "a" * 40, 1001, [_candidate()])
    path = tmp_path / "policy-state.json"
    write_policy_state(state, path)
    assert json.loads(path.read_text(encoding="utf-8"))["project_id"] == "demo"
    assert not path.with_suffix(".json.tmp").exists()


def test_ingest_runtime_result_ignores_ineligible_environment_feedback(tmp_path: Path):
    state = new_policy_state("demo", "a" * 40, 1001, [_candidate()])
    result = {
        "candidate_id": "candidate-a",
        "project_id": "demo",
        "project_commit": "a" * 40,
        "canonical_signature": "sig-a",
        "classification": "environment_blocked",
        "eligible": False,
        "eligibility_reason": "environment_blocked",
        "result_sha256": "e" * 64,
        "policy_input_sha256": state["input_sha256"],
    }
    path = tmp_path / "blocked.json"
    path.write_text(json.dumps(result), encoding="utf-8")

    updated = ingest_runtime_result(state, path)

    row = updated["candidate_states"]["candidate-a"]
    assert row["status"] == "unknown"
    assert row["run_count"] == 0
    assert updated["history"] == []


def test_ingest_runtime_result_ignores_ineligible_cleanup_failure(tmp_path: Path):
    state = new_policy_state("demo", "a" * 40, 1001, [_candidate()])
    result = {
        "candidate_id": "candidate-a",
        "project_id": "demo",
        "project_commit": "a" * 40,
        "canonical_signature": "sig-a",
        "classification": "unsupported",
        "eligible": False,
        "eligibility_reason": "cleanup_not_verified",
        "result_sha256": "f" * 64,
        "policy_input_sha256": state["input_sha256"],
    }
    path = tmp_path / "dirty.json"
    path.write_text(json.dumps(result), encoding="utf-8")

    updated = ingest_runtime_result(state, path)

    assert updated["candidate_states"]["candidate-a"]["run_count"] == 0
