from __future__ import annotations

from tools.discovery_to_rca import build_case_from_hypothesis


def _hypothesis() -> dict:
    return {
        "hypothesis_id": "h-api-kill",
        "canonical_signature": "a" * 64,
        "target": "deployment:api",
        "target_kind": "deployment",
        "fault_family": "pod_kill",
        "parameters": {"mode": "one"},
        "hypothesis": "losing the only API pod may violate availability",
        "expected_invariant": "availableReplicas >= 1 and business probe succeeds",
        "expected_steady_state": "deployment.availableReplicas >= 1",
        "validation_plan": "baseline, inject, observe, recover, cleanup",
        "recovery_expectation": "replacement pod becomes Ready",
        "weakness_surface": "deployment availability",
    }


def test_discovery_hypothesis_becomes_pending_rca_case_without_verdict():
    case = build_case_from_hypothesis(
        _hypothesis(),
        project_id="demo",
        project_commit="a" * 40,
        round_id="discovery-r1",
        business_oracle={"workflow": "GET /", "success": "HTTP 200"},
    )
    assert case["rca_status"] == "pending"
    assert case["weakness_status"] == "candidate"
    assert case["knowledge_status"] == "none"
    assert case["hypothesis_ids"] == ["h-api-kill"]
    assert case["hypotheses"][0]["status"] == "pending"
    assert "runtime_verdict" not in case


def test_discovery_case_identity_is_stable_and_bound_to_target():
    kwargs = {
        "project_id": "demo",
        "project_commit": "a" * 40,
        "round_id": "discovery-r1",
        "business_oracle": {"workflow": "GET /", "success": "HTTP 200"},
    }
    first = build_case_from_hypothesis(_hypothesis(), **kwargs)
    second = build_case_from_hypothesis(_hypothesis(), **kwargs)
    assert first["weakness_id"] == second["weakness_id"]
    assert first["test_node"]["target"] == "deployment:api"
    assert first["hypotheses"][0]["scope"]["edge"] == "deployment:api"


def test_discovery_case_rejects_missing_recovery_contract():
    hypothesis = _hypothesis()
    hypothesis.pop("recovery_expectation")
    try:
        build_case_from_hypothesis(
            hypothesis,
            project_id="demo",
            project_commit="a" * 40,
            round_id="discovery-r1",
            business_oracle={"workflow": "GET /", "success": "HTTP 200"},
        )
    except ValueError as exc:
        assert "recovery" in str(exc)
    else:
        raise AssertionError("missing recovery contract must fail closed")

