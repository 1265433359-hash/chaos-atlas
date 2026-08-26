"""Explicit execution status for every deployment fault family."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


_REGISTRY: dict[str, dict[str, Any]] = {
    "pod_kill": {"status": "ready", "executor": "KubernetesLifecycleExecutor", "required_evidence": ["pod_identity", "baseline_oracle", "recovery", "cleanup"]},
    "container_kill": {"status": "ready", "executor": "KubernetesLifecycleExecutor", "required_evidence": ["container_restart", "baseline_oracle", "recovery", "cleanup"]},
    "stress_cpu": {"status": "ready", "executor": "KubernetesLifecycleExecutor", "required_evidence": ["resource_effect", "baseline_oracle", "recovery", "cleanup"]},
    "stress_memory": {"status": "ready", "executor": "KubernetesLifecycleExecutor", "required_evidence": ["resource_effect", "baseline_oracle", "recovery", "cleanup"]},
    "network_loss": {"status": "ready", "executor": "KubernetesLifecycleExecutor", "required_evidence": ["network_effect", "baseline_oracle", "recovery", "cleanup"]},
    "network_partition": {"status": "ready", "executor": "KubernetesLifecycleExecutor", "required_evidence": ["network_effect", "baseline_oracle", "recovery", "cleanup"]},
    "network_delay": {"status": "pending_method_freeze", "executor": None, "required_evidence": ["latency_effect", "timeout_or_retry_behavior", "recovery", "cleanup"]},
    "backend_pod_kill": {"status": "pending_method_freeze", "executor": None, "required_evidence": ["backend_identity", "route_effect", "recovery", "cleanup"]},
    "config_reload": {"status": "pending_method_freeze", "executor": None, "required_evidence": ["config_diff", "reload_confirmation", "recovery", "cleanup"]},
    "replica_reduction": {"status": "pending_method_freeze", "executor": None, "required_evidence": ["replica_transition", "endpoint_continuity", "recovery", "cleanup"]},
}


def list_fault_executors() -> dict[str, dict[str, Any]]:
    return deepcopy(_REGISTRY)


def get_fault_executor(family: str, *, live: bool = False) -> dict[str, Any]:
    item = _REGISTRY.get(str(family))
    if item is None:
        return {"family": str(family), "status": "method_invalid", "executor": None, "required_evidence": [], "can_execute": False}
    result = {"family": str(family), **deepcopy(item)}
    result["can_execute"] = result["status"] == "ready" and bool(result["executor"])
    if live and result["status"] != "ready":
        result["can_execute"] = False
    return result

