"""Apply one WorkflowOracle lifecycle around specialized fault executors."""

from __future__ import annotations

from typing import Any, Callable

from chaosatlas.oracles.contracts import WorkflowOracle


FaultExecutor = Callable[..., dict[str, Any]]


class WorkflowBoundFaultExecutor:
    """Make non-lifecycle executors obey the shared business workflow contract."""

    def __init__(self, executor: FaultExecutor, workflow: WorkflowOracle) -> None:
        self.executor = executor
        self.workflow = workflow

    @staticmethod
    def _context(manifest: dict[str, Any]) -> dict[str, Any]:
        action_id = str((manifest.get("metadata") or {}).get("name") or "runtime-action")
        namespace = str((manifest.get("metadata") or {}).get("namespace") or "")
        return {"run_id": action_id, "action_id": action_id, "namespace": namespace}

    @staticmethod
    def _cleanup_failed(result: dict[str, Any], business_cleanup: dict[str, Any]) -> None:
        cleanup = result.get("cleanup") if isinstance(result.get("cleanup"), dict) else {}
        cleanup = dict(cleanup)
        fault_confirmed = cleanup.get("confirmed") is True
        cleanup["business"] = business_cleanup
        cleanup["confirmed"] = fault_confirmed and business_cleanup.get("cleanup_confirmed") is True
        result["cleanup"] = cleanup
        result["cleanup_confirmed"] = cleanup["confirmed"]
        if not cleanup["confirmed"]:
            result["status"] = "cleanup_failed"
            result["promotion_allowed"] = False
            attestation = result.get("attestation") if isinstance(result.get("attestation"), dict) else {}
            attestation = dict(attestation)
            attestation["valid"] = False
            attestation["cleanup"] = False
            attestation["comparison_eligible"] = False
            attestation["missing"] = sorted(set(attestation.get("missing") or []) | {"cleanup"})
            result["attestation"] = attestation

    def __call__(
        self,
        manifest: dict[str, Any],
        phase: dict[str, Any] | None = None,
        fault: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = self._context(manifest)
        prepared = self.workflow.prepare_fixture(context)
        if not isinstance(prepared, dict) or prepared.get("status") not in {"prepared", "not_required"}:
            return {
                "schema_version": "chaosatlas-workflow-bound-fault-v1",
                "status": "business_fixture_prepare_failed",
                "business_fixture": prepared,
                "injection_confirmed": False,
                "injected_count": 0,
                "recovery_confirmed": False,
                "cleanup_confirmed": bool(
                    isinstance(prepared, dict)
                    and isinstance(prepared.get("cleanup"), dict)
                    and prepared["cleanup"].get("cleanup_confirmed") is True
                ),
                "promotion_allowed": False,
                "errors": ["business workflow fixture preparation failed"],
                "lifecycle": ["prepare_fixture"],
            }
        workflow_prepared = prepared.get("status") == "prepared"
        result: dict[str, Any]
        try:
            result = self.executor(manifest, phase, fault)
            if not isinstance(result, dict):
                raise TypeError("fault executor must return an object")
        except Exception as exc:
            result = {
                "schema_version": "chaosatlas-workflow-bound-fault-v1",
                "status": "method_invalid",
                "injection_confirmed": False,
                "injected_count": 0,
                "recovery_confirmed": False,
                "cleanup": {"confirmed": False},
                "cleanup_confirmed": False,
                "promotion_allowed": False,
                "errors": [f"{type(exc).__name__}: {exc}"],
                "lifecycle": [],
            }
        result["business_fixture"] = prepared
        lifecycle = list(result.get("lifecycle") or [])
        lifecycle.insert(0, "prepare_fixture")
        try:
            evidence = self.workflow.collect_evidence(context)
        except Exception as exc:
            evidence = {"status": "failed", "reason_code": type(exc).__name__}
            result["promotion_allowed"] = False
        result["business_evidence"] = evidence
        lifecycle.append("collect_business_evidence")
        if workflow_prepared:
            try:
                business_cleanup = self.workflow.cleanup_fixture(context)
            except Exception as exc:
                business_cleanup = {
                    "status": "cleanup_failed", "cleanup_confirmed": False,
                    "errors": [{"reason_code": type(exc).__name__}],
                }
            self._cleanup_failed(result, business_cleanup)
            lifecycle.append("cleanup_fixture")
        result["lifecycle"] = list(dict.fromkeys(lifecycle))
        return result
