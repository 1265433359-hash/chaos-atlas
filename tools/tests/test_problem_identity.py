from __future__ import annotations

from tools.problem_identity import derive_problem_identity


def _run(**overrides):
    value = {
        "project_id": "demo",
        "claim_scope": "runtime",
        "rca_status": "confirmed",
        "weakness_id": "WS-demo-api-pod-kill",
        "test_node": {
            "target": "api",
            "target_kind": "deployment",
            "family": "pod_kill",
        },
        "hypotheses": [{"scope": {"edge": "deployment:api"}}],
        "symptom": {"oracle": "HTTP / on api"},
        "attestation": {
            "baseline": True,
            "injection": True,
            "observation": True,
            "recovery": True,
            "cleanup": True,
            "independent_oracle": True,
            "valid": True,
        },
        "cleanup_status": "verified",
    }
    value.update(overrides)
    return value


def test_problem_identity_is_stable_across_run_and_fault_method():
    first = derive_problem_identity(_run())
    second = derive_problem_identity(
        _run(
            weakness_id="WS-demo-api-container-kill",
            test_node={
                "target": "api",
                "target_kind": "deployment",
                "family": "container_kill",
            },
            round_id="live-2",
        )
    )

    assert first["eligible"] is True
    assert first["issue_id"] == second["issue_id"]
    assert first["weakness_id"] != second["weakness_id"]


def test_problem_identity_rejects_incomplete_cleanup_or_runtime_scope():
    blocked = derive_problem_identity(_run(cleanup_status="blocked"))
    static = derive_problem_identity(_run(claim_scope="static"))

    assert blocked["eligible"] is False
    assert "cleanup" in blocked["reasons"]
    assert static["eligible"] is False
    assert "claim_scope" in static["reasons"]


def test_problem_identity_keeps_causal_cluster_family_specific():
    first = derive_problem_identity(_run())
    second = derive_problem_identity(_run(
        test_node={
            "target": "api",
            "target_kind": "deployment",
            "family": "container_kill",
        }
    ))

    assert first["causal_cluster_id"] != second["causal_cluster_id"]

