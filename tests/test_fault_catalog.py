from tools.compile_scenario_node import compile_scenario
from tools.deployment_capability import build_deployment_node
from tools.fault_catalog import get_fault_spec


def _scenario(fault_family: str):
    node = build_deployment_node(
        project_id="nginx-kubernetes-ingress",
        project_commit="f92a24e4fd2b52c72739c4a1f4f9bb6424bf5731",
        namespace="chaosatlas-nginx-ingress",
        deployment={
            "metadata": {"name": "nginx-ingress"},
            "spec": {
                "replicas": 1,
                "selector": {"matchLabels": {"app": "nginx-ingress"}},
                "template": {"metadata": {"labels": {"app": "nginx-ingress"}}, "spec": {"containers": [{"name": "nginx-ingress"}]}},
            },
        },
        service={"metadata": {"name": "nginx-ingress"}, "spec": {"ports": [{"port": 80}], "selector": {"app": "nginx-ingress"}}},
        source_refs=["test"],
        manifest_sha256="0" * 64,
    )
    parameters = {"latency_ms": 500, "jitter_ms": 0, "correlation": 100} if fault_family == "network_delay" else {"mode": "one"}
    return {
        "schema_version": 3,
        "node_type": "scenario_node",
        "scenario_id": "test-network-delay",
        "deployment_nodes": [node],
        "phases": [{
            "phase_id": "phase-1",
            "mode": "ordered",
            "duration_s": 5,
            "target_node_ids": [node["node_id"]],
            "inject_confirmation": "status.injectedCount >= 1",
            "cleanup_owner": "chaosatlas",
            "faults": [{
                "kind": fault_family,
                "action": "network-delay" if fault_family == "network_delay" else "pod-kill",
                "selector": {"app": "nginx-ingress"},
                "parameters": parameters,
                "target_node_id": node["node_id"],
            }],
        }],
        "oracle": {"business": {"kind": "http", "service": "nginx-ingress", "remote_port": 80}},
        "recovery": {"deadline_s": 60},
        "cleanup": {"required": True, "owner": "chaosatlas"},
    }


def test_network_delay_is_cataloged_as_implemented():
    spec = get_fault_spec("network_delay")

    assert spec["status"] == "implemented"
    assert spec["backend"] == "NetworkChaos"


def test_network_delay_compiles_to_networkchaos_delay_manifest():
    result = compile_scenario(_scenario("network_delay"))

    assert result["status"] == "verified"
    manifest = result["manifests"][0]
    assert manifest["kind"] == "NetworkChaos"
    assert manifest["spec"]["action"] == "delay"
    assert manifest["spec"]["delay"]["latency"] == "500ms"


def test_backend_pod_kill_uses_podchaos_backend_with_dependency_semantics():
    spec = get_fault_spec("backend_pod_kill")
    result = compile_scenario(_scenario("backend_pod_kill"))

    assert spec["status"] == "implemented"
    assert spec["semantic_alias"] == "pod_kill"
    assert result["status"] == "verified"
    assert result["manifests"][0]["kind"] == "PodChaos"
    assert result["manifests"][0]["spec"]["action"] == "pod-kill"
