from chaosatlas.orchestration.engine import _live_scenario
from tools.compile_scenario_node import compile_scenario
from tools.fault_capability_registry import capability_for
from tools.fault_catalog import fault_catalog


def _compile_inputs():
    profile = {
        "project_id": "fixture",
        "business_oracles": [{"kind": "http", "service": "web", "remote_port": 80, "entrypoint": "/"}],
        "recovery": {"deadline_s": 60},
        "cleanup": {"required": True, "owner": "chaosatlas"},
    }
    inventory = {
        "project_id": "fixture",
        "project_commit": "0" * 40,
        "namespace": "lab",
        "deployments": [{
            "name": "web",
            "desired_replicas": 2,
            "selector": {"app": "web"},
            "spec": {
                "replicas": 2,
                "selector": {"matchLabels": {"app": "web"}},
                "template": {"metadata": {"labels": {"app": "web"}}, "spec": {"containers": [{"name": "web"}]}},
            },
        }],
        "services": [{
            "metadata": {"name": "web"},
            "spec": {"ports": [{"port": 80, "targetPort": 80}], "selector": {"app": "web"}},
        }],
    }
    return profile, inventory


def test_all_32_catalog_faults_compile_through_live_scenario_contract():
    profile, inventory = _compile_inputs()

    results = {}
    for fault_family in fault_catalog():
        candidate = {
            "candidate_id": f"candidate-{fault_family}",
            "target": "web",
            "service_target": "web",
            "fault_family": fault_family,
            "desired_replicas": 2,
            "selector": {"matchLabels": {"app": "web"}},
        }
        scenario = _live_scenario(
            profile=profile,
            inventory=inventory,
            candidate=candidate,
            scenario_id="catalog-contract",
        )
        results[fault_family] = compile_scenario(scenario)["status"]

    assert len(results) == 32
    assert set(results.values()) == {"verified"}


def test_kubernetes_api_fault_is_exposed_with_executor():
    capability = capability_for("config_reload")

    assert capability.status == "implemented"
    assert callable(capability.executor)


def test_unknown_fault_fails_closed():
    try:
        capability_for("not-a-real-fault")
    except KeyError as exc:
        assert "not-a-real-fault" in str(exc)
    else:
        raise AssertionError("unknown fault must fail closed")


def test_next_http_faults_are_registered_with_http_executor():
    for fault_id in ("http_response_corrupt", "dependency_error", "connection_reset"):
        capability = capability_for(fault_id)
        assert capability.status == "implemented"
        assert capability.backend == "HTTPChaos"
        assert callable(capability.executor)


def test_native_http_faults_are_registered_with_guarded_executor():
    for fault_id in ("http_rate_limit", "business_dependency_unreachable"):
        capability = capability_for(fault_id)
        assert capability.status == "implemented"
        assert capability.backend == "NativeExecutor"
        assert callable(capability.executor)


def test_remaining_faults_are_registered_with_guarded_executors():
    for fault_id in (
        "dns_failure", "dns_delay", "env_misconfiguration", "secret_rotation",
        "rollout_pause", "image_pull_failure", "pod_unschedulable", "api_server_delay",
    ):
        capability = capability_for(fault_id)
        assert capability.status == "implemented"
        assert callable(capability.executor)
