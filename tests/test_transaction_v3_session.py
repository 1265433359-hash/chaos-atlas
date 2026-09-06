"""In-memory protocol tests only: no real approvals or application evidence."""

from copy import deepcopy
import json

import pytest

from chaosatlas.oracles.recovery_ledger import RecoveryLedger
from chaosatlas.oracles.replay import HttpObservation, ResponseLost, TransactionReplayer
from chaosatlas.oracles.transaction_contracts import make_draft, validate_draft, record_human_approval, freeze_approved_contract
from test_transaction_v3_validation import lease_exclusive_contract, write_contract


def frozen():
    value = write_contract()
    value.update(oracle_id='synthetic-v3', project_id='synthetic', project_revision='synthetic-test-only',
                 credential_refs=[], evidence_sources=['synthetic-test-only'], ownership={'synthetic_only': True})
    return freeze_approved_contract(record_human_approval(validate_draft(make_draft(value)), {
        'decision': 'approved', 'reviewer': 'synthetic-test-only', 'reviewed_at': '2020-01-01T00:00:00+00:00',
        'decision_reference': 'synthetic-test-only:no-real-authorization',
    }))


def frozen_lease_exclusive():
    value = lease_exclusive_contract()
    value.update(oracle_id='synthetic-lease-v3', project_id='synthetic', project_revision='synthetic-test-only',
                 credential_refs=[], evidence_sources=['synthetic-test-only'], ownership={'synthetic_only': True})
    return freeze_approved_contract(record_human_approval(validate_draft(make_draft(value)), {
        'decision': 'approved', 'reviewer': 'synthetic-test-only', 'reviewed_at': '2020-01-01T00:00:00+00:00',
        'decision_reference': 'synthetic-test-only:no-real-authorization',
    }))


class Runtime:
    def __init__(self):
        self.binding = {key: 'synthetic-' + key for key in (
            'lease_id', 'cluster_uid', 'namespace_uid', 'namespace', 'context', 'service_uid', 'service', 'principal_id', 'service_spec_sha256')}
        self.binding.update(origin='http://127.0.0.1:12345', project_revision='synthetic-test-only', principal_id='synthetic-user')

    def verify(self, scope, transport):
        return deepcopy(self.binding)


class Transport:
    def __init__(self, create_fault=None, delete_fault=None):
        self.objects = []
        self.calls = []
        self.create_fault, self.delete_fault = create_fault, delete_fault
        self.value = 1

    def send(self, **kwargs):
        self.calls.append(kwargs)
        method = kwargs['method']
        if method == 'POST':
            if self.create_fault == 'before-send':
                raise ResponseLost('synthetic-test-only')
            self.objects.append({'id': 'owned-1', 'marker': kwargs['json_body']['marker'], 'owner': 'synthetic-user'})
            if self.create_fault == 'lost':
                raise ResponseLost('synthetic-test-only')
            if self.create_fault == 'missing-id':
                return HttpObservation(201, b'{}')
            return HttpObservation(201, b'{"id":"owned-1"}')
        if method == 'DELETE':
            self.objects = [o for o in self.objects if o['id'] != kwargs['path'].split('/')[-1]]
            if self.delete_fault:
                raise ResponseLost('synthetic-test-only')
            return HttpObservation(204)
        return HttpObservation(200, json.dumps({'items': self.objects, 'total': len(self.objects), 'value': self.value}).encode())


def session(tmp_path, *, transport=None, runtime=None, contract=None, journal=None):
    return TransactionReplayer(contract or frozen(), transport or Transport(),
        credential_headers=lambda _: {}, fixtures={}, runtime=runtime or Runtime(),
        ledger=RecoveryLedger(tmp_path), journal=journal or (lambda event: None), synthetic_test_only=True)


def test_v3_public_entry_normal_and_fresh_probe(tmp_path):
    transport = Transport()
    replay = session(tmp_path, transport=transport)
    assert replay.prepare(run_id='run-test')['status'] == 'prepared'
    transport.value = 0
    assert replay.probe('fault-observe')['status'] == 'fail'
    assert replay.cleanup()['cleanup_confirmed'] is True
    assert replay.cleanup()['cleanup_confirmed'] is True
    assert sum(c['method'] == 'DELETE' for c in transport.calls) == 1


@pytest.mark.parametrize('fault', ['lost', 'missing-id'])
def test_uncertain_or_bad_write_response_reconciles_but_never_passes_business(tmp_path, fault):
    replay = session(tmp_path, transport=Transport(create_fault=fault))
    result = replay.prepare(run_id='run-test')
    assert result['status'] == 'prepare_failed'
    assert result['cleanup']['cleanup_confirmed'] is True
    assert replay.ledger.cleanup_confirmed('run-test')


def test_empty_lookup_does_not_clear_uncertain_commit(tmp_path):
    replay = session(tmp_path, transport=Transport(create_fault='before-send'))
    result = replay.prepare(run_id='run-test')
    assert result['cleanup']['cleanup_confirmed'] is False
    assert replay.ledger.load('run-test')['operations']['create']['state'] == 'outcome_unknown'
    with pytest.raises(FileExistsError):
        replay.prepare(run_id='run-test')


