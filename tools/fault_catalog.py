"""Canonical product-level fault intent catalog.

The catalog intentionally contains stable product intents. Runtime aliases from
older experiments are resolved separately so they do not inflate the 32-class
product count.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


_CATALOG: dict[str, dict[str, Any]] = {
    # Workload and resource
    "pod_kill": {"status": "implemented", "backend": "PodChaos", "category": "workload", "risk_level": "medium"},
    "container_kill": {"status": "implemented", "backend": "PodChaos", "category": "workload", "risk_level": "medium"},
    "stress_cpu": {"status": "implemented", "backend": "StressChaos", "category": "resource", "risk_level": "medium"},
    "stress_memory": {"status": "implemented", "backend": "StressChaos", "category": "resource", "risk_level": "high"},
    "disk_pressure": {"status": "implemented", "backend": "NativeExecutor", "category": "resource", "risk_level": "high"},
    "file_descriptor_exhaustion": {"status": "implemented", "backend": "NativeExecutor", "category": "resource", "risk_level": "high"},
    "process_exhaustion": {"status": "implemented", "backend": "NativeExecutor", "category": "resource", "risk_level": "high"},
    "replica_reduction": {"status": "implemented", "backend": "KubernetesAPI", "category": "scaling", "risk_level": "high"},
    # Network and protocol
    "network_loss": {"status": "implemented", "backend": "NetworkChaos", "category": "network", "risk_level": "high"},
    "network_partition": {"status": "implemented", "backend": "NetworkChaos", "category": "network", "risk_level": "high"},
    "network_delay": {"status": "implemented", "backend": "NetworkChaos", "category": "network", "risk_level": "medium"},
    "network_bandwidth": {"status": "implemented", "backend": "NetworkChaos", "category": "network", "risk_level": "medium"},
    "network_duplicate": {"status": "implemented", "backend": "NetworkChaos", "category": "network", "risk_level": "medium"},
    "network_corrupt": {"status": "implemented", "backend": "NetworkChaos", "category": "network", "risk_level": "medium"},
    "dns_failure": {"status": "implemented", "backend": "DNSChaos", "category": "network", "risk_level": "high"},
    "dns_delay": {"status": "implemented", "backend": "DNSChaos", "category": "network", "risk_level": "medium"},
    # HTTP and business
    "http_delay": {"status": "implemented", "backend": "HTTPChaos", "category": "http_business", "risk_level": "medium"},
    "http_abort": {"status": "implemented", "backend": "HTTPChaos", "category": "http_business", "risk_level": "high"},
    "http_status_error": {"status": "implemented", "backend": "HTTPChaos", "category": "http_business", "risk_level": "medium"},
    "http_response_corrupt": {"status": "implemented", "backend": "HTTPChaos", "category": "http_business", "risk_level": "medium"},
    "http_rate_limit": {"status": "implemented", "backend": "NativeExecutor", "category": "http_business", "risk_level": "medium"},
    "dependency_error": {"status": "implemented", "backend": "HTTPChaos", "category": "http_business", "risk_level": "high"},
    "connection_reset": {"status": "implemented", "backend": "HTTPChaos", "category": "http_business", "risk_level": "high"},
    "business_dependency_unreachable": {"status": "implemented", "backend": "NativeExecutor", "category": "http_business", "risk_level": "high"},
    # Configuration, release, scaling and platform
    "config_reload": {"status": "implemented", "backend": "KubernetesAPI", "category": "configuration", "risk_level": "medium"},
    "config_drift": {"status": "implemented", "backend": "KubernetesAPI", "category": "configuration", "risk_level": "high"},
    "env_misconfiguration": {"status": "implemented", "backend": "KubernetesAPI", "category": "configuration", "risk_level": "high"},
    "secret_rotation": {"status": "implemented", "backend": "KubernetesAPI", "category": "configuration", "risk_level": "high"},
    "rollout_pause": {"status": "implemented", "backend": "KubernetesAPI", "category": "release", "risk_level": "medium"},
    "image_pull_failure": {"status": "implemented", "backend": "KubernetesAPI", "category": "release", "risk_level": "high"},
    "pod_unschedulable": {"status": "implemented", "backend": "KubernetesAPI", "category": "platform", "risk_level": "high"},
    "api_server_delay": {"status": "implemented", "backend": "NativeExecutor", "category": "platform", "risk_level": "critical"},
}

_ALIASES: dict[str, str] = {"backend_pod_kill": "pod_kill"}


def get_fault_spec(fault_family: str) -> dict[str, Any]:
    """Return a copy of one canonical entry or a legacy alias."""
    key = str(fault_family or "").strip()
    canonical = _ALIASES.get(key, key)
    if canonical not in _CATALOG:
        raise KeyError(f"unknown fault family: {key}")
    result = {"fault_family": key, **deepcopy(_CATALOG[canonical])}
    if key != canonical:
        result["semantic_alias"] = canonical
        result["category"] = "dependency"
    return result


def fault_catalog() -> dict[str, dict[str, Any]]:
    """Return exactly the 32 product-level entries, excluding aliases."""
    return {key: deepcopy(value) for key, value in _CATALOG.items()}


def implemented_fault_families() -> tuple[str, ...]:
    """Return implemented canonical IDs plus compatibility aliases."""
    implemented = [key for key, value in _CATALOG.items() if value.get("status") == "implemented"]
    implemented.extend(alias for alias, canonical in _ALIASES.items() if canonical in implemented)
    return tuple(implemented)
