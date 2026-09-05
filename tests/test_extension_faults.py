from tools.deployment_capability import build_deployment_node
from tools.extension_capability import assess_extension_capability, generate_extension_candidates
from tools.extension_fault_catalog import extension_catalog, extension_categories, get_extension_spec
from tools.extension_fault_compiler import compile_extension_fault
from tools.fault_catalog import fault_catalog
from tools.compile_scenario_node import compile_scenario
from tools.kubernetes_project_adapter import KubernetesProjectAdapter


def _node(*, extensions=None):
    return build_deployment_node(
        project_id="fixture",
        project_commit="0" * 40,
        namespace="chaosatlas-fixture",
        deployment={
            "metadata": {"name": "web"},
            "spec": {
                "replicas": 2,
                "selector": {"matchLabels": {"app": "web"}},
                "template": {
                    "metadata": {"labels": {"app": "web"}},
                    "spec": {"containers": [{"name": "web"}], "volumes": []},
                },
            },
            "extensions": extensions or {},
        },
        service={"metadata": {"name": "web"}, "spec": {"ports": [{"port": 80}], "selector": {"app": "web"}}},
        source_refs=["fixture/deployment/web"],
        manifest_sha256="0" * 64,
    )


def _scenario(node, extension_id, parameters):
    return {
        "schema_version": 3,
        "node_type": "scenario_node",
        "scenario_id": "extension-contract",
        "deployment_nodes": [node],
        "phases": [{
            "phase_id": "phase-1",
            "mode": "ordered",
            "duration_s": 10,
            "target_node_ids": [node["node_id"]],
            "inject_confirmation": "status.injectedCount >= 1",
            "cleanup_owner": "chaosatlas",
            "faults": [{
                "kind": extension_id,
                "action": extension_id,
                "selector": {"app": "web"},
                "parameters": parameters,
                "target_node_id": node["node_id"],
            }],
        }],
        "oracle": {"business": {"kind": "http", "service": "web", "remote_port": 80}},
        "recovery": {"deadline_s": 60},
        "cleanup": {"required": True, "owner": "chaosatlas"},
    }


def test_extension_catalog_is_separate_from_core_catalog():
    assert len(fault_catalog()) == 32
    assert len(extension_catalog()) == 9
    assert len(extension_categories()) == 7
    assert get_extension_spec("extension.io_delay").backend == "IOChaos"


def test_io_delay_requires_allowlisted_disposable_path():
    node = _node(extensions={"capabilities": {"iochaos": True, "disposable_target": True}, "writable_paths": ["/tmp/chaosatlas-test"]})
    params = {"path": "/tmp/chaosatlas-test", "latency_ms": 100, "percent": 25, "duration_s": 10}
    assert assess_extension_capability("extension.io_delay", node, params)["status"] == "supported"
    assert assess_extension_capability("extension.io_delay", node, {**params, "path": "/etc"})["status"] == "blocked"


def test_extension_compiler_builds_io_and_time_manifests():
    node = _node(extensions={"capabilities": {"iochaos": True, "timechaos": True, "disposable_target": True}, "writable_paths": ["/tmp/chaosatlas-test"]})
    io = compile_extension_fault(_scenario(node, "extension.io_delay", {"path": "/tmp/chaosatlas-test", "latency_ms": 100, "percent": 25, "duration_s": 10}), {"phase_id": "phase-1", "cleanup_owner": "chaosatlas"}, {"kind": "extension.io_delay", "selector": {"app": "web"}, "parameters": {"path": "/tmp/chaosatlas-test", "latency_ms": 100, "percent": 25, "duration_s": 10}, "target_node_id": node["node_id"]}, 0)
    assert io["kind"] == "IOChaos"
    assert io["spec"]["action"] == "latency"

    time_node = _node(extensions={"capabilities": {"timechaos": True, "disposable_target": True}})
    time = compile_extension_fault(_scenario(time_node, "extension.time_offset", {"offset_ms": 500, "duration_s": 10}), {"phase_id": "phase-1", "cleanup_owner": "chaosatlas"}, {"kind": "extension.time_offset", "selector": {"app": "web"}, "parameters": {"offset_ms": 500, "duration_s": 10}, "target_node_id": time_node["node_id"]}, 0)
    assert time["kind"] == "TimeChaos"
    assert time["spec"]["timeOffset"] == "+500ms"


def test_jvm_compiler_uses_verified_jvmchaos_schema_and_pid():
    node = _node(extensions={
        "capabilities": {"jvmchaos": True, "disposable_target": True},
        "runtime": {"jvm_present": True, "process_name": "java", "pid_hint": 42},
    })
    parameters = {"target_process": "java", "pause_ms": 100, "duration_s": 10}
    manifest = compile_extension_fault(
        _scenario(node, "extension.jvm_gc_pause", parameters),
        {"phase_id": "phase-1", "cleanup_owner": "chaosatlas"},
        {"kind": "extension.jvm_gc_pause", "selector": {"app": "web"}, "parameters": parameters, "target_node_id": node["node_id"]},
        0,
    )
    assert manifest["kind"] == "JVMChaos"
    assert manifest["spec"]["action"] == "latency"
    assert manifest["spec"]["pid"] == 42


def test_main_scenario_compiler_accepts_extension_intent():
    node = _node(extensions={"capabilities": {"iochaos": True, "disposable_target": True}, "writable_paths": ["/tmp/chaosatlas-test"]})
    scenario = _scenario(node, "extension.io_delay", {"path": "/tmp/chaosatlas-test", "latency_ms": 100, "percent": 25, "duration_s": 10})
    result = compile_scenario(scenario)
    assert result["status"] == "verified"
    assert result["manifests"][0]["kind"] == "IOChaos"


