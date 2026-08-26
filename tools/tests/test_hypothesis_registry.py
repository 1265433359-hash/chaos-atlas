from __future__ import annotations

from tools.hypothesis_registry import build_hypothesis_registry, build_project_portrait


INVENTORY = {
    "project_id": "nginx-kubernetes-ingress",
    "project_commit": "f92a24e4fd2b52c72739c4a1f4f9bb6424bf5731",
    "namespace": "chaosatlas-nginx-ingress",
    "services": ["nginx-ingress", "fixture-backend"],
    "deployments": [
        {"name": "nginx-ingress", "selector": {"app": "nginx-ingress"}, "desired_replicas": 1},
        {"name": "fixture-backend", "selector": {"app": "fixture-backend"}, "desired_replicas": 1},
    ],
    "dependencies": [{"source": "nginx-ingress", "target": "fixture-backend", "relation": "http"}],
    "business_oracles": [{"id": "route", "kind": "http", "entrypoint": "/", "success_contract": "http_200"}],
}
DETECTION = {
    "status": "verified",
    "deployment_nodes": [
        {
            "node_id": "deployment:nginx-ingress",
            "deployment": {
                "name": "nginx-ingress",
                "desired_replicas": 1,
                "containers": ["nginx-ingress"],
                "resources": {"requests": {"cpu": "100m"}, "limits": {}},
            },
            "availability_profile": {"pdb": None, "readiness_probe": {"httpGet": {"path": "/ready"}}},
            "service": {"name": "nginx-ingress"},
        },
        {
            "node_id": "deployment:fixture-backend",
            "deployment": {
                "name": "fixture-backend",
                "desired_replicas": 1,
                "containers": ["http-echo"],
                "resources": {"requests": {}, "limits": {}},
            },
            "availability_profile": {"pdb": None, "readiness_probe": {}},
            "service": {"name": "fixture-backend"},
        },
    ],
}
CANDIDATE_SPACE = {
    "status": "verified",
    "candidates": [
        {"candidate_id": "server:nginx-ingress:pod_kill", "target": "nginx-ingress", "target_kind": "deployment", "fault_family": "pod_kill"},
        {"candidate_id": "server:nginx-ingress:network_loss", "target": "nginx-ingress", "target_kind": "deployment", "fault_family": "network_loss"},
    ],
}
ADVISORY = {
    "hypotheses": [
        {"candidate_id": "server:nginx-ingress:pod_kill", "mechanism": "controller replacement may interrupt the only endpoint", "expected_observations": ["route failure"], "missing_evidence": ["business probe"], "next_actions": ["run pod kill"]},
        {"candidate_id": "server:nginx-ingress:network_loss", "mechanism": "controller-to-backend loss may delay the route", "expected_observations": ["request timeout"], "missing_evidence": ["network evidence"], "next_actions": ["run network loss"]},
    ]
}


def test_registry_contains_all_five_hypothesis_categories() -> None:
    portrait = build_project_portrait(INVENTORY, DETECTION, CANDIDATE_SPACE, cards=[])
    registry = build_hypothesis_registry(INVENTORY, DETECTION, CANDIDATE_SPACE, advisory=ADVISORY, cards=[])

    assert portrait["schema_version"] == "chaosatlas-project-portrait-v1"
    assert portrait["deployment_count"] == 2
    assert {item["kind"] for item in registry["hypotheses"]} == {
        "architecture", "configuration", "dependency", "runtime", "defense"
    }
    assert registry["counts"]["runtime"] == 2
    assert registry["execution_eligible_count"] == 2


def test_registry_marks_unknown_pdb_as_evidence_required_not_absent() -> None:
    registry = build_hypothesis_registry(INVENTORY, DETECTION, CANDIDATE_SPACE, advisory=ADVISORY, cards=[])

    pdb = next(item for item in registry["hypotheses"] if item["mechanism"] == "pdb_coverage_needs_verification")

    assert pdb["execution_eligible"] is False
    assert "pdb" in pdb["required_evidence"]
    assert "weakness_status" not in pdb
    assert "runtime_verdict" not in pdb


def test_registry_is_stable_and_deduplicated() -> None:
    first = build_hypothesis_registry(INVENTORY, DETECTION, CANDIDATE_SPACE, advisory=ADVISORY, cards=[])
    second = build_hypothesis_registry(INVENTORY, DETECTION, CANDIDATE_SPACE, advisory=ADVISORY, cards=[])

    assert first == second
    ids = [item["hypothesis_id"] for item in first["hypotheses"]]
    assert len(ids) == len(set(ids))
    assert first["hypothesis_count"] == len(ids)
