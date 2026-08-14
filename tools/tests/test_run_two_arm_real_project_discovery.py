from __future__ import annotations

import pytest

from tools.run_two_arm_real_project_discovery import build_discovery_handoff


def bundle() -> dict:
    return {
        "project_id": "demo",
        "method_id": "ChaosAtlas-full",
        "seed": 1001,
        "common_input": {
            "project_id": "demo",
            "project_commit": "a" * 40,
            "namespace": "chaosatlas-demo",
            "topology": {
                "nodes": [
                    {"id": "workload/api", "role": "workload", "kind": "Deployment", "name": "api", "pod_labels": {"app": "api"}},
                    {"id": "service/api", "role": "routing", "kind": "Service", "name": "api", "selector": {"app": "api"}},
                ],
                "edges": [{"source": "service/api", "target": "workload/api", "kind": "selector_routes"}],
            },
            "business_oracle": {"workflow": "GET /", "success": "HTTP 200"},
        },
    }


def payload(count: int = 5) -> dict:
    return {
        "project_id": "demo",
        "project_commit": "a" * 40,
        "hypotheses": [
            {
                "hypothesis_id": f"h-{index}",
                "target": "workload/api",
                "target_kind": "service",
                "fault_family": ["pod_kill", "network_delay", "network_loss", "container_cpu_stress", "network_delay"][index],
                "parameters": [
                    {"mode": "one"},
                    {"latency_ms": 10, "duration_s": 5},
                    {"loss_percent": 10, "duration_s": 5},
                    {"workers": 1, "load_percent": 20, "duration_s": 5},
                    {"latency_ms": 20, "duration_s": 5},
                ][index],
                "hypothesis": "pod interruption tests availability",
                "weakness_surface": "api",
                "expected_invariant": "request succeeds after recovery",
                "validation_plan": "run the frozen oracle",
                "recovery_expectation": "pod returns",
                "call_chain": [{"source": "service/api", "target": "workload/api", "relation": "selects", "evidence_ref": "topology"}],
            }
            for index in range(count)
        ],
    }


def ready_profile() -> dict:
    return {"runtime_ready": True, "status": "runtime_ready"}


def test_handoff_selects_first_four_and_creates_two_repetitions() -> None:
    result = build_discovery_handoff(bundle(), payload(), ready_profile())
    assert result["status"] == "handoff_ready"
    assert len(result["selected_hypotheses"]) == 4
    assert result["budget_not_executed"] == ["h-4"]
    assert [item["replicate"] for item in result["runtime_units"]] == [1, 2, 1, 2, 1, 2, 1, 2]
    assert all(item["execution_started"] is False for item in result["runtime_units"])


def test_handoff_refuses_blocked_runtime_profile() -> None:
    with pytest.raises(ValueError, match="runtime profile is not ready"):
        build_discovery_handoff(bundle(), payload(1), {"runtime_ready": False})
