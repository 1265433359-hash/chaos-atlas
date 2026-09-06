"""Construct one transaction WorkflowOracle from explicit runtime dependencies."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from chaosatlas.oracles.recovery_ledger import RecoveryLedger
from chaosatlas.oracles.replay import TransactionWorkflowOracle
from chaosatlas.oracles.replay_session import ReplaySession


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

    def build(self) -> TransactionWorkflowOracle:
        transport = self.runtime.open()
        return TransactionWorkflowOracle(ReplaySession(
            self.contract, transport,
            credential_headers=self.credential_headers,
            fixtures=self.fixtures,
            runtime=self.runtime,
            ledger=self.ledger,
            journal=self.journal,
            synthetic_test_only=self.synthetic_test_only,
            environment_releaser=self.environment_releaser,
        ))
