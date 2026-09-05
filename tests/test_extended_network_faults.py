import base64

from tools.compile_scenario_node import compile_scenario
from tools.deployment_capability import build_deployment_node
from chaosatlas.orchestration.engine import _live_scenario


def _scenario(fault_family: str, parameters: dict):
    node = build_deployment_node(
        project_id="fixture",
        project_commit="0" * 40,
        namespace="lab",
        deployment={
            "metadata": {"name": "web"},
            "spec": {
                "replicas": 1,
                "selector": {"matchLabels": {"app": "web"}},
                "template": {"metadata": {"labels": {"app": "web"}}, "spec": {"containers": [{"name": "web"}]}},
            },
        },
        service={"metadata": {"name": "web"}, "spec": {"ports": [{"port": 80}], "selector": {"app": "web"}}},
        source_refs=["test"],
        manifest_sha256="0" * 64,
    )
    return {
        "schema_version": 3,
        "node_type": "scenario_node",
        "scenario_id": "extended-network",
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
                "action": fault_family.replace("network_", ""),
                "selector": {"app": "web"},
                "parameters": parameters,
                "target_node_id": node["node_id"],
            }],
        }],
        "oracle": {"business": {"kind": "http", "service": "web", "remote_port": 80}},
        "recovery": {"deadline_s": 60},
        "cleanup": {"required": True, "owner": "chaosatlas"},
    }


def test_network_bandwidth_compiles_to_networkchaos_bandwidth():
    result = compile_scenario(_scenario("network_bandwidth", {"rate": "1mbps", "limit": 10, "buffer": 1}))
    assert result["status"] == "verified"
    manifest = result["manifests"][0]
    assert manifest["kind"] == "NetworkChaos"
    assert manifest["spec"]["action"] == "bandwidth"
    assert manifest["spec"]["bandwidth"]["rate"] == "1mbps"


def test_network_duplicate_compiles_to_networkchaos_duplicate():
    result = compile_scenario(_scenario("network_duplicate", {"duplicate_percent": 20, "correlation": 100}))
    assert result["status"] == "verified"
    assert result["manifests"][0]["spec"]["action"] == "duplicate"


def test_network_corrupt_compiles_to_networkchaos_corrupt():
    result = compile_scenario(_scenario("network_corrupt", {"corrupt_percent": 10, "correlation": 100}))
    assert result["status"] == "verified"
    assert result["manifests"][0]["spec"]["action"] == "corrupt"


def test_dns_failure_compiles_to_dnschaos_error():
    result = compile_scenario(_scenario("dns_failure", {"hostname": "catalogue"}))
    assert result["status"] == "verified"
    manifest = result["manifests"][0]
    assert manifest["kind"] == "DNSChaos"
    assert manifest["spec"]["action"] == "error"
    assert manifest["spec"]["patterns"] == ["catalogue"]


def test_dns_delay_compiles_to_dnschaos_delay():
    result = compile_scenario(_scenario("dns_delay", {"hostname": "catalogue", "latency_ms": 300}))
    assert result["status"] == "verified"
    manifest = result["manifests"][0]
    assert manifest["kind"] == "DNSChaos"
    assert manifest["spec"]["action"] == "delay"
    assert manifest["spec"]["delay"]["latency"] == "300ms"


def test_http_response_corrupt_compiles_with_httpchaos_replace_body():
    result = compile_scenario(_scenario("http_response_corrupt", {"port": 80, "path": "/", "body": "broken"}))
    assert result["status"] == "verified"
    assert result["manifests"][0]["spec"]["replace"]["body"] == base64.b64encode(b"broken").decode("ascii")


def test_http_status_error_rejects_status_above_http_range():
    result = compile_scenario(_scenario("http_status_error", {"port": 80, "path": "/", "status_code": 600}))
    assert result["status"] == "method_invalid"


