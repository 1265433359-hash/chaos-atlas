"""Construct one transaction WorkflowOracle from explicit runtime dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from chaosatlas.oracles.recovery_ledger import RecoveryLedger
from chaosatlas.oracles.replay import TransactionWorkflowOracle
from chaosatlas.oracles.replay_session import ReplaySession


@dataclass(frozen=True)
class TransactionOracleDependencies:
    """Explicit, lease-bound inputs required by the registered transaction Oracle."""

    runtime: Any
    contract: dict[str, Any]
    fixtures: dict[str, Any]
    credential_headers: Callable[[str], dict[str, str]]
    ledger_root: str | Path
    journal: Callable[[dict[str, Any]], None]
    synthetic_test_only: bool = False
    environment_releaser: Callable[[], Any] | None = None


class ManagedTransactionWorkflowOracle:
    """Close the lease tunnel on every terminal workflow path."""

    def __init__(self, workflow: TransactionWorkflowOracle, runtime: Any) -> None:
        self._workflow = workflow
        self._runtime = runtime
        self.replayer = workflow.replayer
        self._closed = False

    def _close(self) -> None:
        if not self._closed:
            self._runtime.close()
            self._closed = True

    def prepare_fixture(self, run_context: dict[str, Any]) -> dict[str, Any]:
        try:
            result = self._workflow.prepare_fixture(run_context)
        except BaseException:
            self._close()
            raise
        if result.get("status") != "prepared":
            self._close()
        return result

    def probe(self, phase: str, run_context: dict[str, Any]) -> dict[str, Any]:
        return self._workflow.probe(phase, run_context)

    def collect_evidence(self, run_context: dict[str, Any]) -> dict[str, Any]:
        return self._workflow.collect_evidence(run_context)

    def cleanup_fixture(self, run_context: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._workflow.cleanup_fixture(run_context)
        finally:
            self._close()


class TransactionOracleFactory:
    """Dependency-injected factory; it never discovers credentials or targets."""

    def __init__(self, *, runtime: Any, contract: dict[str, Any], fixtures: dict[str, Any],
                 credential_headers: Callable[[str], dict[str, str]],
                 ledger_root: str | Path, journal: Callable[[dict[str, Any]], None],
                 synthetic_test_only: bool = False, environment_releaser: Callable[[], Any] | None = None):
        self.runtime = runtime
        self.contract = contract
        self.fixtures = fixtures
        self.credential_headers = credential_headers
        self.ledger = RecoveryLedger(ledger_root)
        self.journal = journal
        self.synthetic_test_only = synthetic_test_only
        self.environment_releaser = environment_releaser

    @classmethod
    def from_dependencies(cls, dependencies: TransactionOracleDependencies) -> "TransactionOracleFactory":
        if not isinstance(dependencies, TransactionOracleDependencies):
            raise ValueError("explicit transaction Oracle dependencies are required")
        return cls(
            runtime=dependencies.runtime,
            contract=dependencies.contract,
            fixtures=dependencies.fixtures,
            credential_headers=dependencies.credential_headers,
            ledger_root=dependencies.ledger_root,
            journal=dependencies.journal,
            synthetic_test_only=dependencies.synthetic_test_only,
            environment_releaser=dependencies.environment_releaser,
        )

    def build(self) -> ManagedTransactionWorkflowOracle:
        transport = self.runtime.open()
        workflow = TransactionWorkflowOracle(ReplaySession(
            self.contract, transport,
            credential_headers=self.credential_headers,
            fixtures=self.fixtures,
            runtime=self.runtime,
            ledger=self.ledger,
            journal=self.journal,
            synthetic_test_only=self.synthetic_test_only,
            environment_releaser=self.environment_releaser,
        ))
        return ManagedTransactionWorkflowOracle(workflow, self.runtime)
