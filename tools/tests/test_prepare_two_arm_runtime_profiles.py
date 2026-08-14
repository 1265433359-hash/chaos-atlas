from __future__ import annotations

from tools.prepare_two_arm_runtime_profiles import evaluate_runtime_profile


def base_manifest() -> dict:
    return {
        "project_id": "online-boutique",
        "namespace": "chaosatlas-online-boutique",
        "static_gate": {"status": "passed", "blocked_reasons": []},
        "image_provenance": {"all_immutable": True},
        "oracle_contract": {"workflow": "health_then_place_order", "success": "HTTP 200 and order_id"},
    }


def test_runtime_ready_requires_every_cluster_lifecycle_gate() -> None:
    facts = {
        "server_side_dry_run": "passed",
        "baseline_windows": {"passed": 2},
        "recovery_rehearsal": "passed",
        "cleanup": "passed",
        "global_residual_scan": "clear",
        "washout": {"stable": True},
    }
    profile = evaluate_runtime_profile(base_manifest(), facts)
    assert profile["runtime_ready"] is True
    assert profile["status"] == "runtime_ready"


def test_runtime_profile_fails_closed_for_missing_immutable_provenance() -> None:
    manifest = base_manifest()
    manifest["image_provenance"] = {"all_immutable": False}
    profile = evaluate_runtime_profile(manifest, {})
    assert profile["runtime_ready"] is False
    assert "immutable_image_provenance_missing" in profile["blocked_reasons"]


def test_runtime_profile_rejects_wrong_namespace() -> None:
    manifest = base_manifest()
    manifest["namespace"] = "chaosatlas-otel"
    profile = evaluate_runtime_profile(manifest, {})
    assert profile["runtime_ready"] is False
    assert "namespace_not_allowed_for_project" in profile["blocked_reasons"]


def test_sock_shop_cluster_facts_require_healthy_deployments_two_baselines_and_rehearsal() -> None:
    from tools.prepare_two_arm_runtime_profiles import sock_shop_cluster_facts

    health = {
        "context": "minikube",
        "node_ready": True,
        "namespace": "chaosatlas-sock-shop",
        "deployments_available": 13,
        "deployments_total": 13,
        "server_side_dry_run": "passed",
    }
    baseline_windows = [
        [{"pass": True} for _ in range(5)],
        [{"pass": True} for _ in range(5)],
    ]
    rehearsal = {
        "status": "completed",
        "recovery": {"recovered": True},
        "cleanup": {"absent_confirmed": True, "residual_resources": [], "global_scan_errors": []},
        "washout": {"stable": True, "journeys": [{"pass": True} for _ in range(10)]},
    }

    facts = sock_shop_cluster_facts(health, baseline_windows, rehearsal)

    assert facts["baseline_windows"] == {"passed": 2, "successes": [5, 5]}
    assert facts["recovery_rehearsal"] == "passed"
    assert facts["cleanup"] == "passed"
    assert facts["global_residual_scan"] == "clear"
    assert facts["washout"] == {"stable": True, "successes": 10}


def test_sock_shop_cluster_facts_fail_closed_for_residual_or_incomplete_rehearsal() -> None:
    from tools.prepare_two_arm_runtime_profiles import sock_shop_cluster_facts

    health = {
        "context": "minikube",
        "node_ready": True,
        "namespace": "chaosatlas-sock-shop",
        "deployments_available": 12,
        "deployments_total": 13,
        "server_side_dry_run": "passed",
    }
    rehearsal = {
        "status": "failed",
        "recovery": {"recovered": False},
        "cleanup": {
            "absent_confirmed": True,
            "residual_resources": [{"namespace": "chaosatlas-sock-shop", "name": "leftover"}],
            "global_scan_errors": [],
        },
        "washout": {"stable": False, "journeys": []},
    }

    facts = sock_shop_cluster_facts(health, [[{"pass": True}], [{"pass": False}]], rehearsal)

    assert facts["deployments_healthy"] is False
    assert facts["baseline_windows"]["passed"] == 1
    assert facts["recovery_rehearsal"] == "failed"
    assert facts["global_residual_scan"] == "blocked"
