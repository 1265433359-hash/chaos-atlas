"""Fail-closed registry for built-in and project workflow oracles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from chaosatlas.oracles.contracts import ProbeWorkflowOracle, WorkflowOracle
from tools.dify_chatflow_oracle import DifyChatflowOracle


@dataclass(frozen=True)
class OracleRuntime:
    namespace: str
    kube_context: str | None = None
    default_probe: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None


OracleFactory = Callable[[dict[str, Any], OracleRuntime], WorkflowOracle]


class OracleRegistry:
    """Resolve a declared oracle kind to one auditable workflow contract."""

    def __init__(self) -> None:
        self._factories: dict[str, OracleFactory] = {}

    def register(self, kind: str, factory: OracleFactory, *, replace: bool = False) -> None:
        normalized = str(kind).strip().lower()
        if not normalized:
            raise ValueError("oracle kind is required")
        if normalized in self._factories and not replace:
            raise ValueError(f"oracle kind already registered: {normalized}")
        self._factories[normalized] = factory

    def supports(self, kind: str) -> bool:
        return str(kind).strip().lower() in self._factories

    def kinds(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))

    def create(
        self,
        oracle: dict[str, Any],
        *,
        namespace: str,
        kube_context: str | None = None,
        default_probe: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    ) -> WorkflowOracle:
        kind = str(oracle.get("kind") or "http").strip().lower()
        factory = self._factories.get(kind)
        if factory is None:
            raise ValueError(f"live business oracle does not support {kind or 'unknown'}")
        workflow = factory(
            dict(oracle),
            OracleRuntime(
                namespace=str(namespace),
                kube_context=str(kube_context).strip() if kube_context else None,
                default_probe=default_probe,
            ),
        )
        if not isinstance(workflow, WorkflowOracle):
            raise TypeError(f"oracle factory did not return a WorkflowOracle: {kind}")
        return workflow


def _lifecycle_factory(kind: str) -> OracleFactory:
    def create(_oracle: dict[str, Any], runtime: OracleRuntime) -> WorkflowOracle:
        if runtime.default_probe is None:
            raise ValueError(f"{kind} oracle requires a lifecycle probe")
        return ProbeWorkflowOracle(runtime.default_probe, kind)

    return create


def _dify_factory(oracle: dict[str, Any], runtime: OracleRuntime) -> WorkflowOracle:
    probe = DifyChatflowOracle.from_oracle(
        oracle,
        namespace=runtime.namespace,
        kube_context=runtime.kube_context,
    )
    return ProbeWorkflowOracle(probe, "dify_chatflow")


def build_default_oracle_registry() -> OracleRegistry:
    registry = OracleRegistry()
    registry.register("http", _lifecycle_factory("http"))
    registry.register("grpc", _lifecycle_factory("grpc"))
    registry.register("dify_chatflow", _dify_factory)
    return registry


DEFAULT_ORACLE_REGISTRY = build_default_oracle_registry()
