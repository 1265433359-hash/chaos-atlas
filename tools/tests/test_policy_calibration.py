from tools.policy_calibration import new_calibration, record_policy_outcome


def test_calibration_counts_runtime_yield_and_stop_reasons():
    calibration = new_calibration("demo", "round-1")
    decision = {
        "policy_selected_candidate_ids": ["candidate-a"],
        "policy_selected_hypothesis_ids": ["h-a"],
        "stop_reason": None,
    }
    result = {
        "classification": "confirmed_weakness",
        "boundary_discovered": True,
        "candidate_id": "candidate-a",
    }
    updated = record_policy_outcome(calibration, decision, result)
    assert updated["metrics"]["experiments"] == 1
    assert updated["metrics"]["confirmed_weaknesses"] == 1
    assert updated["metrics"]["boundary_discoveries"] == 1


def test_calibration_does_not_treat_protected_or_invalid_as_weakness():
    calibration = new_calibration("demo", "round-1")
    decision = {"policy_selected_candidate_ids": ["candidate-a"], "stop_reason": "resolved"}
    protected = record_policy_outcome(calibration, decision, {"classification": "protected"})
    invalid = record_policy_outcome(protected, decision, {"classification": "method_invalid"})
    assert invalid["metrics"]["confirmed_weaknesses"] == 0
    assert invalid["metrics"]["protected_waste"] == 1
    assert invalid["metrics"]["method_invalid"] == 1
    assert invalid["metrics"]["stop_reasons"]["resolved"] == 1
