"""V3 protocol tests use synthetic-test-only contracts, never real approvals."""

from copy import deepcopy
import pytest

from chaosatlas.oracles.replay_validation import INTERPRETER, V3_SCHEMA, validate_v3


def contract():
    read = {'id': 'read', 'request_id': 'read', 'success': {'statuses': [200]}}
    check = {'id': 'value', 'step_id': 'read', 'operator': 'json_path_equals', 'path': '$.value', 'expected': 1}
    return {
        'schema_version': V3_SCHEMA, 'interpreter_version': INTERPRETER,
        'inputs': {}, 'runtime_scope': {'mode': 'dedicated', 'service': 'synthetic', 'source_revision': 'synthetic-test-only'},
        'timeouts': {'request_s': 10, 'eventual_s': 30, 'poll_interval_s': 1},
        'allowed_requests': [{'id': 'read', 'method': 'GET', 'path': '/objects', 'effect': 'read'}],
        'steps': [read], 'probe_steps': ['read'], 'assertions': [check], 'probe_assertions': [deepcopy(check)],
        'cleanup': {'strategy': 'exact_owned_ids', 'on_every_exit': True, 'steps': []},
    }


def test_v3_valid_minimal_protocol():
    assert validate_v3(contract()) == []


@pytest.mark.parametrize('mutation', [
    lambda c: c.update(shell='hidden command'),
    lambda c: c['steps'][0].update(python='hidden expression'),
    lambda c: c['allowed_requests'].append(deepcopy(c['allowed_requests'][0])),
    lambda c: c['steps'].append(deepcopy(c['steps'][0])),
    lambda c: c['assertions'][0].update(path='$.value trailing'),
    lambda c: c['assertions'][0].update(expected_from='undefined'),
    lambda c: c['steps'][0].update(query={'q': '{not_yet_captured}'}),
    lambda c: c['steps'][0].update(capture={'run_id': {'path': '$.id', 'type': 'string', 'max_length': 20}}),
    lambda c: c['timeouts'].update(poll_interval_s=0),
    lambda c: c['timeouts'].update(eventual_s=float('nan')),
    lambda c: c['timeouts'].update(request_s=float('inf')),
    lambda c: c['probe_assertions'][0].update(step_id='old-prepare-step'),
    lambda c: c.update(interpreter_version='transaction-http-4.0'),
    lambda c: c['allowed_requests'][0].update(path='/objects/{bad}/../foreign'),
])
def test_v3_rejects_unreviewable_execution(mutation):
    value = contract()
    mutation(value)
    assert validate_v3(value)
