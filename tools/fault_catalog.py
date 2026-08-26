"""Canonical fault-family metadata shared by discovery and compilation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


_CATALOG: dict[str, dict[str, Any]] = {
    "pod_kill": {"status": "implemented", "backend": "PodChaos", "category": "workload"},
    "container_kill": {"status": "implemented", "backend": "PodChaos", "category": "workload"},
    "stress_cpu": {"status": "implemented", "backend": "StressChaos", "category": "resource"},
    "stress_memory": {"status": "implemented", "backend": "StressChaos", "category": "resource"},
    "network_loss": {"status": "implemented", "backend": "NetworkChaos", "category": "network"},
    "network_partition": {"status": "implemented", "backend": "NetworkChaos", "category": "network"},
    "network_delay": {"status": "implemented", "backend": "NetworkChaos", "category": "network"},
    "backend_pod_kill": {"status": "planned", "backend": "PodChaos", "category": "dependency"},
    "config_reload": {"status": "planned", "backend": "KubernetesAPI", "category": "configuration"},
    "replica_reduction": {"status": "planned", "backend": "KubernetesAPI", "category": "scaling"},
}


def get_fault_spec(fault_family: str) -> dict[str, Any]:
    """Return a copy of one catalog entry, failing closed for unknown types."""
    key = str(fault_family or "").strip()
    if key not in _CATALOG:
        raise KeyError(f"unknown fault family: {key}")
    return {"fault_family": key, **deepcopy(_CATALOG[key])}


def fault_catalog() -> dict[str, dict[str, Any]]:
    return {key: deepcopy(value) for key, value in _CATALOG.items()}


def implemented_fault_families() -> tuple[str, ...]:
    return tuple(key for key, value in _CATALOG.items() if value.get("status") == "implemented")
