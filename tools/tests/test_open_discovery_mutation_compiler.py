from __future__ import annotations

import hashlib
import json

import yaml

from tools.open_discovery_mutation_compiler import compile_mutation, compile_payload


def topology() -> dict:
    return {
        "graph_hash": "g" * 64,
        "nodes": [
            {"id": "lab/deployment/api", "kind": "Deployment", "name": "api", "role": "workload", "pod_labels": {"app": "api"}},
            {"id": "lab/deployment/db", "kind": "Deployment", "name": "db", "role": "workload", "pod_labels": {"app": "db"}},
            {"id": "lab/service/api", "kind": "Service", "name": "api", "role": "routing", "labels": {"app": "api"}},
            {"id": "lab/configmap/settings", "kind": "ConfigMap", "name": "settings", "role": "configuration"},
        ],
        "edges": [
            {"source": "lab/service/api", "target": "lab/deployment/api", "kind": "selector_routes"},
            {"source": "lab/deployment/api", "target": "lab/deployment/db", "kind": "depends_on"},
        ],
    }


def intent(target: str = "lab/deployment/api", family: str = "network_delay", params: dict | None = None, target_kind: str = "service") -> dict:
    params = params or {"latency_ms": 200, "duration_s": 20}
    core = {"target": target, "target_kind": target_kind, "fault_family": family, "parameters": params}
    return {
        "project_id": "P02",
        "project_commit": "a" * 40,
        "namespace": "chaosatlas-p02",
        "hypothesis_id": "h1",
        "canonical_signature": hashlib.sha256(json.dumps(core, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        **core,
    }


def test_network_delay_yaml_resolves_workload_and_records_provenance() -> None:
    provenance, text = compile_mutation(intent(), topology())
    doc = yaml.safe_load(text)
    assert doc["kind"] == "NetworkChaos"
    assert doc["metadata"]["namespace"] == "chaosatlas-p02"
    assert doc["spec"]["selector"]["labelSelectors"] == {"app": "api"}
    assert doc["spec"]["delay"]["latency"] == "200ms"
    assert provenance["topology_graph_hash"] == "g" * 64
    assert provenance["resolved_source"]["selector_source"] == "topology.pod_labels"
    assert provenance["execution_ready"] is False


def test_network_loss_dependency_edge_targets_source_and_records_destination() -> None:
    edge = intent(
        target="lab/deployment/api->lab/deployment/db",
        target_kind="dependency_edge",
        family="network_loss",
        params={"loss_percent": 25, "duration_s": 10},
    )
    provenance, text = compile_mutation(edge, topology())
    doc = yaml.safe_load(text)
    assert doc["kind"] == "NetworkChaos"
    assert doc["spec"]["loss"]["loss"] == "25"
    assert doc["spec"]["selector"]["labelSelectors"] == {"app": "api"}
    assert provenance["resolved_destination"]["name"] == "db"


def test_pod_kill_and_cpu_stress_are_compiled() -> None:
    kill, kill_text = compile_mutation(intent(family="pod_kill", params={"mode": "one"}), topology())
    stress, stress_text = compile_mutation(intent(family="container_cpu_stress", params={"workers": 1, "load_percent": 60, "duration_s": 15}), topology())
    assert yaml.safe_load(kill_text)["kind"] == "PodChaos"
    assert yaml.safe_load(stress_text)["kind"] == "StressChaos"
    assert yaml.safe_load(stress_text)["spec"]["stressors"]["cpu"] == {"workers": 1, "load": 60}
    assert kill["canonical_signature"] != stress["canonical_signature"]


def test_configuration_target_is_rejected() -> None:
    result = compile_payload(intent(target="lab/configmap/settings"), topology())
    assert result["status"] == "method_invalid"
    assert "configuration targets" in result["rejected"][0]["reason"]


def test_missing_selector_is_rejected() -> None:
    topo = topology()
    topo["nodes"][0].pop("pod_labels")
    topo["nodes"][0]["labels"] = {}
    result = compile_payload(intent(), topo)
    assert result["status"] == "method_invalid"
    assert "no non-empty Pod selector" in result["rejected"][0]["reason"]


def test_runtime_mapping_must_stay_in_project_namespace() -> None:
    result = compile_payload(intent(target="compose/service/api"), topology(), {"targets": {"compose/service/api": {"namespace": "default", "name": "api", "selector": {"app": "api"}}}})
    assert result["status"] == "method_invalid"
    assert "namespace" in result["rejected"][0]["reason"]


def test_signature_mismatch_is_rejected() -> None:
    item = intent()
    item["parameters"] = {"latency_ms": 201, "duration_s": 20}
    result = compile_payload(item, topology())
    assert result["status"] == "method_invalid"
    assert "canonical signature" in result["rejected"][0]["reason"]


def test_pod_kill_edge_is_rejected() -> None:
    item = intent(
        target="lab/deployment/api->lab/deployment/db",
        target_kind="dependency_edge",
        family="pod_kill",
        params={"mode": "one"},
    )
    result = compile_payload(item, topology())
    assert result["status"] == "method_invalid"
    assert "only network faults" in result["rejected"][0]["reason"]


def test_invalid_upstream_compiler_status_cannot_be_promoted() -> None:
    result = compile_payload({"status": "method_invalid", "accepted": []}, topology())
    assert result["status"] == "method_invalid"
    assert result["rejected"][0]["reason"] == "upstream_compiler_not_valid"


def test_extra_parameter_is_rejected_even_without_upstream_compiler() -> None:
    item = intent()
    item["parameters"] = {"latency_ms": 200, "duration_s": 20, "jitter_ms": 1}
    core = {"target": item["target"], "target_kind": item["target_kind"], "fault_family": item["fault_family"], "parameters": item["parameters"]}
    item["canonical_signature"] = hashlib.sha256(json.dumps(core, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    result = compile_payload(item, topology())
    assert result["status"] == "method_invalid"
    assert "exactly" in result["rejected"][0]["reason"]
