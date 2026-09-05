from tools.fault_executor import LifecycleAttestation, observation_verdict, validate_attestation


def test_attestation_requires_complete_lifecycle():
    result = validate_attestation({
        "baseline": True,
        "injection": True,
        "observation": True,
        "recovery": True,
        "cleanup": False,
        "independent_oracle": True,
        "comparison_eligible": False,
    })
    assert result.valid is False
    assert "cleanup" in result.missing


def test_complete_attestation_is_valid():
    result = validate_attestation({key: True for key in LifecycleAttestation.REQUIRED})
    assert result.valid is True
    assert result.missing == ()


def test_observation_verdict_is_terminal_after_observation():
    assert observation_verdict({"status": "pass"}, "executed") == "pass"
    assert observation_verdict({"status": "degraded"}, "executed") == "degraded"
    assert observation_verdict({"status": "business_unreachable"}, "executed") == "business_unreachable"
    assert observation_verdict({"status": "pass"}, "executed", "rate_limit_observed") == "rate_limit_observed"
    assert observation_verdict({}, "executed") == "observation_pending"
