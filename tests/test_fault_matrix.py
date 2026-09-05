import json
from pathlib import Path

from tools.fault_matrix import build_fault_matrix


def test_matrix_contains_all_catalog_ids_and_project_statuses():
    profile = json.loads(Path("projects/nginx-kubernetes-ingress/profile.json").read_text(encoding="utf-8"))

    matrix = build_fault_matrix(profile)

    assert matrix["project_id"] == "nginx-kubernetes-ingress"
    assert len(matrix["faults"]) == 32
    assert {item["status"] for item in matrix["faults"]} <= {
        "supported",
        "planned",
        "inapplicable",
        "blocked_by_platform_prerequisite",
        "not_reachable",
        "unsupported",
    }
    assert any(item["fault_id"] == "network_delay" and item["status"] == "supported" for item in matrix["faults"])
    assert matrix["status_counts"]["supported"] > 0


def test_matrix_explains_why_undeclared_implemented_faults_are_not_candidates():
    profile = {"project_id": "fixture", "runtime_contract": {"supported_fault_families": ["pod_kill"]}}

    matrix = build_fault_matrix(profile)
    config = next(item for item in matrix["faults"] if item["fault_id"] == "config_reload")

    assert config["status"] == "inapplicable"
    assert config["reason"]
    assert config["execution_eligible"] is False


def test_matrix_preserves_platform_and_reachability_boundaries():
    matrix = build_fault_matrix({
        "project_id": "fixture",
        "fault_support": {
            "http_delay": {"status": "blocked_by_platform_prerequisite", "reason": "kernel prerequisite"},
            "http_rate_limit": {"status": "not_reachable", "reason": "no native contract"},
        },
    })

    by_id = {item["fault_id"]: item for item in matrix["faults"]}
    assert by_id["http_delay"]["status"] == "blocked_by_platform_prerequisite"
    assert by_id["http_rate_limit"]["status"] == "not_reachable"
    assert matrix["status_counts"]["blocked_by_platform_prerequisite"] == 1
    assert matrix["status_counts"]["not_reachable"] == 1
