import json
import subprocess
import sys
from pathlib import Path

import pytest


def test_inventory_classifies_product_and_evidence(tmp_path):
    from scripts.repository_inventory import build_inventory

    (tmp_path / "src" / "chaosatlas").mkdir(parents=True)
    (tmp_path / "artifacts" / "run-1").mkdir(parents=True)
    (tmp_path / "src" / "chaosatlas" / "core.py").write_text("x", encoding="utf-8")
    (tmp_path / "artifacts" / "run-1" / "result.json").write_text("{}", encoding="utf-8")

    inventory = build_inventory(tmp_path)
    by_path = {entry["path"]: entry for entry in inventory["files"]}

    assert by_path["src/chaosatlas/core.py"]["category"] == "product_code"
    assert by_path["artifacts/run-1/result.json"]["category"] == "evidence"
    assert inventory["summary"]["files"] == 2


def test_migration_manifest_rejects_sensitive_files(tmp_path):
    from scripts.migration_manifest import build_manifest

    (tmp_path / "projects").mkdir()
    (tmp_path / "projects" / "profile.json").write_text("{}", encoding="utf-8")
    (tmp_path / "kubeconfig").write_text("secret", encoding="utf-8")
    inventory = {
        "root": str(tmp_path),
        "files": [
            {"path": "projects/profile.json", "category": "project_input", "sensitive": False},
            {"path": "kubeconfig", "category": "runtime_state", "sensitive": True},
        ],
    }

    with pytest.raises(ValueError, match="sensitive"):
        build_manifest(inventory)


def test_cli_defaults_to_dry_run(monkeypatch, tmp_path, capsys):
    from chaosatlas import cli

    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"project_id": "demo"}), encoding="utf-8")
    monkeypatch.setattr(
        cli,
        "_run_legacy",
        lambda argv: (_ for _ in ()).throw(AssertionError("legacy execution")),
    )

    result = cli.main(
        ["run", "--profile", str(profile), "--evidence-root", str(tmp_path / "evidence")]
    )

    assert result == 0
    assert "dry-run" in capsys.readouterr().out


def test_cli_live_forwards_profile_and_output_to_legacy(monkeypatch, tmp_path):
    from chaosatlas import cli

    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"project_id": "demo"}), encoding="utf-8")
    captured = {}

    def fake_legacy(argv):
        captured["argv"] = argv
        return 0

    monkeypatch.setattr(cli, "_run_legacy", fake_legacy)

    assert cli.main(["run", "--profile", str(profile), "--mode", "live", "--evidence-root", "runs/demo"]) == 0
    assert captured["argv"] == [
        "run",
        "--profile",
        str(profile),
        "--mode",
        "live",
        "--output",
        "runs/demo",
    ]


def test_product_snapshot_excludes_evidence_and_runtime_state(tmp_path):
    from scripts.build_product_snapshot import build_snapshot

    for relative in (
        "src/chaosatlas/core.py",
        "projects/demo/profile.json",
        "docs/README.md",
        "artifacts/run.json",
        "raw_yaml/input.yaml",
        ".venv/pyvenv.cfg",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")

    destination = tmp_path / "snapshot"
    build_snapshot(tmp_path, destination)

    assert (destination / "src/chaosatlas/core.py").is_file()
    assert (destination / "projects/demo/profile.json").is_file()
    assert not (destination / "artifacts").exists()
    assert not (destination / "raw_yaml").exists()
    assert not (destination / ".venv").exists()


def test_acceptance_status_is_success_only_when_all_checks_pass():
    from scripts.run_repository_acceptance import acceptance_status

    assert acceptance_status([{"name": "cli", "ok": True}]) == "success"
    assert acceptance_status([{"name": "cli", "ok": False}]) == "failed"


def test_acceptance_can_target_an_explicit_product_root(tmp_path):
    from scripts.run_repository_acceptance import resolve_product_root

    product_root = tmp_path / "release"
    product_root.mkdir()

    assert resolve_product_root(tmp_path, str(product_root)) == product_root.resolve()


def test_live_legacy_path_resolves_inside_product_repository(monkeypatch, tmp_path):
    from chaosatlas import cli

    product_root = tmp_path / "product"
    tool = product_root / "tools" / "chaosatlas.py"
    tool.parent.mkdir(parents=True)
    tool.write_text("# compatibility entry\n", encoding="utf-8")
    monkeypatch.setattr(cli, "__file__", str(product_root / "src" / "chaosatlas" / "cli.py"))

    assert cli._legacy_tool_path() == tool


def test_product_snapshot_excludes_python_caches_and_generated_metadata(tmp_path):
    from scripts.build_product_snapshot import build_snapshot

    source = tmp_path / "source"
    (source / "src" / "chaosatlas").mkdir(parents=True)
    (source / "src" / "chaosatlas" / "__pycache__").mkdir()
    (source / "src" / "chaosatlas" / "__pycache__" / "cli.cpython-312.pyc").write_bytes(b"cache")
    (source / "src" / "chaosatlas.egg-info").mkdir()
    (source / "src" / "chaosatlas.egg-info" / "PKG-INFO").write_text("generated", encoding="utf-8")
    (source / "src" / "chaosatlas" / "core.py").write_text("x", encoding="utf-8")

    destination = tmp_path / "snapshot"
    build_snapshot(source, destination)

    assert (destination / "src" / "chaosatlas" / "core.py").is_file()
    assert not (destination / "src" / "chaosatlas" / "__pycache__").exists()
    assert not (destination / "src" / "chaosatlas.egg-info").exists()


def test_product_snapshot_compatibility_wrapper_imports_package(tmp_path):
    from scripts.build_product_snapshot import build_snapshot

    source = tmp_path / "source"
    package = source / "src" / "chaosatlas"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "cli.py").write_text(
        "import argparse\n"
        "def main(argv=None):\n"
        "    argparse.ArgumentParser(prog='chaosatlas').parse_args(argv)\n"
        "    return 0\n",
        encoding="utf-8",
    )

    destination = tmp_path / "snapshot"
    build_snapshot(source, destination)
    completed = subprocess.run(
        [sys.executable, str(destination / "tools" / "chaosatlas.py"), "--help"],
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0
    assert "usage:" in completed.stdout


def test_product_snapshot_keeps_minimal_legacy_runtime_delegate(tmp_path):
    from scripts.build_product_snapshot import build_snapshot

    source = tmp_path / "source"
    package = source / "src" / "chaosatlas"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "cli.py").write_text("def main(argv=None): return 0\n", encoding="utf-8")
    (source / "tools").mkdir()
    (source / "tools" / "chaosatlas.py").write_text("legacy", encoding="utf-8")

    destination = tmp_path / "snapshot"
    build_snapshot(source, destination)

    assert (destination / "tools" / "_legacy_chaosatlas.py").read_text(encoding="utf-8") == "legacy"
