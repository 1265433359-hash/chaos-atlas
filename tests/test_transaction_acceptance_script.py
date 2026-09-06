import json

import pytest

from chaosatlas.oracles.replay import HttpObservation, ResponseLost, UrllibHttpTransport
from scripts.run_transaction_oracle_acceptance import (
    AfterFirstWriteTransport,
    _finalize_transaction,
    _load_fixtures,
    _scenario_transport,
)


def test_external_byte_fixture_reference_is_loaded_without_entering_contract(tmp_path):
    payload = tmp_path / 'synthetic.png'
    payload.write_bytes(b'not-a-real-image-but-bounded-for-loader-test')
    manifest = tmp_path / 'fixtures.json'
    manifest.write_text(json.dumps({
        'synthetic_png': {'source': 'file', 'path': 'synthetic.png'},
        'fixture_sha256': 'synthetic-test-only',
    }), encoding='utf-8')
    result = _load_fixtures(
        manifest,
        {'synthetic_png': {'type': 'bytes', 'max_length': 1024},
         'fixture_sha256': {'type': 'string', 'max_length': 64}},
        tmp_path / 'repository',
    )
    assert result['synthetic_png'] == payload.read_bytes()
    assert result['fixture_sha256'] == 'synthetic-test-only'


@pytest.mark.parametrize('descriptor', [
    'plain-path-is-not-accepted',
    {'source': 'inline', 'path': 'synthetic.png'},
    {'source': 'file', 'path': 'synthetic.png', 'value': 'hidden'},
])
def test_byte_fixture_rejects_ambiguous_or_inline_material(tmp_path, descriptor):
    (tmp_path / 'synthetic.png').write_bytes(b'x')
    manifest = tmp_path / 'fixtures.json'
    manifest.write_text(json.dumps({'payload': descriptor}), encoding='utf-8')
    with pytest.raises(ValueError):
        _load_fixtures(manifest, {'payload': {'type': 'bytes', 'max_length': 10}}, tmp_path / 'repository')


def test_prepare_failure_reuses_completed_cleanup_instead_of_calling_it_twice():
    completed = {'status': 'cleaned', 'cleanup_confirmed': True, 'environment_released': True}

    class Workflow:
        def cleanup_fixture(self, _context):
            raise AssertionError('cleanup must not be repeated')

    replay = type('Replay', (), {'_run_id': 'run-test'})()
    assert _finalize_transaction(Workflow(), replay, 'run-test', {'cleanup': completed}) is completed


class StubLiveTransport(UrllibHttpTransport):
    def __init__(self):
        super().__init__('http://127.0.0.1:12345')
        self.calls = []

    def send(self, **kwargs):
        self.calls.append(kwargs)
        return HttpObservation(201, b'{"id":"real-response"}')


def test_post_response_action_runs_once_and_only_after_a_real_write_response():
    delegate = StubLiveTransport()
    actions = []
    transport = AfterFirstWriteTransport(
        delegate, lambda request, response: actions.append((request['path'], response.status)),
    )

    get = dict(method='GET', path='/read', query={}, json_body=None, multipart={}, headers={}, timeout_s=1)
    post = dict(method='POST', path='/write', query={}, json_body={}, multipart={}, headers={}, timeout_s=1)
    assert transport.send(**get).status == 201
    assert transport.send(**post).status == 201
    assert transport.send(**post).status == 201
    assert actions == [('/write', 201)]
    assert len(delegate.calls) == 3


def test_response_loss_scenario_discards_one_complete_response_without_server_fault(tmp_path):
    delegate = StubLiveTransport()
    events = []
    transport = _scenario_transport(
        delegate, scenario='response-loss', run_id='run-test', journal=events.append,
        evidence_root=tmp_path, crash_marker=None,
    )
    request = dict(method='POST', path='/write', query={}, json_body={}, multipart={}, headers={}, timeout_s=1)

    with pytest.raises(ResponseLost, match='discarded one complete real response'):
        transport.send(**request)

    assert len(delegate.calls) == 1
    assert events[0]['event'] == 'client_response_discarded'
    assert events[0]['response_status'] == 201
    assert events[0]['server_fault_injection_performed'] is False
