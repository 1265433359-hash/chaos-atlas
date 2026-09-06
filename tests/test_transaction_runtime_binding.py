"""Synthetic control-plane identity tests, not application acceptance."""

from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from chaosatlas.isolation.manager import IsolationManager
from chaosatlas.isolation.contracts import with_hash
from chaosatlas.isolation.providers import KubernetesIsolationProvider, ProviderRegistry
from chaosatlas.oracles.runtime_binding import LeaseRuntime


def setup_runtime(tmp_path):
    from chaosatlas.isolation.lease_store import LeaseStore
    objects = {
        'cluster': {'metadata': {'uid': 'cluster-uid'}},
        'namespace': {'metadata': {'uid': 'namespace-uid'}},
        'service': {'metadata': {'uid': 'service-uid'}, 'spec': {'ports': [{'port': 80}], 'selector': {'app': 'test'}}},
    }
    calls = []
    def runner(args, **kwargs):
        calls.append(args)
        assert args[:2] == ['--context', 'synthetic-context']
        key = 'cluster' if 'kube-system' in args else 'service' if 'service' in args else 'namespace'
        return 0, json.dumps(objects[key]), ''
    provider = KubernetesIsolationProvider(name='test', level='L1', runner=runner)
    manager = IsolationManager(store=LeaseStore(tmp_path), providers=ProviderRegistry([provider]))
    runtime = LeaseRuntime(manager, 'lease-test', service='test-service', port=80,
                           principal_id='test-principal', project_revision='test-revision')
    lease = {'provider': 'test', 'plan': {'mode': 'adopted-test-replica', 'source_namespace': 'test-ns'},
             'runtime_locator': {'kube_context': 'synthetic-context', 'cluster_uid': 'cluster-uid'},
             'resources': [{'kind': 'Namespace', 'name': 'test-ns', 'actual_uid': 'namespace-uid'}]}
    return runtime, lease, objects, calls


def test_identity_uses_provider_context_and_pins_uids(tmp_path):
    runtime, lease, objects, calls = setup_runtime(tmp_path)
    result = runtime._read_identity(lease)
    assert result['namespace_uid'] == 'namespace-uid'
    assert result['service_uid'] == 'service-uid'
    assert len(calls) == 3
    assert not hasattr(runtime, 'claim_scope')


@pytest.mark.parametrize('mutation', [
    lambda l, o: o['cluster']['metadata'].update(uid='replacement'),
    lambda l, o: o['namespace']['metadata'].update(uid='replacement'),
    lambda l, o: l.update(resources=[]),
    lambda l, o: l['resources'].append(deepcopy(l['resources'][0])),
    lambda l, o: o['service']['spec'].update(type='ExternalName'),
    lambda l, o: o['service']['spec'].update(ports=[{'port': 81}]),
    lambda l, o: o['service']['metadata'].update(uid=''),
])
def test_runtime_rejects_out_of_lease_targets(tmp_path, mutation):
    runtime, lease, objects, calls = setup_runtime(tmp_path)
    mutation(lease, objects)
    with pytest.raises(ValueError):
        runtime._read_identity(lease)


def test_adopted_release_never_proves_destruction(tmp_path, monkeypatch):
    runtime, lease, objects, calls = setup_runtime(tmp_path)
    monkeypatch.setattr(runtime, '_lease', lambda: lease)
    with pytest.raises(ValueError, match='adopted release'):
        runtime.release()


def test_disposable_release_reads_the_matching_verified_cleanup_audit(tmp_path, monkeypatch):
    runtime, lease, objects, calls = setup_runtime(tmp_path)
    lease['plan']['mode'] = 'ephemeral-target'
    monkeypatch.setattr(runtime, '_lease', lambda: lease)
    released = {'cleanup_attempts': 2}
    monkeypatch.setattr(runtime.manager, 'release', lambda lease_id: released)
    audit = with_hash({
        'schema_version': 'chaosatlas-isolation-audit-v1',
        'lease_id': 'lease-test', 'status': 'cleanup_verified',
        'checked_at': '2026-09-06T00:00:00+00:00', 'checks': {}, 'errors': [],
    }, 'audit_sha256')
    path = runtime.manager.store.audits / 'lease-test' / 'cleanup-2.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(audit), encoding='utf-8')
    assert runtime.release() == audit


