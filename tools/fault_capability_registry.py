"""Backend capability lookup for product-level fault intents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from tools.fault_catalog import fault_catalog, get_fault_spec


Executor = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class CapabilitySpec:
    fault_id: str
    status: str
    backend: str
    category: str
    risk_level: str
    executor: Executor | None = None
    semantic_alias: str | None = None


def _executor_for(_fault_id: str) -> Executor | None:
    if _fault_id in {
        "http_delay",
        "http_abort",
        "http_status_error",
        "http_response_corrupt",
        "dependency_error",
        "connection_reset",
    }:
        from tools.http_fault_executor import execute_http_fault

        return execute_http_fault
    if _fault_id in {"http_rate_limit", "business_dependency_unreachable"}:
        from tools.native_http_fault_executor import NativeHttpFaultExecutor

        def execute_native_http_fault(manifest: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
            executor = kwargs.pop("executor", None)
            if executor is None:
                raise ValueError("native HTTP fault execution requires a configured executor")
            if not isinstance(executor, NativeHttpFaultExecutor):
                raise TypeError("native HTTP executor has an invalid type")
            return executor(manifest, **kwargs)

        return execute_native_http_fault
    if _fault_id in {"replica_reduction", "config_reload", "config_drift", "env_misconfiguration", "secret_rotation", "rollout_pause", "image_pull_failure", "pod_unschedulable"}:
        from tools.kubernetes_fault_executor import KubernetesApiFaultExecutor

        def execute_kubernetes_api_fault(manifest: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
            executor = kwargs.pop("executor", None)
            if executor is None:
                raise ValueError("Kubernetes API fault execution requires a configured executor")
            return executor(manifest, **kwargs)

        return execute_kubernetes_api_fault
    if _fault_id == "api_server_delay":
        from tools.kubernetes_fault_executor import ControlPlaneDelayExecutor

        def execute_control_plane_fault(manifest: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
            executor = kwargs.pop("executor", None)
            if executor is None:
                raise ValueError("control-plane fault execution requires a configured executor")
            if not isinstance(executor, ControlPlaneDelayExecutor):
                raise TypeError("control-plane executor has an invalid type")
            return executor(manifest, **kwargs)

        return execute_control_plane_fault
    if _fault_id in {"dns_failure", "dns_delay"}:
        from tools.kubernetes_lifecycle_executor import KubernetesLifecycleExecutor

        def execute_dns_fault(manifest: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
            executor = kwargs.pop("executor", None)
            if executor is None:
                raise ValueError("DNS fault execution requires a configured executor")
            if not isinstance(executor, KubernetesLifecycleExecutor):
                raise TypeError("DNS executor has an invalid type")
            return executor(manifest, **kwargs)

        return execute_dns_fault
    if _fault_id in {"disk_pressure", "file_descriptor_exhaustion", "process_exhaustion"}:
        from tools.native_resource_fault_executor import NativeResourceFaultExecutor

        def execute_native_resource_fault(manifest: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
            executor = kwargs.pop("executor", None)
            if executor is None:
                raise ValueError("native resource fault execution requires a configured executor")
            if not isinstance(executor, NativeResourceFaultExecutor):
                raise TypeError("native resource executor has an invalid type")
            return executor(manifest, **kwargs)

        return execute_native_resource_fault
    # Other executors are registered by later capability batches. Planned
    # entries deliberately remain non-executable until their full contract
    # exists.
    return None


def capability_for(fault_id: str) -> CapabilitySpec:
    key = str(fault_id or "").strip()
    spec = get_fault_spec(key)
    canonical = str(spec.get("semantic_alias") or key)
    catalog_entry = fault_catalog()[canonical]
    return CapabilitySpec(
        fault_id=key,
        status=str(catalog_entry["status"]),
        backend=str(catalog_entry["backend"]),
        category=str(spec["category"]),
        risk_level=str(catalog_entry["risk_level"]),
        # A planned family may have a fully validated executor contract while
        # still requiring live evidence before it is promoted to implemented.
        executor=_executor_for(canonical),
        semantic_alias=canonical if canonical != key else None,
    )


def capabilities() -> dict[str, CapabilitySpec]:
    """Return all canonical capabilities without compatibility aliases."""
    return {fault_id: capability_for(fault_id) for fault_id in fault_catalog()}
