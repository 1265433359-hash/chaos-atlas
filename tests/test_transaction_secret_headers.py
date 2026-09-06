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


def lease_owned_setup(tmp_path, monkeypatch):
    runtime, lease, objects, calls = setup_runtime(tmp_path)
    lease['plan']['mode'] = 'ephemeral-target'
    lease['target_name'] = 'test-ns'
    lease['owner_labels'] = {
        'chaosatlas.dev/lease-id': 'lease-test',
        'chaosatlas.dev/managed': 'true',
        'chaosatlas.dev/project': 'synthetic',
    }
    lease['resources'].append({
        'kind': 'Secret', 'namespace': 'test-ns', 'name': 'test-secret',
        'actual_uid': 'runtime-secret-uid', 'cleanup_policy': 'namespace',
    })
    monkeypatch.setattr(runtime, '_lease', lambda: lease)
    ref = {
        'id': 'test-auth', 'source': 'lease_owned_secret_ref',
        'secret_name': 'test-secret', 'principal_role': 'transaction-test-user',
        'header_keys': {'Authorization': 'authorization-header'},
    }
    secret = {
        'metadata': {
            'name': 'test-secret', 'namespace': 'test-ns', 'uid': 'runtime-secret-uid',
            'labels': deepcopy(lease['owner_labels']),
            'annotations': {
                'chaosatlas.dev/principal-role': 'transaction-test-user',
                'chaosatlas.dev/principal-id': 'test-principal',
            },
        },
        'data': {'authorization-header': base64.b64encode(b'Bearer synthetic-test-only').decode()},
    }
    provider = runtime.manager.providers.get('test')
    original = provider._json
    queries = []
    def query(plan, args, **kwargs):
        queries.append(args)
        if 'secret' in args:
            return deepcopy(secret), None
        return original(plan, args, **kwargs)
    monkeypatch.setattr(provider, '_json', query)
    return runtime, lease, ref, secret, queries


def test_lease_owned_secret_binds_dynamic_uid_and_principal(tmp_path, monkeypatch):
    runtime, lease, ref, secret, queries = lease_owned_setup(tmp_path, monkeypatch)
    resolver = SecretHeaders(runtime, [ref])
    assert resolver('test-auth') == {'Authorization': 'Bearer synthetic-test-only'}
    assert resolver.audit['test-auth'] == {
        'secret_name': 'test-secret', 'secret_uid': 'runtime-secret-uid',
        'namespace_uid': 'namespace-uid', 'principal_id': 'test-principal',
        'principal_role': 'transaction-test-user', 'key_names': ['authorization-header'],
        'binding_source': 'lease_owned_secret_ref',
    }


@pytest.mark.parametrize('mutation', [
    lambda lease, secret: secret['metadata'].update(namespace='foreign'),
    lambda lease, secret: secret['metadata'].update(uid='replacement'),
    lambda lease, secret: secret['data'].update(extra=base64.b64encode(b'extra').decode()),
    lambda lease, secret: secret['metadata']['annotations'].update({'chaosatlas.dev/principal-id': 'foreign'}),
    lambda lease, secret: secret['metadata']['labels'].update({'chaosatlas.dev/lease-id': 'foreign'}),
    lambda lease, secret: lease['resources'].clear(),
])
def test_lease_owned_secret_rejects_foreign_replacement_or_ambiguous_identity(
    tmp_path, monkeypatch, mutation,
):
    runtime, lease, ref, secret, queries = lease_owned_setup(tmp_path, monkeypatch)
    mutation(lease, secret)
    with pytest.raises(ValueError):
        SecretHeaders(runtime, [ref])('test-auth')


def test_lease_owned_secret_is_not_valid_for_adopted_namespace(tmp_path, monkeypatch):
    runtime, lease, ref, secret, queries = lease_owned_setup(tmp_path, monkeypatch)
    lease['plan']['mode'] = 'adopted-test-replica'
    with pytest.raises(ValueError, match='disposable lease'):
        SecretHeaders(runtime, [ref])('test-auth')
