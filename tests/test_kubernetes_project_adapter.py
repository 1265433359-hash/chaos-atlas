import json

from tools.kubernetes_project_adapter import KubernetesProjectAdapter
from tools.compile_scenario_node import compile_scenario


def _runner(args, **_kwargs):
    resource = args[1]
    payloads = {
        "deployments": {"items": [{
            "metadata": {"name": "web", "namespace": "lab", "labels": {"app": "web"}},
            "spec": {"replicas": 1, "selector": {"matchLabels": {"app": "web"}}, "template": {"metadata": {"labels": {"app": "web"}}, "spec": {"containers": [{"name": "web"}]}}},
        }]},
        "services": {"items": [{"metadata": {"name": "web", "namespace": "lab"}, "spec": {"selector": {"app": "web"}, "ports": [{"port": 80}]}}]},
        "pods": {"items": []},
        "ingresses": {"items": []},
    }
    import json
    return 0, json.dumps(payloads[resource]), ""


def test_live_detection_uses_project_declared_supported_faults():
    profile = {
        "project_id": "fixture",
        "project_commit": "fixture",
        "namespace_policy": {"allowed_namespaces": ["lab"]},
        "runtime_contract": {"supported_fault_families": ["pod_kill", "network_delay", "config_reload"]},
    }

    adapter = KubernetesProjectAdapter(profile=profile, runner=_runner)
    result = adapter.detect_server_deployment(adapter.inventory())

    assert result["status"] == "verified"
    assert {item["fault_family"] for item in result["candidates"]} == {"pod_kill", "network_delay", "config_reload"}


def test_capability_node_discovery_is_independent_of_supported_faults():
    base = {
        "project_id": "fixture",
        "project_commit": "fixture",
        "namespace_policy": {"allowed_namespaces": ["lab"]},
    }
    first = KubernetesProjectAdapter(profile={**base, "runtime_contract": {"supported_fault_families": ["pod_kill"]}}, runner=_runner)
    second = KubernetesProjectAdapter(profile={**base, "runtime_contract": {"supported_fault_families": ["network_delay"]}}, runner=_runner)

    first_nodes = first.build_capability_nodes(first.inventory())
    second_nodes = second.build_capability_nodes(second.inventory())

    assert first_nodes["status"] == "verified"
    assert first_nodes["deployment_nodes"] == second_nodes["deployment_nodes"]
    assert first_nodes["read_only"] is True


def test_live_detection_expands_profile_parameter_ladder():
    profile = {
        "project_id": "fixture",
        "project_commit": "fixture",
        "namespace_policy": {"allowed_namespaces": ["lab"]},
        "runtime_contract": {"supported_fault_families": ["network_delay"]},
        "candidate_generation": {
            "parameter_ladders": {
                "network_delay": [
                    {"level": "baseline", "parameters": {"latency_ms": 500, "jitter_ms": 0, "correlation": 100}},
                    {"level": "low", "parameters": {"latency_ms": 100, "jitter_ms": 0, "correlation": 100}},
                ]
            }
        },
    }

    result = KubernetesProjectAdapter(profile=profile, runner=_runner).detect_server_deployment(
        KubernetesProjectAdapter(profile=profile, runner=_runner).inventory()
    )

    node_id = result["candidates"][0]["node_id"]
    assert [item["candidate_id"] for item in result["candidates"]] == [
        f"server:{node_id}:network_delay",
        f"server:{node_id}:network_delay:low",
    ]
    assert result["candidates"][1]["parameters"]["latency_ms"] == 100
    assert result["candidates"][0]["causal_cluster_id"] == result["candidates"][1]["causal_cluster_id"]


def test_live_detection_generates_dependency_edge_candidates_from_profile():
    profile = {
        "project_id": "fixture",
        "project_commit": "fixture",
        "namespace_policy": {"allowed_namespaces": ["lab"]},
        "runtime_contract": {"supported_fault_families": ["network_delay"]},
        "dependency_edges": [{
            "id": "web-cache",
            "source": "web",
            "target": "cache",
            "oracle_id": "web-http",
        }],
    }

    def runner(args, **_kwargs):
        resource = args[1]
        if resource == "deployments":
            payload = {"items": [{
                "metadata": {"name": "web", "namespace": "lab", "labels": {"app": "web"}},
                "spec": {"replicas": 1, "selector": {"matchLabels": {"app": "web"}}, "template": {"metadata": {"labels": {"app": "web"}}, "spec": {"containers": [{"name": "web"}]}}},
            }]}
        elif resource == "services":
            payload = {"items": [
                {"metadata": {"name": "web", "namespace": "lab"}, "spec": {"selector": {"app": "web"}, "ports": [{"port": 80}]}},
                {"metadata": {"name": "cache", "namespace": "lab"}, "spec": {"selector": {"app": "cache"}, "ports": [{"port": 6379}]}},
            ]}
        else:
            payload = {"items": []}
        import json
        return 0, json.dumps(payload), ""

    result = KubernetesProjectAdapter(profile=profile, runner=runner).detect_server_deployment(
        KubernetesProjectAdapter(profile=profile, runner=runner).inventory()
    )
    dependency = [item for item in result["extension_candidates"] if item["fault_family"] == "extension.dependency_delay"]
    assert len(dependency) == 1
    assert dependency[0]["target_kind"] == "dependency_edge"
    assert dependency[0]["edge"]["target_selector"] == {"app": "cache"}


