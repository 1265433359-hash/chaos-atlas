"""Synthetic state persistence and identity tests, without application evidence."""

import json
import subprocess
import sys

import pytest

from chaosatlas.isolation.contracts import canonical_hash
from chaosatlas.oracles.recovery_ledger import RecoveryLedger, BINDING_KEYS
from chaosatlas.oracles.replay import UrllibHttpTransport, render_path, validate_auth_headers


def create(ledger):
    binding = {key: 'synthetic-' + key for key in BINDING_KEYS}
    ledger.create('test-run', attempt_id='test-attempt', contract_sha256='a'*64, binding=binding)
    return binding


def test_unknown_commit_persists_and_new_process_cannot_claim_cleanup(tmp_path):
    ledger = RecoveryLedger(tmp_path)
    binding = create(ledger)
    ledger.intent('test-run', 'create', object_type='synthetic', marker_sha256=canonical_hash('marker'))
    ledger.transition('test-run', 'create', 'outcome_unknown')
    loaded = RecoveryLedger(tmp_path).assert_binding('test-run', binding, 'a'*64)
    assert loaded['operations']['create']['state'] == 'outcome_unknown'
    assert not ledger.cleanup_confirmed('test-run')
    with pytest.raises(FileExistsError):
        create(ledger)
    code = "from chaosatlas.oracles.recovery_ledger import RecoveryLedger; import sys; assert not RecoveryLedger(sys.argv[1]).cleanup_confirmed('test-run')"
    result = subprocess.run([sys.executable, '-c', code, str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_owned_and_absent_require_evidence_and_binding_matches(tmp_path):
    ledger = RecoveryLedger(tmp_path)
    binding = create(ledger)
    ledger.intent('test-run', 'create', object_type='synthetic', marker_sha256='a'*64)
    ledger.transition('test-run', 'create', 'outcome_unknown')
    with pytest.raises(ValueError, match='ownership'):
        ledger.transition('test-run', 'create', 'owned_confirmed', identity={'id': 'object-1'})
    ledger.transition('test-run', 'create', 'owned_confirmed', identity={'id': 'object-1'}, ownership_sha256='b'*64)
    ledger.transition('test-run', 'create', 'cleanup_pending')
    with pytest.raises(ValueError, match='absence'):
        ledger.transition('test-run', 'create', 'absent_confirmed')
    ledger.transition('test-run', 'create', 'absent_confirmed', absence_sha256='c'*64)
    assert ledger.cleanup_confirmed('test-run')
    with pytest.raises(ValueError, match='identity mismatch'):
        ledger.assert_binding('test-run', {**binding, 'namespace_uid': 'recreated'}, 'a'*64)


def test_corrupt_ledger_and_parallel_recovery_fail_closed(tmp_path):
    ledger = RecoveryLedger(tmp_path)
    create(ledger)
    with ledger.operation('test-run'):
        code = "from chaosatlas.oracles.recovery_ledger import RecoveryLedger; import sys;\nwith RecoveryLedger(sys.argv[1]).operation('test-run'): pass"
        result = subprocess.run([sys.executable, '-c', code, str(tmp_path)], capture_output=True, text=True)
        assert result.returncode != 0
        assert 'already in progress' in result.stderr
    path = tmp_path / 'ledgers/test-run.json'
    value = json.loads(path.read_text(encoding='utf-8'))
    value['binding']['namespace_uid'] = 'replacement'
    path.write_text(json.dumps(value), encoding='utf-8')
    with pytest.raises(ValueError, match='integrity'):
        ledger.load('test-run')


@pytest.mark.parametrize('origin', ['http://u:p@localhost', 'http://localhost?x=1', 'http://localhost#fragment', 'http://localhost:0', 'http://localhost\\evil', 'http://local\nhost'])
def test_origin_rejects_ambiguous_authority(origin):
    with pytest.raises(ValueError):
        UrllibHttpTransport(origin)


@pytest.mark.parametrize('value', ['../foreign', '..', 'a/b', 'a?x=y', '%2f', 'a\\b'])
def test_identity_cannot_change_path(value):
    with pytest.raises(ValueError):
        render_path('/objects/{id}', {'id': value})


@pytest.mark.parametrize('headers', [{'Host': 'foreign'}, {'Cookie': 'session'}, {'Authorization': 'x\r\ny'}, {'Authorization': 'one', 'authorization': 'two'}])
def test_resolver_cannot_override_routing_or_headers(headers):
    with pytest.raises(ValueError):
        validate_auth_headers(headers)
