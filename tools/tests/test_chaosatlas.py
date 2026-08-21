from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.chaosatlas import run_closed_loop
from tools.chaosatlas_contracts import STAGES


REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE = REPO_ROOT / "artifacts" / "project_profiles" / "sock-shop" / "project_profile.json"


def test_dry_run_executes_correct_stage_order_and_writes_all_artifacts(tmp_path: Path) -> None:
    output = tmp_path / "run"

    result = run_closed_loop(profile_path=PROFILE, output_root=output, mode="dry-run", seed=1001)

    assert result["status"] == "dry_run_ready"
    assert result["completed_stages"] == list(STAGES)
    for name in (
        "inventory.json",
        "server_deployment_detection.json",
        "candidate_space.json",
        "retrieval.json",
        "hypotheses.json",
        "finding_report.json",
        "rca_report.json",
        "knowledge_draft.json",
        "regression_intents.json",
        "cleanup_report.json",
        "summary.md",
        "checkpoint.json",
    ):
        assert (output / name).is_file(), name


def test_dry_run_never_emits_runtime_weakness_or_defense_claim(tmp_path: Path) -> None:
    output = tmp_path / "run"
    run_closed_loop(profile_path=PROFILE, output_root=output, mode="dry-run")

    text = "\n".join(path.read_text(encoding="utf-8") for path in output.glob("*.json"))
    assert '"weakness_status": "confirmed"' not in text
    assert '"result": "weakness"' not in text
    assert '"result": "defended"' not in text
    assert '"rca_status": "confirmed"' not in text


def test_invalid_profile_stops_before_inventory(tmp_path: Path) -> None:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    profile["namespace_policy"]["allowed_namespaces"] = ["default"]
    bad_profile = tmp_path / "bad.json"
    bad_profile.write_text(json.dumps(profile), encoding="utf-8")

    result = run_closed_loop(profile_path=bad_profile, output_root=tmp_path / "run", mode="dry-run")

    assert result["status"] == "method_invalid"
    assert not (tmp_path / "run" / "inventory.json").exists()


def test_resume_skips_completed_stages_and_reuses_input_hash(tmp_path: Path) -> None:
    output = tmp_path / "run"
    first = run_closed_loop(profile_path=PROFILE, output_root=output, mode="dry-run")
    second = run_closed_loop(profile_path=PROFILE, output_root=output, mode="dry-run", resume=True)

    assert second["status"] == "dry_run_ready"
    assert first["input_snapshot_sha256"] == second["input_snapshot_sha256"]
    assert second["resumed"] is True


def test_non_empty_output_is_rejected_without_overwriting_files(tmp_path: Path) -> None:
    output = tmp_path / "run"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("preserve", encoding="utf-8")

    with pytest.raises(FileExistsError):
        run_closed_loop(profile_path=PROFILE, output_root=output, mode="dry-run")

    assert marker.read_text(encoding="utf-8") == "preserve"


@pytest.mark.parametrize(
    "project_id",
    ["sock-shop", "online-boutique", "p02"],
)
def test_offline_replay_uses_one_orchestrator_for_three_projects(tmp_path: Path, project_id: str) -> None:
    profile = (
        REPO_ROOT
        / "tools"
        / "tests"
        / "fixtures"
        / "chaosatlas_offline"
        / project_id
        / "project_profile.json"
    )
    output = tmp_path / project_id

    result = run_closed_loop(profile_path=profile, output_root=output, mode="dry-run")

    assert result["status"] == "dry_run_ready"
    assert result["completed_stages"] == list(STAGES)
    inventory = json.loads((output / "inventory.json").read_text(encoding="utf-8"))
    assert inventory["payload"]["project_id"] == project_id
    assert not any('"result": "weakness"' in path.read_text(encoding="utf-8") for path in output.glob("*.json"))
