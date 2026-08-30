import json
from pathlib import Path
import types

from chaosatlas.cli import main
from tools._legacy_chaosatlas import _read_json


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "projects" / "sock-shop" / "profile.json"


def test_cli_dry_run_returns_zero_and_writes_summary(tmp_path):
    output = tmp_path / "run"

    result = main(
        [
            "run",
            "--profile",
            str(PROFILE),
            "--mode",
            "dry-run",
            "--output",
            str(output),
        ]
    )

    assert result == 0
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "dry_run_ready"


def test_cli_live_is_rejected_before_legacy_dispatch(tmp_path, capsys):
    result = main(
        [
            "run",
            "--profile",
            str(PROFILE),
            "--mode",
            "live",
            "--output",
            str(tmp_path / "run"),
        ]
    )

    assert result != 0
    assert "approve-live" in capsys.readouterr().err


def test_cli_live_requires_new_output_directory(tmp_path, capsys):
    output = tmp_path / "run"
    output.mkdir()
    (output / "existing.json").write_text("{}", encoding="utf-8")

    result = main(
        [
            "run",
            "--profile",
            str(PROFILE),
            "--mode",
            "live",
            "--approve-live",
            "--output",
            str(output),
        ]
    )

    assert result != 0
    assert "non-empty" in capsys.readouterr().err


def test_cli_live_forwards_native_runner_options(tmp_path, monkeypatch, capsys):
    calls = {}

    legacy = types.ModuleType("tools._legacy_chaosatlas")

    def fake_run_closed_loop(**kwargs):
        calls.update(kwargs)
        return {"status": "live_completed", "run_id": "live-test"}

    legacy.run_closed_loop = fake_run_closed_loop
    monkeypatch.setitem(__import__("sys").modules, "tools._legacy_chaosatlas", legacy)

    output = tmp_path / "live"
    result = main(
        [
            "run",
            "--profile",
            str(PROFILE),
            "--mode",
            "live",
            "--approve-live",
            "--candidate-id",
            "candidate-1",
            "--kube-context",
            "minikube",
            "--advisory-provider",
            "deterministic",
            "--defense-history-root",
            str(tmp_path / "history"),
            "--knowledge-write-root",
            str(tmp_path / "knowledge"),
            "--registry-shadow",
            "--output",
            str(output),
        ]
    )

    assert result == 0
    assert calls["profile_path"] == Path(PROFILE)
    assert calls["output_root"] == output
    assert calls["mode"] == "live"
    assert calls["approve_live"] is True
    assert calls["candidate_id"] == "candidate-1"
    assert calls["kube_context"] == "minikube"
    assert calls["registry_shadow"] is True
    assert json.loads(capsys.readouterr().out)["status"] == "live_completed"


def test_cli_live_rejects_resume_before_dispatch(tmp_path, capsys):
    result = main(
        [
            "run",
            "--profile",
            str(PROFILE),
            "--mode",
            "live",
            "--approve-live",
            "--resume",
            "--output",
            str(tmp_path / "run"),
        ]
    )

    assert result != 0
    assert "resume" in capsys.readouterr().err


def test_legacy_json_reader_accepts_windows_utf8_bom(tmp_path):
    profile = tmp_path / "profile.json"
    profile.write_bytes(b"\xef\xbb\xbf{\"project_id\": \"resource-canary\"}")

    assert _read_json(profile)["project_id"] == "resource-canary"
