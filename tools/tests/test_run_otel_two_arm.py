from __future__ import annotations

from pathlib import Path

from tools.run_otel_two_arm import classify_observation, consecutive_successes, validate_otel_mutation


def test_validate_otel_mutation_is_namespace_and_selector_local() -> None:
    valid = {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "PodChaos",
        "metadata": {"name": "x", "namespace": "chaosatlas-otel"},
        "spec": {"action": "pod-kill", "mode": "one", "selector": {"namespaces": ["chaosatlas-otel"], "labelSelectors": {"app": "checkout"}}},
    }
    assert validate_otel_mutation(valid)["status"] == "passed"
    invalid = {**valid, "metadata": {**valid["metadata"], "namespace": "default"}}
    assert validate_otel_mutation(invalid)["status"] == "blocked"


def test_observation_and_sustained_success_classification() -> None:
    ok = [{"grpc_status": "OK"}, {"grpc_status": "OK"}]
    bad = [{"grpc_status": "OK"}, {"grpc_status": "DEADLINE_EXCEEDED"}, {"grpc_status": "OK"}]
    assert consecutive_successes(ok) == 2
    assert consecutive_successes(bad) == 1
    assert classify_observation({"observations": ok}) == "no_business_impact_observed"
    assert classify_observation({"observations": bad}) == "weakness_observed"