def test_live_inventory_discovers_statefulsets_and_related_resources_without_secret_values():
    profile = {
        "project_id": "fixture",
        "project_commit": "fixture",
        "namespace_policy": {"allowed_namespaces": ["lab"]},
        "runtime_contract": {"supported_fault_families": ["pod_kill", "replica_reduction"]},
    }
    payloads = {
        "deployments": {"items": []},
        "statefulsets": {"items": [{
            "metadata": {"name": "redis", "namespace": "lab", "labels": {"app": "redis"}},
            "kind": "StatefulSet",
            "spec": {"replicas": 1, "selector": {"matchLabels": {"app": "redis", "component": "primary"}}, "serviceName": "redis-headless", "template": {"metadata": {"labels": {"app": "redis", "component": "primary"}}, "spec": {"containers": [{"name": "redis"}], "volumes": []}}, "volumeClaimTemplates": [{"metadata": {"name": "data"}}]},
        }]},
        "daemonsets": {"items": []},
        "services": {"items": [{"metadata": {"name": "redis", "namespace": "lab"}, "spec": {"selector": {"app": "redis"}, "ports": [{"port": 6379}]}}]},
        "pods": {"items": []},
        "ingresses": {"items": []},
        "persistentvolumeclaims": {"items": [{"metadata": {"name": "data-redis-0", "namespace": "lab"}, "spec": {"accessModes": ["ReadWriteOnce"], "resources": {"requests": {"storage": "1Gi"}}, "storageClassName": "standard"}, "status": {"phase": "Bound"}}]},
        "configmaps": {"items": [{"metadata": {"name": "redis-config", "namespace": "lab"}, "data": {"password": "must-not-leak"}}]},
        "secrets": {"items": [{"metadata": {"name": "redis-secret", "namespace": "lab"}, "data": {"password": "c2Vuc2l0aXZl"}}]},
        "horizontalpodautoscalers": {"items": [{"metadata": {"name": "redis-hpa", "namespace": "lab"}, "spec": {"scaleTargetRef": {"kind": "StatefulSet", "name": "redis"}, "minReplicas": 1, "maxReplicas": 3}}]},
        "poddisruptionbudgets": {"items": [{"metadata": {"name": "redis-pdb", "namespace": "lab"}, "spec": {"minAvailable": 1, "selector": {"matchLabels": {"app": "redis"}}}}]},
        "jobs": {"items": []},
    }

    def runner(args, **_kwargs):
        resource = args[1]
        import json
        return 0, json.dumps(payloads[resource]), ""

    adapter = KubernetesProjectAdapter(profile=profile, runner=runner)
    inventory = adapter.inventory()
    assert inventory["status"] == "verified"
    assert [item["metadata"]["name"] for item in inventory["statefulsets"]] == ["redis"]
    assert inventory["configmaps"] == [{"name": "redis-config", "namespace": "lab", "labels": {}}]
    assert inventory["secrets"] == [{"name": "redis-secret", "namespace": "lab", "labels": {}}]
    assert inventory["persistentvolumeclaims"][0]["status"]["phase"] == "Bound"
    assert "must-not-leak" not in json.dumps(inventory)
    detection = adapter.detect_server_deployment(inventory)
    assert detection["status"] == "verified"
    assert len(detection["deployment_nodes"]) == 1
    node = detection["deployment_nodes"][0]
    assert node["deployment"]["workload_kind"] == "StatefulSet"
    assert node["service"]["name"] == "redis"
    assert node["availability_profile"]["hpa"]["name"] == "redis-hpa"
    assert node["availability_profile"]["pdb"]["name"] == "redis-pdb"
    assert detection["candidates"][0]["target_kind"] == "statefulset"
    candidate = next(item for item in detection["candidates"] if item["fault_family"] == "replica_reduction")
    scenario = {
        "schema_version": 3,
        "node_type": "scenario_node",
        "scenario_id": "stateful-compile",
        "deployment_nodes": [node],
        "phases": [{"phase_id": "p", "mode": "ordered", "duration_s": 10, "target_node_ids": [node["node_id"]], "inject_confirmation": "ok", "cleanup_owner": "chaosatlas", "faults": [{"kind": "replica_reduction", "action": "replica_reduction", "selector": candidate["selector"], "parameters": {"replicas": 0}, "target_node_id": node["node_id"]}]}],
        "oracle": {"kind": "http", "service": "redis", "remote_port": 6379},
        "recovery": {"deadline_s": 60},
        "cleanup": {"required": True, "owner": "chaosatlas"},
    }
    compiled = compile_scenario(scenario)
    assert compiled["status"] == "verified"
    assert compiled["manifests"][0]["spec"]["targetRef"]["kind"] == "StatefulSet"
