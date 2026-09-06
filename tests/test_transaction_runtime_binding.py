"""Synthetic control-plane identity tests, not application acceptance."""

from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from chaosatlas.isolation.manager import IsolationManager
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