def test_disposable_release_rejects_missing_or_unverified_cleanup_audit(tmp_path, monkeypatch):
    runtime, lease, objects, calls = setup_runtime(tmp_path)
    lease['plan']['mode'] = 'ephemeral-target'
    monkeypatch.setattr(runtime, '_lease', lambda: lease)
    monkeypatch.setattr(runtime.manager, 'release', lambda lease_id: {'cleanup_attempts': 1})
    with pytest.raises(ValueError, match='audit is unavailable'):
        runtime.release()


def test_target_change_after_open_is_rejected(tmp_path, monkeypatch):
    runtime, lease, objects, calls = setup_runtime(tmp_path)
    monkeypatch.setattr(runtime, '_lease', lambda: lease)
    runtime._binding = {**runtime._read_identity(lease), 'origin': 'http://127.0.0.1:12345'}
    runtime._tunnel = SimpleNamespace(poll=lambda: None)
    objects['service']['metadata']['uid'] = 'replacement'
    with pytest.raises(ValueError, match='target changed'):
        runtime.verify({'service': 'test-service', 'mode': 'dedicated'}, SimpleNamespace(base_url=runtime.binding['origin']))


def test_selected_image_is_verified_and_selector_change_rejected(tmp_path, monkeypatch):
    runtime, lease, objects, calls = setup_runtime(tmp_path)
    monkeypatch.setattr(runtime, '_lease', lambda: lease)
    runtime._binding = {**runtime._read_identity(lease), 'origin': 'http://127.0.0.1:12345'}
    runtime._tunnel = SimpleNamespace(poll=lambda: None)
    provider = runtime.manager.providers.get('test')
    original = provider._json
    image = ['sha256:' + 'a' * 64]
    def query(plan, args, **kwargs):
        if 'pods' in args:
            assert args[-2:] == ['-l', 'app=test']
            return {'items': [{'status': {'containerStatuses': [{'ready': True, 'imageID': image[0]}]}}]}, None
        return original(plan, args, **kwargs)
    monkeypatch.setattr(provider, '_json', query)
    scope = {'service': 'test-service', 'mode': 'dedicated', 'image_digest': image[0]}
    transport = SimpleNamespace(base_url=runtime.binding['origin'])
    assert runtime.verify(scope, transport) == runtime.binding
    image[0] = 'sha256:' + 'b' * 64
    with pytest.raises(ValueError, match='approved ready image'):
        runtime.verify(scope, transport)
    image[0] = scope['image_digest']
    objects['service']['spec']['selector']['app'] = 'foreign'
    with pytest.raises(ValueError, match='target changed'):
        runtime.verify(scope, transport)


