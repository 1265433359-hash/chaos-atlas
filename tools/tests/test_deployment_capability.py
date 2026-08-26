from __future__ import annotations

import copy

import pytest

from tools.deployment_capability import (
    build_deployment_node,
    build_scenario_node,
    deployment_signature,
    scenario_signature,
    validate_deployment_node,
    validate_scenario_node,
)


def deployment():
    return {
        "metadata": {"name": "front-end"},
        "spec": {
            "replicas": 2,
            "selector": {"matchLabels": {"name": "front-end"}},
            "template": {
                "metadata": {"labels": {"name": "front-end"}},
                "spec": {
                    "containers": [{"name": "front-end", "resources": {"requests": {"cpu": "10m"}}}],
                },
            },
        },
    }


def test_deployment_node_is_valid_and_signature_is_stable():
    node = build_deployment_node(
        project_id="sock-shop",
        project_commit="a" * 40,
        namespace="sock-shop",
        deployment=deployment(),
        service={"metadata": {"name": "front-end"}, "spec": {"ports": [{"port": 80, "targetPort": 8079}]}},
        source_refs=["manifests/front-end.yaml"],
        manifest_sha256="b" * 64,
    )
    assert validate_deployment_node(node) == []
    assert deployment_signature(node) == deployment_signature(copy.deepcopy(node))
    assert node["node_type"] == "deployment_node"
    assert node["deployment"]["desired_replicas"] == 2


@pytest.mark.parametrize(
    "change",
    [
        {"namespace": ""},
        {"project_commit": "not-a-commit"},
        {"deployment": {"spec": {"replicas": 1}}},
        {"manifest_sha256": "bad"},
        {"source_refs": ["C:/secret.yaml"]},
        {"source_refs": ["../secret.yaml"]},
    ],
)
def test_deployment_node_fails_closed(change):
    args = dict(
        project_id="p",
        project_commit="a" * 40,
        namespace="ns",
        deployment=deployment(),
        service=None,
        source_refs=["manifest.yaml"],
        manifest_sha256="b" * 64,
    )
    args.update(change)
    if "deployment" in change:
        node = build_deployment_node(**args)
    else:
        node = build_deployment_node(**args)
    assert validate_deployment_node(node)


def scenario():
    node = build_deployment_node(
        project_id="p", project_commit="a" * 40, namespace="ns", deployment=deployment(),
        service=None, source_refs=["manifest.yaml"], manifest_sha256="b" * 64,
    )
    return build_scenario_node(
        scenario_id="s1",
        deployment_nodes=[node],
        phases=[{
            "phase_id": "kill",
            "mode": "ordered",
            "faults": [{"kind": "pod_kill", "action": "pod-kill", "selector": {"name": "front-end"}, "parameters": {"mode": "one"}, "target_node_id": node["node_id"]}],
            "duration_s": 30,
            "target_node_ids": [node["node_id"]],
            "inject_confirmation": "status.injectedCount >= 1",
            "cleanup_owner": "phase",
        }],
        oracle={"ce_steady_state": {"metric": "deployment.availableReplicas", "minimum_available": 1}},
        recovery={"deadline_s": 120, "stable_samples": 3},
        cleanup={"required": True},
    )


def test_scenario_node_is_valid_and_hash_ignores_key_order():
    value = scenario()
    assert validate_scenario_node(value) == []
    shuffled = {"cleanup": value["cleanup"], "phases": value["phases"], "scenario_id": value["scenario_id"], "recovery": value["recovery"], "oracle": value["oracle"], "deployment_nodes": value["deployment_nodes"], "node_type": value["node_type"], "schema_version": value["schema_version"]}
    assert scenario_signature(value) == scenario_signature(shuffled)


def test_scenario_rejects_invalid_phase():
    value = scenario()
    value["phases"][0]["mode"] = "bad"
    assert any("mode" in error for error in validate_scenario_node(value))