def _live_inputs(fault_family: str):
    profile = {
        "project_id": "fixture",
        "business_oracles": [{"kind": "http", "service": "web", "remote_port": 80, "entrypoint": "/", "success_contract": "http_200"}],
        "recovery": {"deadline_s": 60},
        "cleanup": {"owner": "chaosatlas"},
    }
    inventory = {
        "project_id": "fixture",
        "project_commit": "0" * 40,
        "namespace": "lab",
        "deployments": [{
            "name": "web",
            "desired_replicas": 1,
            "selector": {"app": "web"},
            "spec": {"replicas": 1, "selector": {"matchLabels": {"app": "web"}}, "template": {"spec": {"containers": [{"name": "web"}]}}},
        }],
        "services": [{"metadata": {"name": "web"}, "spec": {"ports": [{"port": 80}]}}],
    }
    candidate = {"target": "web", "fault_family": fault_family, "selector": {"app": "web"}, "parameters": {}}
    return profile, inventory, candidate


def test_live_scenario_supports_network_expansion_defaults():
    expected = {
        "network_bandwidth": ("bandwidth", {"rate": "1mbps", "limit": 1000, "buffer": 1000}),
        "network_duplicate": ("duplicate", {"duplicate_percent": 20, "correlation": 100}),
        "network_corrupt": ("corrupt", {"corrupt_percent": 20, "correlation": 100}),
    }
    for family, (action, parameters) in expected.items():
        profile, inventory, candidate = _live_inputs(family)
        scenario = _live_scenario(profile=profile, inventory=inventory, candidate=candidate, scenario_id=f"{family}-live")
        fault = scenario["phases"][0]["faults"][0]
        assert fault["action"] == action
        assert fault["parameters"] == parameters


def test_live_scenario_preserves_explicit_invalid_network_values():
    profile, inventory, candidate = _live_inputs("network_bandwidth")
    candidate["parameters"] = {"rate": "1mbps", "limit": 0, "buffer": 1000}
    scenario = _live_scenario(profile=profile, inventory=inventory, candidate=candidate, scenario_id="invalid-bandwidth")
    fault = scenario["phases"][0]["faults"][0]

    assert fault["parameters"]["limit"] == 0
    assert compile_scenario(scenario)["status"] == "method_invalid"


def test_live_scenario_supports_dns_failure_defaults():
    profile, inventory, candidate = _live_inputs("dns_failure")
    scenario = _live_scenario(profile=profile, inventory=inventory, candidate=candidate, scenario_id="dns-failure-live")
    fault = scenario["phases"][0]["faults"][0]

    assert fault["action"] == "dns-error"
    assert fault["parameters"] == {"hostname": "web"}
    assert compile_scenario(scenario)["status"] == "verified"


def test_live_scenario_supports_dns_delay_defaults():
    profile, inventory, candidate = _live_inputs("dns_delay")
    scenario = _live_scenario(profile=profile, inventory=inventory, candidate=candidate, scenario_id="dns-delay-live")
    fault = scenario["phases"][0]["faults"][0]

    assert fault["action"] == "dns-delay"
    assert fault["parameters"] == {"hostname": "web", "latency_ms": 500}
    assert compile_scenario(scenario)["status"] == "verified"


def test_live_scenario_supports_http_fault_defaults():
    for family, action, expected in (
        ("http_delay", "http-delay", {"latency_ms": 500, "port": 80, "path": "/"}),
        ("http_abort", "http-abort", {"port": 80, "path": "/"}),
        ("http_status_error", "http-status-error", {"port": 80, "path": "/", "status_code": 503}),
    ):
        profile, inventory, candidate = _live_inputs(family)
        scenario = _live_scenario(profile=profile, inventory=inventory, candidate=candidate, scenario_id=f"{family}-live")
        fault = scenario["phases"][0]["faults"][0]

        assert fault["action"] == action
        assert fault["parameters"] == expected
        assert compile_scenario(scenario)["status"] == "verified"


def test_live_scenario_supports_next_http_fault_defaults():
    expected = {
        "http_response_corrupt": ("http-response-corrupt", {"body": "chaosatlas-response-corrupted", "port": 80, "path": "/"}),
        "dependency_error": ("dependency-error", {"port": 80, "path": "/", "status_code": 503}),
        "connection_reset": ("connection-reset", {"port": 80, "path": "/"}),
    }
    for family, (action, parameters) in expected.items():
        profile, inventory, candidate = _live_inputs(family)
        scenario = _live_scenario(profile=profile, inventory=inventory, candidate=candidate, scenario_id=f"{family}-live")
        fault = scenario["phases"][0]["faults"][0]
        assert fault["action"] == action
        assert fault["parameters"] == parameters
        assert compile_scenario(scenario)["status"] == "verified"


