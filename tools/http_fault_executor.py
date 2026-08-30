"""HTTP fault adapter with an explicit runtime dependency.

The adapter validates the backend boundary and delegates lifecycle sequencing to
the injected Kubernetes executor. It never creates a live runtime implicitly.
"""

from __future__ import annotations

from typing import Any, Callable


HTTP_FAULTS = frozenset({
    "http_delay",
    "http_abort",
    "http_status_error",
    "http_response_corrupt",
    "dependency_error",
    "connection_reset",
})


def execute_http_fault(
    manifest: dict[str, Any],
    *,
    lifecycle_executor: Callable[..., dict[str, Any]] | None = None,
    phase: dict[str, Any] | None = None,
    fault: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Delegate one validated HTTPChaos manifest to the runtime lifecycle.

    A caller must inject the already-approved lifecycle executor. This keeps
    capability lookup side-effect free and preserves the live approval and
    namespace gates owned by :class:`KubernetesLifecycleExecutor`.
    """

    if not isinstance(manifest, dict) or str(manifest.get("kind") or "") != "HTTPChaos":
        return {"status": "method_invalid", "errors": ["HTTP executor requires an HTTPChaos manifest"]}
    if lifecycle_executor is None or not callable(lifecycle_executor):
        return {"status": "method_invalid", "errors": ["lifecycle_executor is required for HTTP fault execution"]}
    try:
        result = lifecycle_executor(manifest, phase=phase, fault=fault)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return {"status": "method_invalid", "errors": [f"HTTP lifecycle executor failed: {type(exc).__name__}: {exc}"]}
    if not isinstance(result, dict):
        return {"status": "method_invalid", "errors": ["HTTP lifecycle executor must return an object"]}
    return result
