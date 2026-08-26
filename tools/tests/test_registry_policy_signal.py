from __future__ import annotations

from copy import deepcopy

from tools.registry_policy_signal import build_registry_policy_signal


def _registry() -> dict:
    return {
        "schema_version": "chaosatlas-hypothesis-registry-v1",
        "claim_scope": "advisory",
        "hypotheses": [
            {"hypothesis_id": "r-a", "kind": "runtime", "candidate_id": "candidate-a", "priority_score": 100, "execution_eligible": True, "claim_scope": "advisory"},
            {"hypothesis_id": "r-b", "kind": "runtime", "candidate_id": "candidate-b", "priority_score": 50, "execution_eligible": True, "claim_scope": "advisory"},
            {"hypothesis_id": "a-1", "kind": "architecture", "candidate_id": None, "priority_score": 999, "execution_eligible": False, "claim_scope": "advisory"},
        ],
    }


def _quality() -> dict:
    return {"schema_version": "chaosatlas-registry-quality-v1", "status": "passed", "claim_scope": "advisory"}


def _space() -> dict:
    return {"candidates": [{"candidate_id": "candidate-a"}, {"candidate_id": "candidate-b"}]}


def test_signal_accepts_runtime_entries_and_caps_bonus() -> None:
    signal = build_registry_policy_signal(_registry(), _quality(), _space(), bonus_cap=0.25)

    assert signal["status"] == "ready"
    assert signal["allowed_candidate_ids"] == ["candidate-a", "candidate-b"]
    assert signal["priority_bonus"]["candidate-a"] == 0.25
    assert signal["priority_bonus"]["candidate-b"] == 0.125
    assert max(signal["priority_bonus"].values()) <= 0.25
    assert signal["fallback_reason"] is None
    assert signal["claim_scope"] == "advisory"


def test_signal_excludes_static_and_falls_back_for_invalid_inputs() -> None:
    static = build_registry_policy_signal(_registry(), _quality(), _space())
    assert "a-1" not in static["priority_bonus"]

    bad_quality = build_registry_policy_signal(_registry(), {"status": "failed"}, _space())
    assert bad_quality["status"] == "fallback"
    assert bad_quality["fallback_reason"] == "quality_not_passed"

    unknown = deepcopy(_registry())
    unknown["hypotheses"][0]["candidate_id"] = "unknown"
    bad_candidate = build_registry_policy_signal(unknown, _quality(), _space())
    assert bad_candidate["status"] == "fallback"
    assert bad_candidate["fallback_reason"] == "unknown_runtime_candidate"


def test_signal_rejects_bad_bonus_cap_and_is_deterministic() -> None:
    first = build_registry_policy_signal(_registry(), _quality(), _space(), bonus_cap=0.25)
    second = build_registry_policy_signal(_registry(), _quality(), _space(), bonus_cap=0.25)
    assert first == second

    negative = build_registry_policy_signal(_registry(), _quality(), _space(), bonus_cap=-1)
    assert negative["status"] == "fallback"
    assert negative["fallback_reason"] == "invalid_bonus_cap"
