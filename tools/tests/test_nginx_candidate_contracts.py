from __future__ import annotations

from tools.nginx_candidate_contracts import build_catalog, validate_catalog
from tools.kubernetes_project_adapter import FAULT_FAMILIES


def test_nginx_catalog_freezes_all_declared_families_and_execution_boundary():
    catalog = build_catalog(
        project_id="nginx-kubernetes-ingress",
        project_commit="f92a24e4fd2b52c72739c4a1f4f9bb6424bf5731",
    )

    assert validate_catalog(catalog) == []
    assert catalog["schema_version"] == "chaosatlas-nginx-candidate-contracts-v1"
    assert {item["family"] for item in catalog["contracts"]} == {
        "pod_kill",
        "container_kill",
        "stress_cpu",
        "stress_memory",
        "network_loss",
        "network_partition",
        "network_delay",
        "backend_pod_kill",
        "config_reload",
        "replica_reduction",
    }
    ready = {item["family"] for item in catalog["contracts"] if item["execution_eligible"]}
    assert ready == {"pod_kill", "container_kill", "stress_cpu", "stress_memory", "network_loss", "network_partition"}
    assert set(FAULT_FAMILIES) == ready
    pending = [item for item in catalog["contracts"] if not item["execution_eligible"]]
    assert {item["family"] for item in pending} == {"network_delay", "backend_pod_kill", "config_reload", "replica_reduction"}
    assert all(item["status"] == "pending_method_freeze" for item in pending)


def test_nginx_catalog_requires_evidence_and_rejects_pending_execution():
    catalog = build_catalog(project_id="nginx-kubernetes-ingress", project_commit="fixture")
    invalid = {**catalog, "contracts": [dict(item) for item in catalog["contracts"]]}
    invalid["contracts"][0]["required_evidence"] = []
    invalid["contracts"][-1]["execution_eligible"] = True

    errors = validate_catalog(invalid)

    assert any("required_evidence" in error for error in errors)
    assert any("pending_method_freeze" in error for error in errors)
