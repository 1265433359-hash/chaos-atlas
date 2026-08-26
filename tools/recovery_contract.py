"""Fault-specific recovery contracts shared by discovery and evidence planning."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


_COMMON_REQUIRED = ("ready_required", "business_probe_required", "cleanup_required")


def contract_for_fault(base: dict[str, Any] | None, fault_family: str) -> dict[str, Any]:
    """Return a normalized recovery contract for one fault family.

    PodKill replaces a Pod identity. ContainerKill restarts a container in the
    existing Pod, so requiring a new Pod UID would reject a valid recovery.
    """
    contract = deepcopy(base) if isinstance(base, dict) else {}
    for key in _COMMON_REQUIRED:
        contract.setdefault(key, True)
    if str(fault_family) == "container_kill":
        contract.update(
            {
                "recovery_mode": "container_restart",
                "replacement_identity_required": False,
                "container_restart_required": True,
            }
        )
    else:
        contract.setdefault("recovery_mode", "pod_replacement")
        contract.setdefault("replacement_identity_required", True)
    return contract


def valid_for_fault(contract: Any, fault_family: str) -> bool:
    """Validate the recovery evidence requirements for a candidate."""
    if not isinstance(contract, dict):
        return False
    if not all(contract.get(key) is True for key in _COMMON_REQUIRED):
        return False
    if str(fault_family) == "container_kill":
        return (
            contract.get("recovery_mode") == "container_restart"
            and contract.get("replacement_identity_required") is False
            and contract.get("container_restart_required") is True
        )
    return contract.get("replacement_identity_required") is True
