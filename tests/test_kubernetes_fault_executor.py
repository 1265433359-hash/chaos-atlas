import json

from tools.kubernetes_fault_executor import KubernetesApiFaultExecutor, build_mutation
from tools.compile_scenario_node import compile_scenario
from tools.deployment_capability import build_deployment_node, build_scenario_node
from tools.run_deployment_scenario import run_scenario


def _deployment(replicas=3):
    return {
        "metadata": {"name": "web", "namespace": "lab"},
        "spec": {
            "replicas": replicas,
            "template": {"metadata": {"annotations": {"existing": "keep"}}},
        },
    }


def test_replica_reduction_builds_reversible_patch_and_snapshot():
    mutation = build_mutation("replica_reduction", _deployment(), {"replicas": 1})

    assert mutation["fault_family"] == "replica_reduction"
    assert mutation["snapshot"]["spec"]["replicas"] == 3
    assert mutation["patch"] == {"spec": {"replicas": 1}}
    assert mutation["restore_patch"] == {"spec": {"replicas": 3}}


def test_config_reload_changes_only_reload_annotation_and_restores_it():
    mutation = build_mutation("config_reload", _deployment(), {"reload_token": "r1"})

    annotations = mutation["patch"]["spec"]["template"]["metadata"]["annotations"]
    restore = mutation["restore_patch"]["spec"]["template"]["metadata"]["annotations"]
    assert annotations["chaosatlas.dev/reload-token"] == "r1"
    assert restore == {"existing": "keep", "chaosatlas.dev/reload-token": None}


def test_config_drift_rejects_empty_drift_value():
    try:
        build_mutation("config_drift", _deployment(), {"value": ""})
    except ValueError as exc:
        assert "drift value" in str(exc)
    else:
        raise AssertionError("empty config drift value must fail closed")


def test_executor_restores_config_annotations_and_accepts_confirmed_outage_as_evidence():
    state = _deployment()

    def runner(args, timeout=30, kube_context=None):
        if args[0] == "get":
            return 0, json.dumps(state), ""
        if args[0] == "patch":
            patch = json.loads(args[-1])
            state["spec"].update(patch.get("spec") or {})
            if "template" in (patch.get("spec") or {}):
                metadata = patch["spec"]["template"].get("metadata") or {}
                annotations = dict(state["spec"]["template"]["metadata"].get("annotations") or {})
                for key, value in (metadata.get("annotations") or {}).items():
                    if value is None:
                        annotations.pop(key, None)
                    else:
                        annotations[key] = value
                state["spec"]["template"]["metadata"]["annotations"] = annotations
            return 0, "patched", ""
        raise AssertionError(args)

    observations = {
        "baseline": {"status": "pass", "samples": [{"status_code": 200}]},
        "observe": {"status": "business_unreachable", "samples": [{"status_code": None}]},
        "recovery": {"status": "pass", "samples": [{"status_code": 200}]},
    }
    executor = KubernetesApiFaultExecutor(
        namespace="lab",
        allowed_namespaces={"lab"},
        allow_live=True,
        runner=runner,
        probe=lambda phase: observations[phase],
    )
    result = executor({
        "apiVersion": "chaosatlas.dev/v1alpha1",
        "kind": "ChaosAtlasKubernetesFault",
        "metadata": {"name": "api-fault", "namespace": "lab"},
        "spec": {
            "faultFamily": "config_drift",
            "targetRef": {"kind": "Deployment", "name": "web"},
            "parameters": {"value": "drift"},
        },
    })

    assert result["injected_count"] == 1
    assert result["recovery"]["annotations_match"] is True
    assert result["attestation"]["valid"] is True
    assert result["attestation"]["comparison_eligible"] is True


def test_image_pull_failure_requires_observed_waiting_reason_and_restores():
    state = {
        "kind": "Deployment",
        "metadata": {"name": "web", "namespace": "ca-l2-lab-1234"},
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": {"app": "web"}},
            "template": {
                "metadata": {"labels": {"app": "web"}},
                "spec": {"containers": [{"name": "web", "image": "web:v1"}]},
            },
        },
    }
    patches = []

    def runner(args, timeout=30, kube_context=None):
        if args[:2] == ["get", "deployment"]:
            return 0, json.dumps(state), ""
        if args[:2] == ["get", "pods"]:
            return 0, json.dumps({"items": [{
                "spec": {"containers": [{"name": "web", "image": "web:v1"}]},
                "status": {"containerStatuses": [{"name": "web", "state": {"running": {}}}]},
            }]}), ""
        if args[0] == "patch":
            patch = json.loads(args[-1])
            patches.append(patch)
            state["spec"]["template"]["spec"]["containers"] = patch["spec"]["template"]["spec"]["containers"]
            return 0, "patched", ""
        raise AssertionError(args)

    executor = KubernetesApiFaultExecutor(
        namespace="ca-l2-lab-1234",
        allowed_namespaces={"ca-l2-lab-1234"},
        allow_live=True,
        isolated=True,
        runner=runner,
        probe=lambda phase: {"status": "pass", "samples": [{"phase": phase}]},
        injection_timeout=0,
        poll_interval=0,
    )
    result = executor({
        "kind": "ChaosAtlasKubernetesFault",
        "metadata": {"name": "image-fault", "namespace": "ca-l2-lab-1234"},
        "spec": {
            "faultFamily": "image_pull_failure",
            "targetRef": {"kind": "Deployment", "name": "web"},
            "parameters": {"image": "chaosatlas.invalid/not-found:test"},
        },
    })

    assert result["status"] == "injection_not_confirmed"
    assert result["injection"]["applied"] is True
    assert result["injection"]["confirmed"] is False
    assert result["attestation"]["valid"] is False
    assert len(patches) == 2
    assert state["spec"]["template"]["spec"]["containers"][0]["image"] == "web:v1"


