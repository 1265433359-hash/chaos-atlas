from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from tools.build_deployment_capability_pool import build_pool


def test_build_pool_discovers_deployments_services_and_local_graph(tmp_path: Path):
    (tmp_path / "app.yaml").write_text(yaml.safe_dump_all([
        {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "api"}, "spec": {"replicas": 2, "selector": {"matchLabels": {"app": "api"}}, "template": {"metadata": {"labels": {"app": "api"}}, "spec": {"containers": [{"name": "api", "readinessProbe": {"httpGet": {"path": "/ready", "port": 8080}}}]}}}},
        {"apiVersion": "v1", "kind": "Service", "metadata": {"name": "api"}, "spec": {"selector": {"app": "api"}, "ports": [{"port": 80, "targetPort": 8080}]}},
    ]), encoding="utf-8")
    result = build_pool(tmp_path, project_id="p", project_commit="a" * 40, namespace="ns")
    assert result["status"] == "verified"
    assert len(result["deployment_nodes"]) == 1
    assert {edge["relation"] for edge in result["impact_graph"]} >= {"service_selector", "replicaset_pod"}
    assert "pod_kill" in result["candidates"][0]["fault_families"]


def test_build_pool_missing_commit_is_static_blocked(tmp_path: Path):
    result = build_pool(tmp_path, project_id="p", project_commit="", namespace="ns")
    assert result["status"] == "static_blocked"
    assert result["deployment_nodes"] == []