def test_restart_reconciles_without_resending_create_and_rebinds_local_port(tmp_path):
    transport, runtime = Transport(), Runtime()
    original = session(tmp_path, transport=transport, runtime=runtime)
    assert original.prepare(run_id='run-test')['status'] == 'prepared'
    runtime.binding['origin'] = 'http://127.0.0.1:23456'
    recovered = session(tmp_path, transport=transport, runtime=runtime)
    assert recovered.recover(run_id='run-test')['cleanup_confirmed'] is True
    assert sum(c['method'] == 'POST' for c in transport.calls) == 1


def test_deleted_response_loss_uses_absence_not_second_delete(tmp_path):
    transport = Transport(delete_fault=True)
    replay = session(tmp_path, transport=transport)
    replay.prepare(run_id='run-test')
    assert replay.cleanup()['cleanup_confirmed'] is True
    assert sum(c['method'] == 'DELETE' for c in transport.calls) == 1


def test_contract_and_capture_views_cannot_change_deletion_target(tmp_path):
    contract, transport = frozen(), Transport()
    replay = session(tmp_path, transport=transport, contract=contract)
    contract['allowed_requests'][2]['path'] = '/foreign'
    replay.contract['allowed_requests'][2]['path'] = '/foreign'
    replay.prepare(run_id='run-test')
    replay.variables['object_id'] = 'foreign'
    replay.cleanup()
    assert [c['path'] for c in transport.calls if c['method'] == 'DELETE'] == ['/objects/owned-1']


def test_same_marker_replacement_never_deleted(tmp_path):
    transport = Transport()
    replay = session(tmp_path, transport=transport)
    replay.prepare(run_id='run-test')
    transport.objects[0]['id'] = 'replacement'
    assert replay.cleanup()['cleanup_confirmed'] is False
    assert not any(c['method'] == 'DELETE' for c in transport.calls)


def test_intent_persistence_failure_blocks_send(tmp_path, monkeypatch):
    transport = Transport()
    replay = session(tmp_path, transport=transport)
    def fail(*args, **kwargs):
        raise OSError('synthetic-test-only')
    monkeypatch.setattr(replay.ledger, 'intent', fail)
    assert replay.prepare(run_id='run-test')['status'] == 'prepare_failed'
    assert not any(c['method'] == 'POST' for c in transport.calls)


def test_synthetic_approval_cannot_enable_default_execution(tmp_path):
    with pytest.raises(ValueError, match='verified LeaseRuntime'):
        TransactionReplayer(frozen(), Transport(), credential_headers=lambda _: {}, fixtures={},
                            runtime=Runtime(), ledger=RecoveryLedger(tmp_path), journal=lambda _: None)


def test_recovery_namespace_change_rejects_before_any_request(tmp_path):
    transport, runtime = Transport(), Runtime()
    replay = session(tmp_path, transport=transport, runtime=runtime)
    replay.prepare(run_id='run-test')
    calls = len(transport.calls)
    runtime.binding['namespace_uid'] = 'replacement'
    with pytest.raises(ValueError, match='identity mismatch'):
        session(tmp_path, transport=transport, runtime=runtime).recover(run_id='run-test')
    assert len(transport.calls) == calls


def test_unresolved_run_blocks_different_prepare(tmp_path):
    replay = session(tmp_path, transport=Transport(create_fault='before-send'))
    replay.prepare(run_id='run-test')
    with pytest.raises(ValueError, match='earlier transaction'):
        replay.prepare(run_id='another-run')


def test_same_identity_wrong_owner_is_not_absence(tmp_path):
    transport = Transport()
    replay = session(tmp_path, transport=transport)
    replay.prepare(run_id='run-test')
    transport.objects[0]['owner'] = 'foreign'
    assert replay.cleanup()['cleanup_confirmed'] is False
    assert not any(c['method'] == 'DELETE' for c in transport.calls)


def test_journal_failure_after_write_keeps_durable_unknown(tmp_path):
    transport = Transport()
    events = []
    def journal(event):
        events.append(event)
        if event['event'] == 'response' and event['step_id'] == 'create':
            raise OSError('synthetic-test-only journal failure')
    replay = session(tmp_path, transport=transport, journal=journal)
    result = replay.prepare(run_id='run-test')
    assert result['status'] == 'prepare_failed'
    assert result['cleanup']['cleanup_confirmed'] is True
    assert any(e['step_id'] == 'create' for e in events)


