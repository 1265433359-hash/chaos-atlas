from __future__ import annotations

import json
from copy import deepcopy

from tools.kubernetes_project_adapter import KubernetesProjectAdapter


PROFILE = {
    "project_id": "demo",
    "project_commit": "fixture-commit",
    "namespace_policy": {"allowed_namespaces": ["demo-lab"], "isolation_required": True},
    "business_oracles": [{"id": "home", "kind": "http", "entrypoint": "/", "success_contract": "http_200"}],
}


def _runner(responses):
    calls = []

    def run(args, timeout=30, input_text=None):
        del timeout, input_text
        calls.append(tuple(args))
        value = responses.get(tuple(args))
        if value is None:
            return 1, "", "unexpected command"
        return 0, json.dumps(value), ""

    return run, calls


def _responses():
    deployment = {
        "metadata": {"name": "front-end"},
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": {"name": "front-end"}},
            "template": {
                "metadata": {"labels": {"name": "front-end"}},
                "spec": {"containers": [{"name": "front-end", "readinessProbe": {"httpGet": {"path": "/", "port": 8079}}}]},
            },
        },
    }
    service = {
        "metadata": {"name": "front-end"},
        "spec": {"selector": {"name": "front-end"}, "ports": [{"port": 80, "targetPort": 8079}]},
    }
    pod = {"metadata": {"name": "front-end-1", "uid": "pod-1", "labels": {"name": "front-end"}}, "status": {"phase": "Running"}}
    ingress = {
        "metadata": {"name": "front-door", "namespace": "demo-lab"},
        "spec": {
            "rules": [{"http": {"paths": [{"path": "/", "pathType": "Prefix", "backend": {"service": {"name": "front-end", "port": {"number": 80}}}}]}}]
        },
    }
    return {
        ("get", "deployments", "-n", "demo-lab", "-o", "json"): {"items": [deployment]},
        ("get", "services", "-n", "demo-lab", "-o", "json"): {"items": [service]},
        ("get", "pods", "-n", "demo-lab", "-o", "json"): {"items": [pod]},
        ("get", "ingresses", "-n", "demo-lab", "-o", "json"): {"items": [ingress]},
    }


def test_live_adapter_builds_inventory_and_candidate_space_without_mutation():
    runner, calls = _runner(_responses())
    adapter = KubernetesProjectAdapter(profile=PROFILE, runner=runner)

    inventory = adapter.inventory()
    detection = adapter.detect_server_deployment(inventory)
    candidates = adapter.map_test_nodes(detection)

    assert inventory["status"] == "verified"
    assert inventory["deployments"][0]["metadata"]["name"] == "front-end"
    assert inventory["business_oracles"] == PROFILE["business_oracles"]
    assert inventory["dependencies"] == [
        {
            "source": "front-door",
            "target": "front-end",
            "relation": "routes_to",
            "source_kind": "ingress",
            "target_kind": "service",
            "evidence": "ingress/front-door",
        },
        {
            "source": "front-end",
            "target": "front-end",
            "relation": "selects",
            "source_kind": "service",
            "target_kind": "deployment",
            "evidence": "service/front-end",
        },
    ]
    assert detection["deployment_nodes"][0]["service"]["name"] == "front-end"
    assert any(item["fault_family"] == "pod_kill" for item in candidates["candidates"])
    assert not any(args[0] in {"apply", "delete", "patch", "create"} for args in calls)


def test_live_adapter_fails_closed_when_inventory_command_fails():
    runner, _ = _runner({})
    adapter = KubernetesProjectAdapter(profile=PROFILE, runner=runner)

    result = adapter.inventory()

    assert result["status"] == "environment_blocked"
    assert result["deployments"] == []
    assert result["errors"]


def test_live_adapter_keeps_service_target_bound_to_each_deployment():
    responses = _responses()
    deployments = responses[("get", "deployments", "-n", "demo-lab", "-o", "json")]["items"]
    services = responses[("get", "services", "-n", "demo-lab", "-o", "json")]["items"]
    pods = responses[("get", "pods", "-n", "demo-lab", "-o", "json")]["items"]

    second_deployment = deepcopy(deployments[0])
    second_deployment["metadata"]["name"] = "user-db"
    second_deployment["spec"]["selector"]["matchLabels"]["name"] = "user-db"
    second_deployment["spec"]["template"]["metadata"]["labels"]["name"] = "user-db"
    second_deployment["spec"]["template"]["spec"]["containers"][0]["name"] = "user-db"
    second_service = deepcopy(services[0])
    second_service["metadata"]["name"] = "user-db"
    second_service["spec"]["selector"]["name"] = "user-db"
    second_pod = deepcopy(pods[0])
    second_pod["metadata"]["name"] = "user-db-1"
    second_pod["metadata"]["labels"]["name"] = "user-db"
    deployments.append(second_deployment)
    services.append(second_service)
    pods.append(second_pod)

    runner, _ = _runner(responses)
    adapter = KubernetesProjectAdapter(profile=PROFILE, runner=runner)
    detection = adapter.detect_server_deployment(adapter.inventory())
    candidates = adapter.map_test_nodes(detection)["candidates"]

    front_end = next(item for item in candidates if item["target"] == "front-end" and item["fault_family"] == "pod_kill")
    user_db = next(item for item in candidates if item["target"] == "user-db" and item["fault_family"] == "pod_kill")
    assert front_end["service_target"] == "front-end"
    assert user_db["service_target"] == "user-db"


def test_live_adapter_pins_all_inventory_calls_to_explicit_kube_context():
    runner, calls = _runner({
        ("--context", "minikube", "get", "deployments", "-n", "demo-lab", "-o", "json"): _responses()[("get", "deployments", "-n", "demo-lab", "-o", "json")],
        ("--context", "minikube", "get", "services", "-n", "demo-lab", "-o", "json"): _responses()[("get", "services", "-n", "demo-lab", "-o", "json")],
        ("--context", "minikube", "get", "pods", "-n", "demo-lab", "-o", "json"): _responses()[("get", "pods", "-n", "demo-lab", "-o", "json")],
    })
    adapter = KubernetesProjectAdapter(profile=PROFILE, runner=runner, kube_context="minikube")

    result = adapter.inventory()

    assert result["status"] == "verified"
    assert all(args[:2] == ("--context", "minikube") for args in calls)
