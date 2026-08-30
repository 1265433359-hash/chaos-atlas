import json
from pathlib import Path

from tools.chaosatlas_orchestrator import run_closed_loop


ROOT = Path(__file__).resolve().parents[1]


def _profile_copy(tmp_path: Path) -> Path:
    source = ROOT / "projects" / "sock-shop" / "profile.json"
    target = tmp_path / "sock-shop-profile.json"
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def test_dry_run_writes_all_stage_artifacts(tmp_path):
    output = tmp_path / "run"

    result = run_closed_loop(
        profile_path=_profile_copy(tmp_path),
        output_root=output,
        mode="dry-run",
        seed=7,
    )

    assert result["status"] == "dry_run_ready"
    assert result["completed_stages"][-1] == "regression"
    for name in (
        "onboard", "inventory", "server_deployment_detection", "mapping",
        "retrieval", "hypotheses", "gate", "baseline", "execute", "observe",
        "classify", "rca", "learn", "promote_defense", "regression",
    ):
        assert (output / f"{name}.json").is_file()
    for name in ("candidate_selection", "stop_decision", "evidence_plan", "cleanup_report"):
        assert (output / f"{name}.json").is_file()
    assert (output / "checkpoint.json").is_file()
    assert (output / "summary.json").is_file()


def test_dry_run_never_claims_runtime_weakness(tmp_path):
    output = tmp_path / "run"

    run_closed_loop(
        profile_path=_profile_copy(tmp_path),
        output_root=output,
        mode="dry-run",
        seed=7,
    )
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))

    assert summary["status"] == "dry_run_ready"
    assert summary["runtime_claims"] == []


def test_changed_input_on_resume_is_method_invalid(tmp_path):
    profile = _profile_copy(tmp_path)
    output = tmp_path / "run"
    run_closed_loop(profile_path=profile, output_root=output, mode="dry-run", seed=7)

    profile.write_text(profile.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    result = run_closed_loop(
        profile_path=profile,
        output_root=output,
        mode="dry-run",
        seed=7,
        resume=True,
    )

    assert result["status"] == "method_invalid"


def test_tampered_stage_artifact_on_resume_is_method_invalid(tmp_path):
    profile = _profile_copy(tmp_path)
    output = tmp_path / "run"
    run_closed_loop(profile_path=profile, output_root=output, mode="dry-run", seed=7)

    artifact_path = output / "inventory.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["payload"]["services"] = []
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

    result = run_closed_loop(
        profile_path=profile,
        output_root=output,
        mode="dry-run",
        seed=7,
        resume=True,
    )

    assert result["status"] == "method_invalid"


def test_invalid_profile_json_is_method_invalid(tmp_path):
    profile = tmp_path / "invalid-profile.json"
    profile.write_text("{", encoding="utf-8")

    result = run_closed_loop(
        profile_path=profile,
        output_root=tmp_path / "run",
        mode="dry-run",
        seed=7,
    )

    assert result["status"] == "method_invalid"