def test_jvm_is_inapplicable_without_a_discovered_jvm():
    node = _node(extensions={"capabilities": {"jvmchaos": True, "disposable_target": True}, "runtime": {"jvm_present": False}})
    result = assess_extension_capability("extension.jvm_gc_pause", node, {"target_process": "java", "pause_ms": 100, "duration_s": 10})
    assert result["status"] == "inapplicable"


def test_extension_candidates_have_stable_ids_and_only_include_supported_targets():
    node = _node(extensions={"capabilities": {"iochaos": True, "disposable_target": True}, "writable_paths": ["/tmp/chaosatlas-test"]})
    first = generate_extension_candidates([node])
    second = generate_extension_candidates([node])
    assert first["candidate_count"] == 2
    assert [item["candidate_id"] for item in first["candidates"]] == [item["candidate_id"] for item in second["candidates"]]
    assert {row["status"] for row in first["matrix"]} == {"supported", "inapplicable", "blocked"}
    native_node = _node(extensions={"capabilities": {"queue_agent": True, "connection_pool_agent": True, "pause_agent": True, "disposable_target": True}})
    native = generate_extension_candidates([native_node])
    assert {item["extension_id"] for item in native["candidates"]} == {"extension.queue_backlog", "extension.connection_pool_exhaustion", "extension.runtime_pause"}


def test_native_runtime_extensions_require_explicit_agents_and_compile_safely():
    node = _node(extensions={"capabilities": {"queue_agent": True, "connection_pool_agent": True, "pause_agent": True, "disposable_target": True}})
    queue_parameters = {"queue_name": "chaosatlas-test-queue", "depth": 100, "duration_s": 10}
    pool_parameters = {"pool_name": "test-pool", "connections": 20, "duration_s": 10}
    assert assess_extension_capability("extension.queue_backlog", node, queue_parameters)["status"] == "supported"
    assert assess_extension_capability("extension.connection_pool_exhaustion", node, pool_parameters)["status"] == "supported"
    pause_parameters = {"target_process": "python", "pause_ms": 100, "duration_s": 10}
    assert assess_extension_capability("extension.runtime_pause", node, pause_parameters)["status"] == "supported"
    for extension_id, parameters in (("extension.queue_backlog", queue_parameters), ("extension.connection_pool_exhaustion", pool_parameters)):
        result = compile_extension_fault(_scenario(node, extension_id, parameters), {"phase_id": "phase-1", "cleanup_owner": "chaosatlas"}, {"kind": extension_id, "selector": {"app": "web"}, "parameters": parameters, "target_node_id": node["node_id"]}, 0)
        assert result["kind"] == "ChaosAtlasNativeExtension"
        assert result["spec"]["faultFamily"] == extension_id
    result = compile_extension_fault(_scenario(node, "extension.runtime_pause", pause_parameters), {"phase_id": "phase-1", "cleanup_owner": "chaosatlas"}, {"kind": "extension.runtime_pause", "selector": {"app": "web"}, "parameters": pause_parameters, "target_node_id": node["node_id"]}, 0)
    assert result["kind"] == "ChaosAtlasNativeExtension"


def test_dependency_extension_compiles_source_to_target_networkchaos():
    node = _node(extensions={"capabilities": {"networkchaos": True}})
    edge = {
        "id": "web-cache",
        "source": "web",
        "target": "cache",
        "source_selector": {"app": "web"},
        "target_selector": {"app": "cache"},
    }
    scenario = _scenario(node, "extension.dependency_delay", {
        "latency_ms": 100,
        "jitter_ms": 0,
        "correlation": 100,
        "duration_s": 10,
    })
    scenario["phases"][0]["faults"][0]["edge"] = edge
    result = compile_extension_fault(
        scenario,
        scenario["phases"][0],
        scenario["phases"][0]["faults"][0],
        0,
    )
    assert result["kind"] == "NetworkChaos"
    assert result["spec"]["selector"]["labelSelectors"] == {"app": "web"}
    assert result["spec"]["target"]["selector"]["labelSelectors"] == {"app": "cache"}
    assert result["spec"]["delay"]["latency"] == "100ms"


def test_kubernetes_detection_keeps_extension_candidates_separate_from_core_candidates():
    node = _node(extensions={"capabilities": {"iochaos": True, "disposable_target": True}, "writable_paths": ["/tmp/chaosatlas-test"]})
    adapter = KubernetesProjectAdapter(profile={"project_id": "fixture", "namespace_policy": {"allowed_namespaces": ["chaosatlas-fixture"]}, "fault_support": {}})
    detection = adapter.detect_server_deployment({
        "status": "verified",
        "project_id": "fixture",
        "project_commit": "0" * 40,
        "namespace": "chaosatlas-fixture",
        "deployments": [{"metadata": {"name": "web"}, "spec": {"replicas": 2, "selector": {"matchLabels": {"app": "web"}}, "template": {"metadata": {"labels": {"app": "web"}}, "spec": {"containers": [{"name": "web"}]}}}, "extensions": node["extensions"]}],
        "services": [{"metadata": {"name": "web"}, "spec": {"selector": {"app": "web"}, "ports": [{"port": 80}]}}],
    })
    assert detection["status"] == "verified"
    assert len(detection["extension_candidates"]) == 2
    assert all(item["fault_family"].startswith("extension.") for item in detection["extension_candidates"])
