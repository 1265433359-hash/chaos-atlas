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


def test_inventory_skips_external_state_leaks_and_dependencies(tmp_path):
    from scripts.repository_inventory import build_inventory

    retained = tmp_path / "src" / "chaosatlas" / "core.py"
    retained.parent.mkdir(parents=True)
    retained.write_text("x", encoding="utf-8")
    for relative in (
        ".runs/run/result.json",
        ".email-notify-outbox/pending/message.json",
        "environment-reports/raw/.env",
        "projects/chaosatlas-apps/medusa/node_modules/pkg/index.js",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True)
        path.write_text("generated", encoding="utf-8")

    inventory = build_inventory(tmp_path)

    assert [entry["path"] for entry in inventory["files"]] == ["src/chaosatlas/core.py"]


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


def test_cli_defaults_to_dry_run_and_fails_closed_without_facts(tmp_path, capsys):
    from chaosatlas import cli

    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"project_id": "demo"}), encoding="utf-8")
    result = cli.main(["run", "--profile", str(profile), "--evidence-root", str(tmp_path / "evidence")])

    assert result == 1
    assert "method_invalid" in capsys.readouterr().out


def test_cli_live_is_rejected_before_engine_dispatch(tmp_path, capsys):
    from chaosatlas import cli

    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"project_id": "demo"}), encoding="utf-8")
    assert cli.main(["run", "--profile", str(profile), "--mode", "live", "--evidence-root", "runs/demo"]) == 2
    assert "approve-live" in capsys.readouterr().err


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


def test_cli_uses_packaged_run_engine():
    from chaosatlas import cli
    from chaosatlas.orchestration.engine import RunEngine

    assert cli.RunEngine is RunEngine


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


def test_product_snapshot_uses_packaged_run_engine_without_legacy_delegate(tmp_path):
    from scripts.build_product_snapshot import build_snapshot

    source = tmp_path / "source"
    package = source / "src" / "chaosatlas"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "cli.py").write_text("def main(argv=None): return 0\n", encoding="utf-8")
    orchestration = package / "orchestration"
    orchestration.mkdir()
    (orchestration / "__init__.py").write_text("", encoding="utf-8")
    (orchestration / "engine.py").write_text("class RunEngine: pass\n", encoding="utf-8")
    (source / "tools").mkdir()
    (source / "tools" / "chaosatlas.py").write_text("compatibility wrapper", encoding="utf-8")

    destination = tmp_path / "snapshot"
    build_snapshot(source, destination)

    assert (destination / "src" / "chaosatlas" / "orchestration" / "engine.py").is_file()
    assert not (destination / "tools" / "_legacy_chaosatlas.py").exists()
