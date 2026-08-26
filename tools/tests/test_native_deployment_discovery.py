from __future__ import annotations

from tools.open_discovery_compiler import contract_from_deployment_pool, compile_output


def test_native_compiler_accepts_manifest_deployment_hypothesis_without_runtime_fields():
    pool = {"project_id": "p", "project_commit": "a" * 40, "namespace": "ns", "candidates": [{"target": "deployment:api", "target_kind": "deployment", "compile_eligible": True}]}
    contract = contract_from_deployment_pool(pool)
    payload = {"project_id": "p", "project_commit": "a" * 40, "hypotheses": [{"hypothesis_id": "h1", "target": "deployment:api", "target_kind": "deployment", "fault_family": "pod_kill", "parameters": {"mode": "one"}, "hypothesis": "one pod loss reduces availability", "weakness_surface": "replica availability", "call_chain": [{"source": "deployment:api", "target": "deployment:api", "relation": "deployment_pod", "evidence_ref": "manifest"}], "expected_invariant": "available replicas", "expected_steady_state": "availableReplicas >= 1", "validation_plan": "baseline inject observe recover cleanup", "recovery_expectation": "replacement becomes ready"}]}
    result = compile_output(payload, contract)
    assert result["status"] == "valid"
    assert result["accepted"][0]["target_kind"] == "deployment"


def test_deployment_payload_with_runtime_observation_is_rejected():
    pool = {"project_id": "p", "project_commit": "a" * 40, "namespace": "ns", "candidates": [{"target": "deployment:api", "target_kind": "deployment", "compile_eligible": True}]}
    contract = contract_from_deployment_pool(pool)
    result = compile_output({"project_id": "p", "project_commit": "a" * 40, "runtime_observation": {}, "hypotheses": []}, contract)
    assert result["status"] == "method_invalid"

