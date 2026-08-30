from tools.kubernetes_project_adapter import KubernetesProjectAdapter


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
