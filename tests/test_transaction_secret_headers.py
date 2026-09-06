"""Synthetic Secret data; these tests never query real credentials."""

import base64
from copy import deepcopy

import pytest

from chaosatlas.oracles.secret_headers import SecretHeaders
from test_transaction_runtime_binding import setup_runtime


def setup(tmp_path, monkeypatch):
    runtime, lease, objects, calls = setup_runtime(tmp_path)
    monkeypatch.setattr(runtime, '_lease', lambda: lease)
    ref = {'id': 'test-auth', 'source': 'runtime_secret_ref', 'secret_name': 'test-secret',
           'secret_uid': 'test-secret-uid', 'principal_id': 'test-principal',
           'header_keys': {'Authorization': 'authorization-header'}}
    secret = {'metadata': {'name': 'test-secret', 'namespace': 'test-ns', 'uid': 'test-secret-uid'},
              'data': {'authorization-header': base64.b64encode(b'Bearer synthetic-test-only').decode()}}
    provider = runtime.manager.providers.get('test')
    original = provider._json
    queries = []
    def query(plan, args, **kwargs):
        queries.append(args)
        if 'secret' in args:
            return deepcopy(secret), None
        return original(plan, args, **kwargs)
    monkeypatch.setattr(provider, '_json', query)
    return runtime, ref, secret, queries


def test_exact_secret_reference_and_value_free_audit(tmp_path, monkeypatch):
    runtime, ref, secret, queries = setup(tmp_path, monkeypatch)
    resolver = SecretHeaders(runtime, [ref])
    assert resolver('test-auth') == {'Authorization': 'Bearer synthetic-test-only'}
    assert [q for q in queries if 'secret' in q] == [['-n', 'test-ns', 'get', 'secret', 'test-secret']]
    assert 'Bearer' not in str(resolver.audit)
    assert resolver.audit['test-auth']['secret_uid'] == 'test-secret-uid'
    resolver.audit.clear()
    assert resolver.audit


@pytest.mark.parametrize('mutation', [
    lambda s: s['metadata'].update(uid='replacement'),
    lambda s: s['metadata'].update(namespace='foreign'),
    lambda s: s['data'].update({'authorization-header': 'invalid base64'}),
    lambda s: s['data'].clear(),
    lambda s: s['data'].update({'authorization-header': base64.b64encode(b'Bearer x\r\nHost: evil').decode()}),
])
def test_changed_secret_or_invalid_headers_fail_closed(tmp_path, monkeypatch, mutation):
    runtime, ref, secret, queries = setup(tmp_path, monkeypatch)
    mutation(secret)
    with pytest.raises(ValueError):
        SecretHeaders(runtime, [ref])('test-auth')


def test_principal_mismatch_prevents_secret_read(tmp_path, monkeypatch):
    runtime, ref, secret, queries = setup(tmp_path, monkeypatch)
    ref['principal_id'] = 'foreign'
    with pytest.raises(ValueError, match='principal differs'):
        SecretHeaders(runtime, [ref])('test-auth')
    assert not any('secret' in q for q in queries)


def test_reserved_header_and_alias_mutation_rejected(tmp_path, monkeypatch):
    runtime, ref, secret, queries = setup(tmp_path, monkeypatch)
    resolver = SecretHeaders(runtime, [ref])
    ref['header_keys'] = {'Host': 'authorization-header'}
    assert set(resolver('test-auth')) == {'Authorization'}
    with pytest.raises(ValueError, match='authentication header'):
        SecretHeaders(runtime, [ref])