def test_live_scenario_supports_native_http_fault_defaults():
    expected = {
        "http_rate_limit": ("http-rate-limit", {"requests_per_window": 2, "window_s": 10, "status_code": 429, "port": 80, "path": "/"}),
        "business_dependency_unreachable": ("business-dependency-unreachable", {"port": 80, "path": "/"}),
    }
    for family, (action, parameters) in expected.items():
        profile, inventory, candidate = _live_inputs(family)
        scenario = _live_scenario(profile=profile, inventory=inventory, candidate=candidate, scenario_id=f"{family}-live")
        fault = scenario["phases"][0]["faults"][0]
        assert fault["action"] == action
        assert fault["parameters"] == parameters
        assert compile_scenario(scenario)["status"] == "verified"


def test_live_scenario_supports_kubernetes_api_fault_defaults():
    expected = {
        "replica_reduction": ("replica-reduction", {"replicas": 0}),
        "config_reload": ("config-reload", {"reload_token": "chaosatlas-config_reload-live"}),
        "config_drift": ("config-drift", {"value": "chaosatlas-config-drift"}),
    }
    for family, (action, parameters) in expected.items():
        profile, inventory, candidate = _live_inputs(family)
        scenario = _live_scenario(profile=profile, inventory=inventory, candidate=candidate, scenario_id=f"{family}-live")
        fault = scenario["phases"][0]["faults"][0]
        assert fault["action"] == action
        assert fault["parameters"] == parameters
        assert compile_scenario(scenario)["status"] == "verified"


def test_live_scenario_supports_native_resource_fault_defaults():
    expected = {
        "disk_pressure": {"path": "/tmp/chaosatlas-pressure", "size_mb": 16},
        "file_descriptor_exhaustion": {"count": 32},
        "process_exhaustion": {"count": 8},
    }
    for family, parameters in expected.items():
        profile, inventory, candidate = _live_inputs(family)
        scenario = _live_scenario(profile=profile, inventory=inventory, candidate=candidate, scenario_id=f"{family}-live")
        fault = scenario["phases"][0]["faults"][0]
        assert fault["parameters"] == parameters
        assert compile_scenario(scenario)["status"] == "verified"


def test_live_scenario_supports_remaining_fault_defaults():
    expected = {
        "env_misconfiguration": {"name": "CHAOSATLAS_MODE", "value": "chaosatlas-test-misconfigured"},
        "secret_rotation": {"secret_name": "web-secret", "key": "token", "value": "chaosatlas-test-placeholder"},
        "rollout_pause": {"paused": True},
        "image_pull_failure": {"image": "chaosatlas.invalid/not-found:test"},
        "pod_unschedulable": {"node_selector_key": "chaosatlas.invalid/never", "node_selector_value": "true"},
        "api_server_delay": {"latency_ms": 100},
    }
    for family, parameters in expected.items():
        profile, inventory, candidate = _live_inputs(family)
        profile["fault_defaults"] = {"secret_rotation": {"secret_name": "web-secret"}}
        scenario = _live_scenario(profile=profile, inventory=inventory, candidate=candidate, scenario_id=f"{family}-live")
        fault = scenario["phases"][0]["faults"][0]
        assert fault["parameters"] == parameters
        assert compile_scenario(scenario)["status"] == "verified"


def test_live_http_scenario_uses_service_target_port():
    profile, inventory, candidate = _live_inputs("http_delay")
    inventory["services"][0]["spec"]["ports"][0]["targetPort"] = 8079
    scenario = _live_scenario(profile=profile, inventory=inventory, candidate=candidate, scenario_id="http-target-port-live")

    assert scenario["phases"][0]["faults"][0]["parameters"]["port"] == 8079
