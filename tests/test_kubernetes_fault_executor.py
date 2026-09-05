import json

from tools.kubernetes_fault_executor import KubernetesApiFaultExecutor, build_mutation


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
