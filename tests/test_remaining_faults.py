import json

from tools.compile_scenario_node import compile_scenario
from tools.deployment_capability import build_deployment_node
from tools.kubernetes_fault_executor import KubernetesApiFaultExecutor, build_mutation
from tools.kubernetes_lifecycle_executor import KubernetesLifecycleExecutor


def _scenario(family, parameters):
    node = build_deployment_node(
        project_id="fixture",
        project_commit="0" * 40,
        namespace="lab",
        deployment={
            "metadata": {"name": "web"},
            "spec": {
                "replicas": 2,
                "selector": {"matchLabels": {"app": "web"}},
                "template": {
                    "metadata": {"labels": {"app": "web"}},
                    "spec": {"containers": [{"name": "web", "image": "web:v1"}]},
                },
            },
        },
        service={"metadata": {"name": "web"}, "spec": {"ports": [{"port": 80}], "selector": {"app": "web"}}},
        source_refs=["test"],
        manifest_sha256="0" * 64,
    )
    return {
        "schema_version": 3,
        "node_type": "scenario_node",
        "scenario_id": "remaining-faults",
        "deployment_nodes": [node],
        "phases": [{
            "phase_id": "phase-1", "mode": "ordered", "duration_s": 5,
            "target_node_ids": [node["node_id"]],
            "inject_confirmation": "status.injectedCount >= 1",
            "cleanup_owner": "chaosatlas",
            "faults": [{"kind": family, "action": family, "selector": {"app": "web"},
                        "parameters": parameters, "target_node_id": node["node_id"]}],
        }],
        "oracle": {"business": {"kind": "http", "service": "web", "remote_port": 80}},
        "recovery": {"deadline_s": 60},
        "cleanup": {"required": True, "owner": "chaosatlas"},
    }


def test_remaining_faults_compile_to_explicit_manifests():
    cases = {
        "env_misconfiguration": {"name": "CHAOSATLAS_MODE", "value": "broken"},
        "secret_rotation": {"secret_name": "web-secret", "key": "token", "value": "chaosatlas-test-placeholder"},
        "rollout_pause": {"paused": True},
        "image_pull_failure": {"image": "chaosatlas.invalid/not-found:test"},
        "pod_unschedulable": {"node_selector_key": "chaosatlas.invalid/never", "node_selector_value": "true"},
        "api_server_delay": {"latency_ms": 100},
    }
    for family, parameters in cases.items():
        result = compile_scenario(_scenario(family, parameters))
        assert result["status"] == "verified", (family, result)
        assert result["manifests"][0]["kind"] in {"ChaosAtlasKubernetesFault", "ChaosAtlasControlPlaneFault"}


def _deployment():
    return {
        "metadata": {"name": "web", "namespace": "lab"},
        "spec": {
            "replicas": 2,
            "paused": False,
            "template": {
                "metadata": {"annotations": {"keep": "yes"}},
                "spec": {"containers": [{"name": "web", "image": "web:v1", "env": [{"name": "KEEP", "value": "1"}]}]},
            },
        },
    }


def test_configuration_and_release_mutations_restore_exact_snapshot():
    for family, params in (
        ("env_misconfiguration", {"name": "CHAOSATLAS_MODE", "value": "broken"}),
        ("image_pull_failure", {"image": "chaosatlas.invalid/not-found:test"}),
        ("rollout_pause", {"paused": True}),
        ("pod_unschedulable", {"node_selector_key": "chaosatlas.invalid/never", "node_selector_value": "true"}),
    ):
        mutation = build_mutation(family, _deployment(), params)
        assert mutation["snapshot_sha256"]
        assert mutation["restore_patch"]
        assert mutation["changed_path"]


def test_secret_rotation_redacts_value_and_restores_secret_data():
    secret = {"metadata": {"name": "web-secret", "namespace": "lab"}, "data": {"token": "b2xk"}}
    mutation = build_mutation("secret_rotation", secret, {"key": "token", "value": "chaosatlas-test-placeholder"})
    assert mutation["patch"]["data"]["token"] != "chaosatlas-test-placeholder"
    assert mutation["restore_patch"] == {"data": {"token": "b2xk"}}
    assert "value" not in mutation["evidence_parameters"]