def test_eventual_read_uses_actual_remaining_deadline(tmp_path):
    from chaosatlas.isolation.contracts import with_hash
    from chaosatlas.oracles.transaction_contracts import approval_subject_sha256
    value = frozen()
    value['timeouts'].update(eventual_s=2, request_s=1, poll_interval_s=1)
    value['probe_assertions'].append({'id': 'eventual', 'operator': 'eventually', 'step_id': 'read', 'assertion_ref': 'value'})
    value['approval']['record']['approved_subject_sha256'] = approval_subject_sha256(value)
    value = with_hash(value, 'contract_sha256')
    transport = Transport()
    replay = session(tmp_path, transport=transport, contract=value)
    replay.prepare(run_id='run-test')
    now = [0.0]
    replay._monotonic = lambda: now[0]
    replay._sleep = lambda seconds: now.__setitem__(0, now[0] + seconds)
    transport.value = 0
    with pytest.raises(TimeoutError):
        replay.probe('observe')
    assert now[0] == 2
    assert replay.cleanup()['cleanup_confirmed'] is True


def test_new_session_cannot_bypass_project_pending_gate(tmp_path):
    transport = Transport(create_fault='before-send')
    replay = session(tmp_path, transport=transport)
    replay.prepare(run_id='run-test')
    second_transport = Transport()
    with pytest.raises(ValueError, match='project has an active transaction'):
        session(tmp_path, transport=second_transport).prepare(run_id='new-run')
    assert second_transport.calls == []


def test_lease_exclusive_normal_write_closes_only_after_environment_release(tmp_path):
    transport, runtime = Transport(), Runtime()
    releases = []
    replay = TransactionReplayer(
        frozen_lease_exclusive(), transport, credential_headers=lambda _: {}, fixtures={},
        runtime=runtime, ledger=RecoveryLedger(tmp_path), journal=lambda _: None,
        synthetic_test_only=True, environment_releaser=lambda: releases.append('released') or True,
    )
    assert replay.prepare(run_id='run-lease')['status'] == 'prepared'
    assert replay.cleanup()['cleanup_confirmed'] is True
    assert releases == ['released']
    assert replay.ledger.load('run-lease')['lifecycle'] == 'closed'


def test_lease_exclusive_lost_response_is_resolved_by_verified_release(tmp_path):
    transport, runtime = Transport(create_fault='lost'), Runtime()
    replay = TransactionReplayer(
        frozen_lease_exclusive(), transport, credential_headers=lambda _: {}, fixtures={},
        runtime=runtime, ledger=RecoveryLedger(tmp_path), journal=lambda _: None,
        synthetic_test_only=True, environment_releaser=lambda: True,
    )
    result = replay.prepare(run_id='run-lost')
    assert result['status'] == 'prepare_failed'
    assert result['cleanup']['cleanup_confirmed'] is True
    assert replay.ledger.load('run-lost')['lifecycle'] == 'closed'


def test_lease_exclusive_followup_mutation_reuses_creator_identity(tmp_path):
    value = lease_exclusive_contract()
    value['allowed_requests'].append({
        'id': 'update', 'method': 'PATCH', 'path': '/objects/{object_id}', 'effect': 'write',
    })
    value['steps'].insert(1, {
        'id': 'update', 'request_id': 'update', 'json_body': {'value': 2},
        'success': {'statuses': [200]},
        'on_response_loss': {'strategy': 'disposable_environment'},
        'owned_operation': 'create',
    })
    value.update(oracle_id='synthetic-lease-update-v3', project_id='synthetic',
                 project_revision='synthetic-test-only', credential_refs=[],
                 evidence_sources=['synthetic-test-only'], ownership={'synthetic_only': True})
    approved = freeze_approved_contract(record_human_approval(validate_draft(make_draft(value)), {
        'decision': 'approved', 'reviewer': 'synthetic-test-only',
        'reviewed_at': '2020-01-01T00:00:00+00:00',
        'decision_reference': 'synthetic-test-only:no-real-authorization',
    }))
    transport = Transport()
    replay = TransactionReplayer(
        approved, transport, credential_headers=lambda _: {}, fixtures={}, runtime=Runtime(),
        ledger=RecoveryLedger(tmp_path), journal=lambda _: None, synthetic_test_only=True,
        environment_releaser=lambda: True,
    )
    assert replay.prepare(run_id='run-update')['status'] == 'prepared'
    ledger = replay.ledger.load('run-update')
    assert ledger['operations']['update']['identity'] == {'object_id': 'owned-1'}
    assert replay.cleanup()['cleanup_confirmed'] is True


def test_crashed_before_first_write_requires_recovery_and_close(tmp_path):
    replay = session(tmp_path)
    binding = Runtime().binding
    replay.ledger.create('abandoned-run', project_id='synthetic', attempt_id='attempt-test',
                         contract_sha256=replay.contract['contract_sha256'], binding=binding)
    with pytest.raises(ValueError, match='active transaction'):
        replay.prepare(run_id='new-run')
    assert replay.recover(run_id='abandoned-run')['cleanup_confirmed']
    assert replay.ledger.load('abandoned-run')['lifecycle'] == 'closed'
    assert replay.prepare(run_id='new-run')['status'] == 'prepared'
    assert replay.cleanup()['cleanup_confirmed']
