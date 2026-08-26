from __future__ import annotations

from tools.candidate_coverage_denominator import build_candidate_space, build_coverage_denominator


def _bundle() -> dict:
    return {
        "project_id": "demo",
        "project_commit": "a" * 40,
        "namespace": "chaosatlas-demo",
        "business_oracle": {"workflow": "GET /", "success": "HTTP 200"},
        "topology": {
            "nodes": [
                {"id": "service/api", "role": "workload", "selector_resolved": True},
                {"id": "service/db", "role": "workload", "selector_resolved": True},
            ],
            "edges": [{"source": "service/api", "target": "service/db", "relation": "http"}],
        },
        "deployment_capability_pool": {
            "status": "verified",
            "deployment_nodes": [
                {"node_id": "deployment:api", "deployment": {"selector": {"matchLabels": {"app": "api"}}, "desired_replicas": 2}, "availability_profile": {"manifest_facts_status": "verified", "recovery_contract": {"ready_required": True}}},
                {"node_id": "deployment:db", "deployment": {"selector": {"matchLabels": {"app": "db"}}, "desired_replicas": 1}, "availability_profile": {"manifest_facts_status": "verified", "recovery_contract": {"ready_required": True}}},
            ],
            "candidates": [
                {"target": "deployment:api", "target_kind": "deployment", "compile_eligible": True, "fault_families": ["pod_kill"]},
                {"target": "deployment:db", "target_kind": "deployment", "compile_eligible": True, "fault_families": ["pod_kill"]},
            ],
        },
    }


def test_build_candidate_space_contains_edge_deployment_and_scenario_without_runtime_verdicts():
    candidates = build_candidate_space(_bundle())
    assert {item["target_kind"] for item in candidates} == {"dependency_edge", "deployment", "scenario"}
    assert all("runtime_verdict" not in item and "runtime_observation" not in item for item in candidates)
    assert all(item["validation_plan"] for item in candidates)
    assert all(item["causal_cluster_id"].startswith("sha256:") for item in candidates)
    assert all(item["causal_identity"]["fault_family"] for item in candidates)


def test_unresolved_selector_and_missing_business_oracle_are_blocked():
    bundle = _bundle()
    bundle["topology"]["nodes"][0]["selector_resolved"] = False
    bundle["business_oracle"] = {}
    candidates = build_candidate_space(bundle)
    assert candidates
    assert all(item["status"] == "blocked" for item in candidates)
    assert any("selector" in reason for item in candidates for reason in item["blocked_reasons"])
    assert any("business" in reason for item in candidates for reason in item["blocked_reasons"])


def test_coverage_denominator_is_static_inventory_not_discovery_evidence():
    result = build_coverage_denominator(_bundle(), seed=1001, snapshot_sha256="b" * 64)
    assert result["schema_version"] == "chaosatlas-coverage-denominator-v1"
    assert result["candidate_count"] == len(result["candidates"])
    assert result["evidence_status"] == "static_only"
    assert result["runtime_results"] == []


def test_missing_recovery_contract_blocks_deployment_candidate():
    bundle = _bundle()
    bundle["deployment_capability_pool"]["deployment_nodes"][0]["availability_profile"].pop("recovery_contract")
    candidates = build_candidate_space(bundle)
    item = next(candidate for candidate in candidates if candidate["candidate_id"] == "deployment:api")
    assert item["status"] == "blocked"
    assert any("recovery contract" in reason for reason in item["blocked_reasons"])


def test_runtime_fields_on_deployment_node_are_not_copied_to_candidate_space():
    bundle = _bundle()
    bundle["deployment_capability_pool"]["deployment_nodes"][0]["runtime_observation"] = {"availableReplicas": 0}
    candidates = build_candidate_space(bundle)
    deployment = next(candidate for candidate in candidates if candidate["candidate_id"] == "deployment:api")
    assert "runtime_observation" not in deployment.get("deployment_node", {})


def test_service_candidates_are_materialized_when_service_and_workload_nodes_pair():
    bundle = _bundle()
    bundle["topology"]["nodes"].extend([
        {"id": "service/catalog", "role": "routing", "selector_resolved": True},
        {"id": "workload/catalog", "role": "workload", "selector_resolved": True},
    ])
    candidates = build_candidate_space(bundle)
    item = next(candidate for candidate in candidates if candidate["target"] == "workload/catalog")
    assert item["target_kind"] == "service"
    assert item["fault_family"] == "network_loss"
    assert item["status"] == "eligible"
