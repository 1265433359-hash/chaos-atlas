import json
import subprocess
import sys
from pathlib import Path

from chaosatlas.cli import main
from chaosatlas.orchestration.engine import _read_json


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


def test_cli_live_is_rejected_before_engine_dispatch(tmp_path, capsys):
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

    def fake_run(_self, request):
        calls.update(vars(request))
        return {"status": "live_completed", "run_id": "live-test"}

    monkeypatch.setattr("chaosatlas.cli.RunEngine.run", fake_run)

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


def test_engine_json_reader_accepts_windows_utf8_bom(tmp_path):
    profile = tmp_path / "profile.json"
    profile.write_bytes(b"\xef\xbb\xbf{\"project_id\": \"resource-canary\"}")

    assert _read_json(profile)["project_id"] == "resource-canary"


def test_capabilities_cli_writes_one_result_per_profile_and_summary(tmp_path, monkeypatch, capsys):
    profiles = []
    for project_id in ("one", "two"):
        path = tmp_path / f"{project_id}-profile.json"
        path.write_text(json.dumps({"project_id": project_id, "project_commit": "r", "namespace_policy": {"allowed_namespaces": ["lab"]}}), encoding="utf-8")
        profiles.append(path)

    def fake_run(self):
        return {
            "status": "verified",
            "project_id": self.profile["project_id"],
            "catalog": {"core": 32, "extension": 9, "total": 41},
            "status_counts": {"blocked": 41},
            "read_only": True,
            "injection_performed": False,
            "errors": [],
        }

    monkeypatch.setattr("chaosatlas.capabilities.bootstrap.CapabilityBootstrapper.run", fake_run)
    output = tmp_path / "outside-output"
    result = main(["capabilities", "--profile", str(profiles[0]), "--profile", str(profiles[1]), "--output", str(output)])

    assert result == 0
    assert (output / "one.json").is_file()
    assert (output / "two.json").is_file()
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "verified"
    assert summary["project_count"] == 2
    assert summary["injection_performed"] is False
    assert json.loads(capsys.readouterr().out)["verified_count"] == 2


def test_capabilities_cli_preserves_success_when_another_profile_is_invalid(tmp_path, monkeypatch):
    valid = tmp_path / "valid.json"
    invalid = tmp_path / "invalid.json"
    valid.write_text(json.dumps({"project_id": "valid", "namespace_policy": {"allowed_namespaces": ["lab"]}}), encoding="utf-8")
    invalid.write_text("not json", encoding="utf-8")
    monkeypatch.setattr("chaosatlas.capabilities.bootstrap.CapabilityBootstrapper.run", lambda self: {"status": "verified", "project_id": "valid", "errors": [], "read_only": True, "injection_performed": False})

    output = tmp_path / "partial-output"
    result = main(["capabilities", "--profile", str(valid), "--profile", str(invalid), "--output", str(output)])

    assert result == 2
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "partial"
    assert (output / "valid.json").is_file()
    assert (output / "invalid.json").is_file()


def test_capabilities_cli_rejects_nonempty_output(tmp_path, capsys):
    output = tmp_path / "existing"
    output.mkdir()
    (output / "keep.json").write_text("{}", encoding="utf-8")
    result = main(["capabilities", "--profile", str(PROFILE), "--output", str(output)])
    assert result == 2
    assert "non-empty" in capsys.readouterr().err


def test_cli_module_entrypoint_is_executable():
    completed = subprocess.run(
        [sys.executable, "-m", "chaosatlas.cli", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert "capabilities" in completed.stdout
    assert "isolation" in completed.stdout


def test_isolation_plan_cli_selects_one_record_and_writes_external_plan(tmp_path, capsys):
    profile = tmp_path / "profile.json"
    matrix = tmp_path / "matrix.json"
    output = tmp_path / "plans" / "plan.json"
    profile.write_text(json.dumps({"project_id": "p", "project_commit": "r", "namespace_policy": {"allowed_namespaces": ["p-lab"]}, "isolation": {"l1": {"mode": "adopted-test-replica", "dedicated_test_replica": True}, "synthetic_data_only": True}}), encoding="utf-8")
    matrix.write_text(json.dumps({"target_capabilities": [{"fault_id": "pod_kill", "target_id": "n1", "required_isolation": "L1", "capability_status": "canary_required"}], "targets": [{"node_id": "n1", "deployment": {"name": "web"}}]}), encoding="utf-8")
    result = main(["isolation", "plan", "--profile", str(profile), "--capability-matrix", str(matrix), "--fault-id", "pod_kill", "--target-id", "n1", "--output", str(output)])
    assert result == 0
    assert json.loads(output.read_text(encoding="utf-8"))["provider"] == "kubernetes-l1"
    assert json.loads(capsys.readouterr().out)["injection_performed"] is False


def test_isolation_store_inside_repository_is_rejected(capsys):
    result = main(["isolation", "status", "--lease-id", "lease-safe", "--store-root", str(ROOT / ".forbidden-isolation")])
    assert result == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "method_invalid"
    assert "outside the repository" in payload["reason"]


def test_isolation_prepare_requires_explicit_approval(tmp_path, capsys):
    plan = tmp_path / "plan.json"
    plan.write_text("{}", encoding="utf-8")
    result = main(["isolation", "prepare", "--plan", str(plan), "--store-root", str(tmp_path / "store")])
    assert result == 2
    assert json.loads(capsys.readouterr().out)["reason"] == "approve_isolation_required"
