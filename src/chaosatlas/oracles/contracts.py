"""Business-oracle contracts shared by every ChaosAtlas run mode."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol, runtime_checkable


ORACLE_PHASES = frozenset({"baseline", "observe", "recovery"})


@runtime_checkable
class WorkflowOracle(Protocol):
    """Report business facts without classifying weakness or defense."""

    def prepare_fixture(self, run_context: dict[str, Any]) -> dict[str, Any]: ...

    def probe(self, phase: str, run_context: dict[str, Any]) -> dict[str, Any]: ...

    def collect_evidence(self, run_context: dict[str, Any]) -> dict[str, Any]: ...

    def cleanup_fixture(self, run_context: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class ProbeWorkflowOracle:
    """Adapt an existing phase probe to the complete workflow contract."""

    probe_callable: Callable[[str, dict[str, Any]], dict[str, Any]]
    kind: str

    def prepare_fixture(self, _run_context: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "not_required",
            "oracle_kind": self.kind,
            "created_resource_ids": [],
        }

    def probe(self, phase: str, run_context: dict[str, Any]) -> dict[str, Any]:
        if phase not in ORACLE_PHASES:
            raise ValueError(f"unsupported oracle phase: {phase}")
        result = self.probe_callable(phase, run_context)
        if not isinstance(result, dict):
            raise TypeError("workflow oracle probe must return an object")
        return {"oracle_kind": self.kind, **result}

    def collect_evidence(self, _run_context: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "collected",
            "oracle_kind": self.kind,
            "evidence_refs": [],
        }

    def cleanup_fixture(self, _run_context: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "not_required",
            "oracle_kind": self.kind,
            "cleanup_confirmed": True,
            "created_resource_ids": [],
        }

    def __call__(self, phase: str, run_context: dict[str, Any]) -> dict[str, Any]:
        return self.probe(phase, run_context)
