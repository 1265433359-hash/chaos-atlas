from tools.recovery_contract import contract_for_fault, valid_for_fault


def test_container_kill_uses_restart_contract_without_pod_replacement() -> None:
    contract = contract_for_fault(
        {
            "replacement_identity_required": True,
            "ready_required": True,
            "business_probe_required": True,
            "cleanup_required": True,
        },
        "container_kill",
    )

    assert contract == {
        "replacement_identity_required": False,
        "ready_required": True,
        "business_probe_required": True,
        "cleanup_required": True,
        "recovery_mode": "container_restart",
        "container_restart_required": True,
    }
    assert valid_for_fault(contract, "container_kill") is True


def test_pod_kill_still_requires_replacement_identity() -> None:
    contract = contract_for_fault({}, "pod_kill")
    assert contract["recovery_mode"] == "pod_replacement"
    assert valid_for_fault(contract, "pod_kill") is True
    contract["replacement_identity_required"] = False
    assert valid_for_fault(contract, "pod_kill") is False