def test_disposable_runtime_binds_principal_from_lease_owned_secret(tmp_path, monkeypatch):
    runtime, lease, objects, calls = setup_runtime(tmp_path)
    lease['plan']['mode'] = 'ephemeral-target'
    lease['target_name'] = 'test-ns'
    lease['owner_labels'] = {'chaosatlas.dev/lease-id': 'lease-test'}
    lease['resources'].append({
        'kind': 'Secret', 'namespace': 'test-ns', 'name': 'test-auth',
        'actual_uid': 'secret-uid', 'cleanup_policy': 'namespace',
    })
    runtime.principal_id = None
    monkeypatch.setattr(runtime, '_lease', lambda: lease)
    provider = runtime.manager.providers.get('test')
    original = provider._json
    def query(plan, args, **kwargs):
        if 'secret' in args:
            return {'metadata': {
                'name': 'test-auth', 'namespace': 'test-ns', 'uid': 'secret-uid',
                'labels': deepcopy(lease['owner_labels']),
                'annotations': {
                    'chaosatlas.dev/principal-role': 'transaction-test-user',
                    'chaosatlas.dev/principal-id': 'runtime-user-id',
                },
            }}, None
        return original(plan, args, **kwargs)
    monkeypatch.setattr(provider, '_json', query)
    audit = runtime.bind_principal([{
        'id': 'test-auth', 'source': 'lease_owned_secret_ref', 'secret_name': 'test-auth',
        'principal_role': 'transaction-test-user',
        'header_keys': {'Authorization': 'authorization-header'},
    }])
    assert runtime.principal_id == 'runtime-user-id'
    assert audit == {
        'principal_id': 'runtime-user-id',
        'credential_bindings': [{
            'principal_role': 'transaction-test-user',
            'secret_name': 'test-auth', 'secret_uid': 'secret-uid',
        }],
    }


@pytest.mark.parametrize('mutation', [
    lambda lease, secret, refs: secret['metadata'].update(uid='replacement'),
    lambda lease, secret, refs: secret['metadata']['labels'].update({'chaosatlas.dev/lease-id': 'foreign'}),
    lambda lease, secret, refs: secret['metadata']['annotations'].update({'chaosatlas.dev/principal-role': 'admin'}),
    lambda lease, secret, refs: lease.update(resources=[]),
    lambda lease, secret, refs: refs.append({
        'id': 'other', 'source': 'lease_owned_secret_ref', 'secret_name': 'other-auth',
        'principal_role': 'transaction-test-user',
        'header_keys': {'X-Api-Key': 'api-key'},
    }),
])
def test_disposable_runtime_rejects_untrusted_principal_binding(tmp_path, monkeypatch, mutation):
    runtime, lease, objects, calls = setup_runtime(tmp_path)
    lease['plan']['mode'] = 'ephemeral-target'
    lease['target_name'] = 'test-ns'
    lease['owner_labels'] = {'chaosatlas.dev/lease-id': 'lease-test'}
    lease['resources'].extend([
        {'kind': 'Secret', 'namespace': 'test-ns', 'name': 'test-auth', 'actual_uid': 'secret-uid'},
        {'kind': 'Secret', 'namespace': 'test-ns', 'name': 'other-auth', 'actual_uid': 'other-uid'},
    ])
    runtime.principal_id = None
    monkeypatch.setattr(runtime, '_lease', lambda: lease)
    refs = [{
        'id': 'test-auth', 'source': 'lease_owned_secret_ref', 'secret_name': 'test-auth',
        'principal_role': 'transaction-test-user',
        'header_keys': {'Authorization': 'authorization-header'},
    }]
    secrets = {
        'test-auth': {'metadata': {
            'name': 'test-auth', 'namespace': 'test-ns', 'uid': 'secret-uid',
            'labels': deepcopy(lease['owner_labels']),
            'annotations': {'chaosatlas.dev/principal-role': 'transaction-test-user',
                            'chaosatlas.dev/principal-id': 'runtime-user-id'},
        }},
        'other-auth': {'metadata': {
            'name': 'other-auth', 'namespace': 'test-ns', 'uid': 'other-uid',
            'labels': deepcopy(lease['owner_labels']),
            'annotations': {'chaosatlas.dev/principal-role': 'transaction-test-user',
                            'chaosatlas.dev/principal-id': 'different-user-id'},
        }},
    }
    mutation(lease, secrets['test-auth'], refs)
    provider = runtime.manager.providers.get('test')
    monkeypatch.setattr(provider, '_json', lambda plan, args, **kwargs: (
        deepcopy(secrets[args[-1]]), None
    ) if 'secret' in args else (deepcopy(objects['namespace']), None))
    with pytest.raises(ValueError):
        runtime.bind_principal(refs)