def test_high_risk_fault_confirmation_requires_runtime_pod_state():
    snapshot = {
        "kind": "Deployment",
        "metadata": {"name": "web", "namespace": "ca-l2-lab-1234"},
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": {"app": "web"}},
            "template": {
                "metadata": {"labels": {"app": "web"}},
                "spec": {"containers": [{"name": "web", "image": "web:v1"}]},
            },
        },
    }
    current = json.loads(json.dumps(snapshot))
    pods = {"items": []}

    def runner(args, timeout=30, kube_context=None):
        if args[:2] == ["get", "deployment"]:
            return 0, json.dumps(current), ""
        if args[:2] == ["get", "pods"]:
            return 0, json.dumps(pods), ""
        raise AssertionError(args)

    executor = KubernetesApiFaultExecutor(
        namespace="ca-l2-lab-1234",
        allowed_namespaces={"ca-l2-lab-1234"},
        allow_live=True,
        isolated=True,
        runner=runner,
        probe=lambda phase: {"status": "pass", "samples": [{"phase": phase}]},
        injection_timeout=0,
        poll_interval=0,
    )

    image = build_mutation("image_pull_failure", snapshot, {"image": "chaosatlas.invalid/not-found:test"})
    current["spec"]["template"]["spec"]["containers"] = image["patch"]["spec"]["template"]["spec"]["containers"]
    pods["items"] = [{
        "spec": {"containers": [{"name": "web", "image": "chaosatlas.invalid/not-found:test"}]},
        "status": {"containerStatuses": [{"name": "web", "state": {"waiting": {"reason": "ImagePullBackOff"}}}]},
    }]
    image_result = executor._confirm_injection("image_pull_failure", "Deployment", "web", snapshot, image)
    assert image_result["confirmed"] is True
    assert image_result["mechanism"] == "pod_image_pull_waiting"

    unschedulable = build_mutation("pod_unschedulable", snapshot, {"node_selector_key": "chaosatlas.invalid/never", "node_selector_value": "true"})
    current["spec"]["template"]["spec"]["nodeSelector"] = {"chaosatlas.invalid/never": "true"}
    pods["items"] = [{
        "spec": {"nodeSelector": {"chaosatlas.invalid/never": "true"}},
        "status": {"conditions": [{"type": "PodScheduled", "status": "False", "reason": "Unschedulable"}]},
    }]
    scheduling_result = executor._confirm_injection("pod_unschedulable", "Deployment", "web", snapshot, unschedulable)
    assert scheduling_result["confirmed"] is True
    assert scheduling_result["mechanism"] == "pod_scheduling_condition"


def test_scenario_projection_preserves_injection_confirmation():
    node = build_deployment_node(
        project_id="fixture",
        project_commit="0" * 40,
        namespace="lab",
        deployment={"metadata": {"name": "web"}, "spec": {"replicas": 1, "selector": {"matchLabels": {"app": "web"}}, "template": {"metadata": {"labels": {"app": "web"}}, "spec": {"containers": [{"name": "web", "image": "web:v1"}]}}}},
        service={"metadata": {"name": "web"}, "spec": {"ports": [{"port": 80}], "selector": {"app": "web"}}},
        source_refs=["test"],
        manifest_sha256="0" * 64,
    )
    scenario = build_scenario_node(
        scenario_id="projection",
        deployment_nodes=[node],
        phases=[{"phase_id": "p1", "mode": "ordered", "duration_s": 1, "target_node_ids": [node["node_id"]], "inject_confirmation": "status.injectedCount >= 1", "cleanup_owner": "chaosatlas", "faults": [{"kind": "config_drift", "action": "config-drift", "selector": {"app": "web"}, "parameters": {"value": "test"}, "target_node_id": node["node_id"]}]}],
        oracle={"business": {"kind": "http", "service": "web", "remote_port": 80}},
        recovery={"deadline_s": 60},
        cleanup={"required": True, "owner": "chaosatlas"},
    )
    compiled = compile_scenario(scenario)
    response = {
        "status": "executed", "injected_count": 1, "injection_confirmed": True,
        "injection": {"confirmation": {"confirmed": True, "mechanism": "api_state_reflected"}},
        "cleanup_confirmed": True, "verdict": "pass",
    }

    result = run_scenario(scenario, compiled=compiled, dry_run=False, executor=lambda *_args: response)

    assert result["phases"][0]["faults"][0]["injection_confirmation"] == response["injection"]["confirmation"]
