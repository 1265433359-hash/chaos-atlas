from __future__ import annotations

from pathlib import Path

import yaml

from tools.fresh_deploy import FreshDeploymentAdapter


def _source(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    root.mkdir()
    (root / "deployment.yaml").write_text(
        yaml.safe_dump(
            {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": "front-end", "namespace": "chaosatlas-fresh"},
                "spec": {"replicas": 2},
            }
        ),
        encoding="utf-8",
    )
    return root


def test_fresh_deploy_dry_run_is_namespace_scoped_and_read_only(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def runner(args: list[str]) -> dict:
        calls.append(args)
        return {"return_code": 0, "stdout": "ok", "stderr": ""}

    adapter = FreshDeploymentAdapter(
        namespace="chaosatlas-fresh",
        allowed_namespaces={"chaosatlas-fresh"},
        runner=runner,
        allow_live=False,
    )

    result = adapter.deploy(_source(tmp_path))

    assert result["status"] == "dry_run_ready"
    assert result["live_mutation"] is False
    assert calls and "--dry-run=server" in calls[0]
    assert all("apply" in call for call in calls)


def test_fresh_deploy_requires_explicit_live_approval(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    adapter = FreshDeploymentAdapter(
        namespace="chaosatlas-fresh",
        allowed_namespaces={"chaosatlas-fresh"},
        runner=lambda args: calls.append(args) or {"return_code": 0, "stdout": "ok", "stderr": ""},
        allow_live=False,
    )

    result = adapter.apply_live(_source(tmp_path))

    assert result["status"] == "deployment_blocked"
    assert calls == []


def test_fresh_deploy_rejects_manifest_from_wrong_namespace(tmp_path: Path) -> None:
    source = _source(tmp_path)
    path = source / "deployment.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["metadata"]["namespace"] = "default"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    adapter = FreshDeploymentAdapter(
        namespace="chaosatlas-fresh",
        allowed_namespaces={"chaosatlas-fresh"},
        runner=lambda _args: {"return_code": 0, "stdout": "ok", "stderr": ""},
        allow_live=True,
    )

    result = adapter.deploy(source)

    assert result["status"] == "deployment_blocked"
    assert "namespace" in result["reason"]
