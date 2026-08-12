from __future__ import annotations

from tools.yaml_topology import parse_documents


def test_kubernetes_topology_is_deterministic_and_exposes_defenses() -> None:
    docs = [
        {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "api", "namespace": "lab"}, "spec": {"replicas": 2, "template": {"metadata": {"labels": {"app": "api"}}, "spec": {"containers": [{"name": "api", "image": "example/api", "readinessProbe": {"httpGet": {"path": "/ready"}}, "resources": {"limits": {"cpu": "1"}}}]}}}},
        {"apiVersion": "v1", "kind": "Service", "metadata": {"name": "api", "namespace": "lab"}, "spec": {"selector": {"app": "api"}, "ports": [{"port": 80}]}},
        {"apiVersion": "policy/v1", "kind": "PodDisruptionBudget", "metadata": {"name": "api-pdb", "namespace": "lab"}, "spec": {"selector": {"matchLabels": {"app": "api"}}, "minAvailable": 1}},
    ]
    first = parse_documents(docs, ["a.yaml"])
    second = parse_documents(list(reversed(docs)), ["a.yaml"])
    assert first["graph_hash"] == second["graph_hash"]
    assert any(edge["kind"] == "selector_routes" for edge in first["edges"])
    defense = next(item for item in first["defenses"] if item["target"].endswith("deployment/api"))
    assert defense["attributes"]["replicas"] == 2
    assert defense["attributes"]["pod_disruption_budget"] is True
    assert defense["attributes"]["probes"]["readiness"] == 1


def test_compose_dependencies_are_method_neutral_edges() -> None:
    result = parse_documents([{"services": {"api": {"depends_on": {"db": {"condition": "service_healthy"}, "cache": {}}}, "db": {"healthcheck": {"test": ["CMD", "true"]}}, "cache": {}}}])
    assert {edge["target"] for edge in result["edges"]} == {"compose/service/cache", "compose/service/db"}
    api_defense = next(item for item in result["defenses"] if item["target"].endswith("/api"))
    assert api_defense["attributes"]["healthcheck"] is False


def test_empty_pdb_selector_is_not_claimed_as_workload_protection() -> None:
    result = parse_documents([
        {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "api", "namespace": "lab"}, "spec": {"template": {"metadata": {"labels": {"app": "api"}}, "spec": {"containers": [{"name": "api"}]}}}},
        {"apiVersion": "policy/v1", "kind": "PodDisruptionBudget", "metadata": {"name": "empty", "namespace": "lab"}, "spec": {"selector": {}}},
    ])
    defense = result["defenses"][0]["attributes"]
    assert defense["pod_disruption_budget"] is False
