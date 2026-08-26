from tools.causal_identity import canonical_causal_identity, causal_cluster_id


def test_prompt_wording_and_display_name_do_not_change_cluster():
    first = {
        "candidate_id": "A",
        "target": "station",
        "target_kind": "deployment",
        "fault_family": "network_delay",
        "business_oracle": {"id": "order-success"},
        "recovery_contract": {"id": "pod-ready"},
        "parameters": {"latency_ms": 100, "duration_s": 30},
        "hypothesis": "first wording",
    }
    second = {**first, "candidate_id": "renamed", "hypothesis": "different wording"}
    assert causal_cluster_id(first) == causal_cluster_id(second)


def test_fault_family_changes_cluster_but_parameter_points_share_domain():
    delay = {
        "target": "station",
        "target_kind": "deployment",
        "fault_family": "network_delay",
        "business_oracle": "order-success",
        "recovery_contract": "pod-ready",
        "parameters": {"latency_ms": 100},
    }
    stronger = {**delay, "parameters": {"latency_ms": 500}}
    kill = {**delay, "fault_family": "pod_kill", "parameters": {"mode": "one"}}
    assert canonical_causal_identity(delay)["parameter_domain"] == "latency_ms"
    assert canonical_causal_identity(stronger)["parameter_domain"] == "latency_ms"
    assert causal_cluster_id(delay) == causal_cluster_id(stronger)
    assert causal_cluster_id(delay) != causal_cluster_id(kill)
