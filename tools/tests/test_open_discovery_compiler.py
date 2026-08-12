from __future__ import annotations

from tools.open_discovery_compiler import RuntimeContract, compile_output, contract_from_topology


def contract() -> RuntimeContract:
    return RuntimeContract(
        project_id="P02",
        project_commit="a" * 40,
        namespace="chaosatlas-p02",
        targets=frozenset({"api-gateway", "customers-service", "api-gateway->customers-service"}),
        workload_id="P02-primary-workload",
        workload_contract="gateway health plus CRUD request",
    )


def hypothesis(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "hypothesis_id": "h1",
        "target": "api-gateway",
        "target_kind": "service",
        "fault_family": "network_delay",
        "parameters": {"latency_ms": 200, "duration_s": 20},
        "hypothesis": "gateway may propagate downstream delay without a deadline",
        "weakness_surface": "gateway to customer dependency edge",
        "call_chain": [{"source": "api-gateway", "target": "customers-service", "relation": "http dependency", "evidence_ref": "topology edge"}],
        "expected_invariant": "the CRUD request completes within the workload deadline",
        "validation_plan": "baseline, inject once, observe the CRUD oracle, recover, and clean up",
        "recovery_expectation": "the gateway returns to baseline after removal",
    }
    value.update(overrides)
    return value


def test_accepts_open_hypothesis_without_candidate_pool() -> None:
    result = compile_output({"project_id": "P02", "project_commit": "a" * 40, "hypotheses": [hypothesis()]}, contract())
    assert result["status"] == "valid"
    assert result["accepted_count"] == 1
    assert result["accepted"][0]["novelty"] == "novel_candidate"
    assert result["accepted"][0]["execution_ready"] is False


def test_marks_known_signature_only_after_compilation() -> None:
    item = hypothesis()
    import hashlib
    import json

    signature = hashlib.sha256(json.dumps({"target": item["target"], "target_kind": item["target_kind"], "fault_family": item["fault_family"], "parameters": item["parameters"]}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    result = compile_output({"project_id": "P02", "project_commit": "a" * 40, "hypotheses": [item]}, contract(), {signature})
    assert result["accepted"][0]["status"] == "accepted_known_candidate"


def test_rejects_unknown_target_and_unsafe_parameters() -> None:
    result = compile_output(
        {"project_id": "P02", "project_commit": "a" * 40, "hypotheses": [hypothesis(target="does-not-exist", parameters={"latency_ms": 5000, "duration_s": 20})]},
        contract(),
    )
    assert result["status"] == "method_invalid"
    assert result["accepted_count"] == 0
    assert {item["reason"] for item in result["rejected"]} == {"target_not_in_deployment"}


def test_rejects_forbidden_candidate_pool_field() -> None:
    result = compile_output({"project_id": "P02", "project_commit": "a" * 40, "candidate_pool": [], "hypotheses": []}, contract())
    assert result["status"] == "method_invalid"
    assert result["rejected"][0]["reason"] == "forbidden_field"


def test_empty_output_requires_reason() -> None:
    result = compile_output({"project_id": "P02", "project_commit": "a" * 40, "hypotheses": []}, contract())
    assert result["status"] == "method_invalid"
    result = compile_output({"project_id": "P02", "project_commit": "a" * 40, "hypotheses": [], "no_safe_hypothesis_reason": "deployment evidence is insufficient"}, contract())
    assert result["status"] == "valid"


def test_call_chain_is_required() -> None:
    item = hypothesis()
    item.pop("call_chain")
    result = compile_output({"project_id": "P02", "project_commit": "a" * 40, "hypotheses": [item]}, contract())
    assert result["rejected"][0]["reason"] == "call_chain_required"


def test_topology_contract_resolves_nodes_and_edges_without_execution() -> None:
    topology = {
        "nodes": [{"id": "compose/service/api", "name": "api", "kind": "ComposeService", "role": "workload"}, {"id": "compose/service/db", "name": "db", "kind": "ComposeService", "role": "workload"}, {"id": "compose/configmap/config", "name": "config", "kind": "ConfigMap", "role": "configuration"}],
        "edges": [{"source": "compose/service/api", "target": "compose/service/db", "kind": "depends_on"}],
    }
    runtime = contract_from_topology("P02", "a" * 40, "chaosatlas-p02", "w", "health", topology)
    item = hypothesis(target="compose/service/api", call_chain=[{"source": "compose/service/api", "target": "compose/service/db", "relation": "depends_on", "evidence_ref": "services.depends_on"}])
    result = compile_output({"project_id": "P02", "project_commit": "a" * 40, "hypotheses": [item]}, runtime)
    assert result["accepted"][0]["resolved_target"] == "chaosatlas-p02/composeservice/api"
    assert result["accepted"][0]["resolver_status"] == "static_only"
    edge = hypothesis(target="compose/service/api->compose/service/db", target_kind="dependency_edge", call_chain=[{"source": "compose/service/api", "target": "compose/service/db", "relation": "depends_on", "evidence_ref": "services.depends_on"}])
    edge_result = compile_output({"project_id": "P02", "project_commit": "a" * 40, "hypotheses": [edge]}, runtime)
    assert edge_result["accepted"][0]["target_kind"] == "dependency_edge"


def test_topology_contract_excludes_configuration_targets() -> None:
    topology = {"nodes": [{"id": "default/deployment/api", "name": "api", "kind": "Deployment", "role": "workload"}, {"id": "default/configmap/config", "name": "config", "kind": "ConfigMap", "role": "configuration"}], "edges": [{"source": "default/deployment/api", "target": "default/configmap/config", "kind": "configuration_ref"}]}
    runtime = contract_from_topology("P02", "a" * 40, "chaosatlas-p02", "w", "health", topology)
    assert "default/configmap/config" not in runtime.targets
    assert not any("configmap/config" in target for target in runtime.targets)
