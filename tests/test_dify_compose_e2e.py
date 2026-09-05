import json
from pathlib import Path

from scripts.run_dify_compose_e2e import main


ROOT = Path(__file__).resolve().parents[1]


def test_dify_profile_is_valid():
    profile = json.loads((ROOT / "projects" / "dify-docker" / "profile.json").read_text(encoding="utf-8"))
    from tools.project_onboarding import validate_project_profile

    assert validate_project_profile(profile)["valid"]


def test_e2e_cli_requires_live_approval_without_mutation(tmp_path):
    output = tmp_path / "e2e"
    code = main(["--profile", str(ROOT / "projects" / "dify-docker" / "profile.json"), "--output", str(output), "--service", "api"])
    assert code == 0
    plan = json.loads((output / "plan.json").read_text(encoding="utf-8"))
    assert plan["approval_required"] is True
    assert plan["services"] == ["api"]


def test_e2e_live_requires_external_compose_directory(tmp_path, capsys):
    output = tmp_path / "e2e"
    code = main([
        "--profile",
        str(ROOT / "projects" / "dify-docker" / "profile.json"),
        "--output",
        str(output),
        "--service",
        "api",
        "--approve-live",
    ])

    assert code == 3
    assert "requires --compose-dir" in capsys.readouterr().out
