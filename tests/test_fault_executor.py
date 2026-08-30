from tools.fault_executor import LifecycleAttestation, validate_attestation


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
