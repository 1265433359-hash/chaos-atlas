import json

from tools.evaluate_experiment_value_policy import main, replay_policy


def _candidate(candidate_id: str) -> dict:
    return {
        "candidate_id": candidate_id,
        "target": candidate_id,
        "target_kind": "deployment",
        "fault_family": "pod_kill",
        "causal_cluster_id": f"cluster-{candidate_id}",
        "estimated_cost": 1.0,
        "blast_radius": 0.0,
    }


def test_replay_is_deterministic_and_records_policy_vs_legacy_choices():
    result = replay_policy(
        project_id="demo",
        project_commit="a" * 40,
        seed=1001,
        candidates=[_candidate("candidate-a"), _candidate("candidate-b")],
        runtime_results=[
            {"candidate_id": "candidate-a", "classification": "confirmed_weakness", "result_sha256": "1" * 64},
            {"candidate_id": "candidate-b", "classification": "protected", "result_sha256": "2" * 64},
        ],
    )

    assert result["schema_version"] == "chaosatlas-experiment-policy-replay-v1"
    assert result["policy_version"] == "ig-stop-v1"
    assert result["input_sha256"]
    assert [item["policy_next_candidate_id"] for item in result["decisions"]] == ["candidate-a", "candidate-b"]
    assert result["replay_metadata"] == {"cluster_access": False, "model_called": False, "mutation_executed": False}
    assert result["stop_record"]["stop_reason"] in {"resolved", "low_expected_value", "replay_exhausted"}

    repeated = replay_policy(
        project_id="demo",
        project_commit="a" * 40,
        seed=1001,
        candidates=[_candidate("candidate-a"), _candidate("candidate-b")],
        runtime_results=[
            {"candidate_id": "candidate-a", "classification": "confirmed_weakness", "result_sha256": "1" * 64},
            {"candidate_id": "candidate-b", "classification": "protected", "result_sha256": "2" * 64},
        ],
    )
    assert repeated["input_sha256"] == result["input_sha256"]
    assert repeated["decisions"] == result["decisions"]


def test_replay_rejects_unknown_runtime_candidate():
    try:
        replay_policy(
            project_id="demo",
            project_commit="a" * 40,
            seed=1001,
            candidates=[_candidate("candidate-a")],
            runtime_results=[{"candidate_id": "unknown", "classification": "protected"}],
        )
    except ValueError as exc:
        assert "unknown candidate_id" in str(exc)
    else:
        raise AssertionError("unknown runtime candidates must fail closed")


def test_cli_accepts_list_runtime_payload(tmp_path, monkeypatch):
    candidates = tmp_path / "candidates.json"
    runtime = tmp_path / "runtime.json"
    output = tmp_path / "replay.json"
    candidates.write_text(json.dumps({"candidates": [_candidate("candidate-a")] }), encoding="utf-8")
    runtime.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "evaluate_experiment_value_policy",
            "--candidates",
            str(candidates),
            "--runtime-results",
            str(runtime),
            "--output",
            str(output),
            "--project-id",
            "demo",
            "--project-commit",
            "a" * 40,
        ],
    )

    assert main() == 0
    assert json.loads(output.read_text(encoding="utf-8"))["recorded_result_count"] == 0


def test_cli_accepts_stage_envelope_candidate_payload(tmp_path, monkeypatch):
    candidates = tmp_path / "candidates.json"
    runtime = tmp_path / "runtime.json"
    output = tmp_path / "replay.json"
    candidates.write_text(json.dumps({"payload": {"candidates": [_candidate("candidate-a")]}}), encoding="utf-8")
    runtime.write_text(json.dumps({"runtime_results": []}), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "evaluate_experiment_value_policy",
            "--candidates", str(candidates),
            "--runtime-results", str(runtime),
            "--output", str(output),
            "--project-id", "demo",
            "--project-commit", "a" * 40,
        ],
    )

    assert main() == 0
    assert json.loads(output.read_text(encoding="utf-8"))["stop_record"]["stop_reason"] == "replay_exhausted"


def test_cli_applies_read_only_policy_context(tmp_path, monkeypatch):
    candidates = tmp_path / "candidates.json"
    runtime = tmp_path / "runtime.json"
    context = tmp_path / "context.json"
    output = tmp_path / "replay.json"
    candidates.write_text(json.dumps({"candidates": [_candidate("candidate-a"), _candidate("candidate-b")] }), encoding="utf-8")
    runtime.write_text(json.dumps({"runtime_results": []}), encoding="utf-8")
    context.write_text(json.dumps({"boundary_candidate_ids": ["candidate-b"]}), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "evaluate_experiment_value_policy",
            "--candidates", str(candidates),
            "--runtime-results", str(runtime),
            "--context", str(context),
            "--output", str(output),
            "--project-id", "demo",
            "--project-commit", "a" * 40,
        ],
    )

    assert main() == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["selected_candidate_ids"] == []
    assert report["replay_metadata"]["policy_context"] == {"boundary_candidate_ids": ["candidate-b"]}