def test_high_risk_scheduling_fault_requires_disposable_isolation():
    executor = KubernetesApiFaultExecutor(namespace="lab", allowed_namespaces={"lab"}, allow_live=True, isolated=False)
    result = executor({
        "kind": "ChaosAtlasKubernetesFault", "metadata": {"name": "fault", "namespace": "lab"},
        "spec": {"faultFamily": "pod_unschedulable", "targetRef": {"kind": "Deployment", "name": "web"},
                 "parameters": {"node_selector_key": "never", "node_selector_value": "true"}},
    })
    assert result["status"] == "environment_blocked"
    assert "disposable" in result["errors"][0]


def test_dns_read_only_capability_is_inapplicable(tmp_path):
    executor = KubernetesLifecycleExecutor(
        root=tmp_path, namespace="lab", allowed_namespaces={"lab"}, allow_live=True,
        oracle={"service": "web", "remote_port": 80, "entrypoint": "/"},
        hooks={
            "gate": lambda _manifest, _path: {"decision": "ready_for_injection", "checks": {"target_pods": [{"name": "web-1"}]}},
            "dns_capability_probe": lambda _pods, _manifest: {"status": "inapplicable", "reason": "resolver is read-only"},
            "dns_fallback_builder": lambda _manifest, _capability: None,
            "probe": lambda phase, _manifest: {"status": "pass", "samples": [{"phase": phase}]},
        },
    )
    result = executor.run({
        "kind": "DNSChaos", "metadata": {"name": "dns-fault", "namespace": "lab"},
        "spec": {"action": "error", "selector": {"namespaces": ["lab"], "labelSelectors": {"app": "web"}}, "patterns": ["web"]},
    }, action_id="dns-read-only")
    assert result["status"] == "inapplicable"
    assert result["injection"]["confirmed"] is False
    assert result["attestation"]["valid"] is False


def test_dns_read_only_capability_can_use_network_fallback(tmp_path):
    applied = []

    def fallback(_manifest, _capability):
        return {
            "kind": "NetworkChaos",
            "metadata": {"name": "dns-network", "namespace": "lab"},
            "spec": {
                "selector": {"namespaces": ["lab"], "labelSelectors": {"app": "web"}},
                "action": "loss",
                "mode": "one",
                "direction": "to",
                "externalTargets": ["10.96.0.10"],
                "loss": {"loss": "100", "correlation": "100"},
                "duration": "30s",
            },
        }

    executor = KubernetesLifecycleExecutor(
        root=tmp_path, namespace="lab", allowed_namespaces={"lab"}, allow_live=True,
        oracle={"service": "web", "remote_port": 80, "entrypoint": "/dns-check"},
        hooks={
            "gate": lambda _manifest, _path: {"decision": "ready_for_injection", "checks": {"target_pods": [{"name": "web-1"}]}},
            "dns_capability_probe": lambda _pods, _manifest: {"status": "inapplicable", "reason": "resolver is read-only"},
            "dns_fallback_builder": fallback,
            "apply": lambda manifest: applied.append(manifest) or {"return_code": 0},
            "wait_lifecycle": lambda *_args: (True, {"records": []}, []),
            "probe": lambda phase, _manifest: {"status": "pass", "samples": [{"phase": phase}]},
            "delete": lambda *_args: {"absent_confirmed": True},
        },
    )
    result = executor.run({
        "kind": "DNSChaos", "metadata": {"name": "dns-fault", "namespace": "lab"},
        "spec": {"action": "error", "selector": {"namespaces": ["lab"], "labelSelectors": {"app": "web"}}, "patterns": ["web"]},
    }, action_id="dns-fallback")
    assert result["status"] == "executed"
    assert result["fallback"]["backend"] == "NetworkChaos"
    assert applied[0]["kind"] == "NetworkChaos"


def test_control_plane_delay_fails_closed_without_disposable_cluster():
    from tools.kubernetes_fault_executor import ControlPlaneDelayExecutor

    result = ControlPlaneDelayExecutor(allow_live=True, disposable_cluster=False)({
        "kind": "ChaosAtlasControlPlaneFault", "metadata": {"name": "api-delay", "namespace": "lab"},
        "spec": {"faultFamily": "api_server_delay", "parameters": {"latency_ms": 100}},
    })
    assert result["status"] == "environment_blocked"
