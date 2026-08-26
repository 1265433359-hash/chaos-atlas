from __future__ import annotations

from copy import deepcopy

from tools.registry_shadow import build_registry_shadow, evaluate_registry_quality


def _candidate(candidate_id: str, *, score: int = 50) -> dict:
    return {
        "candidate_id": candidate_id,
        "target": candidate_id.split(":", 1)[-1],
        "fault_family": "pod_kill",
        "retrieval_score": score,
    }


def _registry() -> dict:
    hypotheses = [
        {
            "hypothesis_id": "runtime:candidate-a:pod-kill",
            "kind": "runtime",
            "target": "candidate-a",
            "target_kind": "deployment",
            "candidate_id": "candidate-a",
            "mechanism": "pod_kill",
            "preconditions": ["baseline"],
            "expected_observations": ["oracle"],
            "falsifiers": ["oracle remains stable"],
            "required_evidence": ["recovery"],
            "priority_score": 20,
            "execution_eligible": True,
            "claim_scope": "advisory",
        },
        {
            "hypothesis_id": "runtime:candidate-b:pod-kill",
            "kind": "runtime",
            "target": "candidate-b",
            "target_kind": "deployment",
            "candidate_id": "candidate-b",
            "mechanism": "pod_kill",
            "preconditions": ["baseline"],
            "expected_observations": ["oracle"],
            "falsifiers": ["oracle remains stable"],
            "required_evidence": ["recovery"],
            "priority_score": 80,
            "execution_eligible": True,
            "claim_scope": "advisory",
        },
    ]
    for kind in ("architecture", "configuration", "dependency", "defense"):
        hypotheses.append({
            "hypothesis_id": f"{kind}:service:check",
            "kind": kind,
            "target": "service",
            "target_kind": "deployment",
            "candidate_id": None,
            "mechanism": f"{kind}_check",
            "preconditions": ["facts"],
            "expected_observations": ["evidence"],
            "falsifiers": ["verified"],
            "required_evidence": ["manifest"],
            "priority_score": 90,
            "execution_eligible": False,
            "claim_scope": "advisory",
        })
    return {
        "schema_version": "chaosatlas-hypothesis-registry-v1",
        "claim_scope": "advisory",
        "hypotheses": hypotheses,
        "hypothesis_count": len(hypotheses),
        "execution_eligible_count": 2,
    }


def _candidate_space() -> dict:
    return {"candidates": [_candidate("candidate-a"), _candidate("candidate-b")]}


def test_quality_passes_and_shadow_excludes_static_hypotheses() -> None:
    registry = _registry()
    quality = evaluate_registry_quality(registry, _candidate_space(), execution_budget=1)

    assert quality["status"] == "passed"
    assert quality["checks"]["required_kinds"]["missing"] == []
    assert quality["checks"]["runtime_candidate_overlap"]["intersection"] == ["candidate-a", "candidate-b"]
    assert quality["checks"]["execution_budget"]["execution_eligible_count"] == 2
    shadow = build_registry_shadow(registry, _candidate_space(), legacy_order=["candidate-a", "candidate-b"], top_k=1, execution_budget=1)
    assert shadow["status"] == "passed"
    assert shadow["legacy_selected_candidate_ids"] == ["candidate-a"]
    assert shadow["registry_selected_candidate_ids"] == ["candidate-b"]
    assert all(item in {"candidate-a", "candidate-b"} for item in shadow["registry_candidate_ids"])
    assert shadow["static_hypothesis_count"] == 4


def test_quality_fails_closed_for_invalid_registry_inputs() -> None:
    cases = []
    missing = deepcopy(_registry())
    del missing["hypotheses"][0]["required_evidence"]
    cases.append((missing, "missing_required_field"))
    duplicate = deepcopy(_registry())
    duplicate["hypotheses"].append(deepcopy(duplicate["hypotheses"][0]))
    cases.append((duplicate, "duplicate_hypothesis_id"))
    unknown = deepcopy(_registry())
    unknown["hypotheses"][0]["candidate_id"] = "unknown"
    cases.append((unknown, "unknown_runtime_candidate"))
    non_advisory = deepcopy(_registry())
    non_advisory["hypotheses"][0]["claim_scope"] = "runtime"
    cases.append((non_advisory, "non_advisory_claim_scope"))
    static_executable = deepcopy(_registry())
    static_executable["hypotheses"][2]["execution_eligible"] = True
    cases.append((static_executable, "static_hypothesis_executable"))

    for registry, code in cases:
        result = evaluate_registry_quality(registry, _candidate_space(), execution_budget=1)
        assert result["status"] == "failed", code
        assert code in {item["code"] for item in result["errors"]}, code


def test_shadow_is_deterministic_and_has_no_side_effects() -> None:
    first = build_registry_shadow(_registry(), _candidate_space(), legacy_order=["candidate-a", "candidate-b"], top_k=1, execution_budget=1)
    second = build_registry_shadow(_registry(), _candidate_space(), legacy_order=["candidate-a", "candidate-b"], top_k=1, execution_budget=1)

    assert first == second
    assert first["selection_changed"] is True
    assert first["common_candidate_ids"] == []
    assert first["legacy_only_candidate_ids"] == ["candidate-a"]
    assert first["registry_only_candidate_ids"] == ["candidate-b"]
    assert first["mutation_executed"] is False
    assert first["policy_state_updated"] is False
    assert first["formal_knowledge_written"] is False
    assert first["claim_scope"] == "advisory"
