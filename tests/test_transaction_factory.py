from copy import deepcopy

from chaosatlas.oracles.transaction_factory import TransactionOracleFactory
from chaosatlas.oracles.recovery_ledger import RecoveryLedger
from test_transaction_v3_session import Runtime, Transport, frozen


def test_factory_is_dependency_injected_and_builds_workflow(tmp_path):
    runtime = Runtime()
    transport = Transport()
    runtime.open = lambda: transport
    oracle = TransactionOracleFactory(
        runtime=runtime, contract=frozen(), fixtures={}, credential_headers=lambda _: {},
        ledger_root=tmp_path, journal=lambda _: None, synthetic_test_only=True,
    ).build()
    assert oracle.replayer.contract['schema_version'] == 'chaosatlas-transaction-oracle-v3'
    assert oracle.replayer.transport is transport


def test_factory_does_not_accept_live_without_approved_lease(tmp_path):
    runtime = Runtime()
    runtime.open = lambda: Transport()
    try:
        TransactionOracleFactory(runtime=runtime, contract=frozen(), fixtures={}, credential_headers=lambda _: {},
                                 ledger_root=tmp_path, journal=lambda _: None).build()
    except ValueError as exc:
        assert 'verified LeaseRuntime' in str(exc)
    else:
        raise AssertionError('live construction must remain gated')
