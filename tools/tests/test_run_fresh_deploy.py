from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import yaml

from tools.run_fresh_deploy import run_fresh_deploy


def _source(tmp_path: Path) -> Path:
    root = tmp_path / "fresh"
    root.mkdir()
    (root / "manifest.yaml").write_text(
        yaml.safe_dump(
            {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": "front-end", "namespace": "chaosatlas-fresh"},
            }
        ),
        encoding="utf-8",
    )
    return root


def test_run_fresh_deploy_defaults_to_server_dry_run(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    result = run_fresh_deploy(
        source_root=_source(tmp_path),
        namespace="chaosatlas-fresh",
        allowed_namespaces={"chaosatlas-fresh"},
        runner=lambda args: calls.append(args) or {"return_code": 0, "stdout": "ok", "stderr": ""},
    )

    assert result["status"] == "dry_run_ready"
    assert calls and "--dry-run=server" in calls[0]
    assert result["live_mutation"] is False


def test_run_fresh_deploy_requires_approval_for_apply_and_cleanup(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    runner = lambda args: calls.append(args) or {"return_code": 0, "stdout": "ok", "stderr": ""}
    source = _source(tmp_path)

    apply_result = run_fresh_deploy(
        source_root=source,
        namespace="chaosatlas-fresh",
        allowed_namespaces={"chaosatlas-fresh"},
        runner=runner,
        apply_live=True,
    )
    cleanup_result = run_fresh_deploy(
        source_root=source,
        namespace="chaosatlas-fresh",
        allowed_namespaces={"chaosatlas-fresh"},
        runner=runner,
        cleanup=True,
    )

    assert apply_result["status"] == "deployment_blocked"
    assert cleanup_result["status"] == "deployment_blocked"
    assert calls == []


def test_run_fresh_deploy_script_mode_imports_from_tools_directory() -> None:
    completed = subprocess.run(
        [sys.executable, "tools/run_fresh_deploy.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "--source-root" in completed.stdout
