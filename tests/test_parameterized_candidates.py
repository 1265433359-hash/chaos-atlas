import pytest

from tools.parameterized_candidates import expand_candidate


def test_parameter_ladder_keeps_baseline_id_and_shares_causal_cluster():
    candidate = {
        "candidate_id": "server:deployment:node:network_delay",
        "target": "api",
        "target_kind": "deployment",
        "fault_family": "network_delay",
        "service_target": "api",
        "recovery_contract": {"recovery_mode": "pod_replacement"},
    }
    variants = expand_candidate(
        candidate,
        {
            "parameter_ladders": {
                "network_delay": [
                    {"level": "baseline", "parameters": {"latency_ms": 500, "jitter_ms": 0, "correlation": 100}},
                    {"level": "low", "parameters": {"latency_ms": 100, "jitter_ms": 0, "correlation": 100}},
                    {"level": "high", "parameters": {"latency_ms": 1000, "jitter_ms": 0, "correlation": 100}},
                ]
            }
        },
    )

    assert [item["candidate_id"] for item in variants] == [
        "server:deployment:node:network_delay",
        "server:deployment:node:network_delay:low",
        "server:deployment:node:network_delay:high",
    ]
    assert [item["parameter_level"] for item in variants] == ["baseline", "low", "high"]
    assert len({item["candidate_id"] for item in variants}) == 3
    assert len({item["causal_cluster_id"] for item in variants}) == 1


def test_parameter_ladder_substitutes_target_in_parameters():
    candidate = {
        "candidate_id": "server:deployment:node:dns_delay",
        "target": "api",
        "service_target": "api-service",
        "fault_family": "dns_delay",
    }
    variants = expand_candidate(
        candidate,
        {"parameter_ladders": {"dns_delay": [{"level": "baseline", "parameters": {"hostname": "{service_target}", "latency_ms": 300}}]}},
    )

    assert variants[0]["parameters"] == {"hostname": "api-service", "latency_ms": 300}


def test_invalid_duplicate_parameter_levels_fail_closed():
    candidate = {"candidate_id": "candidate", "fault_family": "stress_cpu", "target": "api"}
    with pytest.raises(ValueError, match="duplicate parameterized candidate id"):
        expand_candidate(
            candidate,
            {"parameter_ladders": {"stress_cpu": [{"level": "low", "parameters": {}}, {"level": "low", "parameters": {}}]}},
        )
