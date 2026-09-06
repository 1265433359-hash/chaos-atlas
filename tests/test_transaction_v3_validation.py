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


def test_v3_accepts_bounded_exact_array_match():
    value = contract()
    value['assertions'][0] = {
        'id': 'owned-message', 'step_id': 'read',
        'operator': 'array_exactly_one_matches', 'path': '$.messages',
        'expected': {'$.rid': '{lease_id}', '$.u._id': '{principal_id}'},
    }
    value['probe_assertions'] = [deepcopy(value['assertions'][0])]
    assert validate_v3(value) == []


@pytest.mark.parametrize('expected', [{}, {'not-a-path': 'x'}, {'$.id': None}, {'$.id': {'nested': True}}])
def test_v3_rejects_unbounded_or_ambiguous_exact_array_match(expected):
    value = contract()
    value['assertions'][0] = {
        'id': 'owned-message', 'step_id': 'read',
        'operator': 'array_exactly_one_matches', 'path': '$.messages',
        'expected': expected,
    }
    value['probe_assertions'] = [deepcopy(value['assertions'][0])]
    assert validate_v3(value)


def test_v3_accepts_logical_lease_owned_credential_slot():
    value = contract()
    value['credential_refs'] = [{
        'id': 'test-auth', 'source': 'lease_owned_secret_ref',
        'secret_name': 'test-auth', 'principal_role': 'transaction-test-user',
        'header_keys': {'Authorization': 'authorization-header'},
    }]
    assert validate_v3(value) == []


@pytest.mark.parametrize('mutation', [
    lambda ref: ref.update(secret_uid='must-not-be-frozen'),
    lambda ref: ref.update(principal_id='must-not-be-frozen'),
    lambda ref: ref.update(source='runtime_secret_ref'),
    lambda ref: ref.update(header_keys={'Host': 'authorization-header'}),
    lambda ref: ref.update(header_keys={'Authorization': 'bad key'}),
])
def test_v3_rejects_unsafe_or_instance_pinned_lease_credential_slot(mutation):
    value = contract()
    ref = {
        'id': 'test-auth', 'source': 'lease_owned_secret_ref',
        'secret_name': 'test-auth', 'principal_role': 'transaction-test-user',
        'header_keys': {'Authorization': 'authorization-header'},
    }
    mutation(ref)
    value['credential_refs'] = [ref]
    assert validate_v3(value)


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


def write_contract():
    value = contract()
    value['allowed_requests'] += [
        {'id': 'create', 'method': 'POST', 'path': '/objects', 'effect': 'write'},
        {'id': 'delete', 'method': 'DELETE', 'path': '/objects/{object_id}', 'effect': 'write'},
    ]
    value['steps'].insert(0, {
        'id': 'create', 'request_id': 'create', 'json_body': {'marker': '{run_id}'},
        'capture': {'object_id': {'path': '$.id', 'type': 'string', 'max_length': 64}},
        'success': {'statuses': [201]}, 'on_response_loss': {'strategy': 'exact_lookup'},
        'ownership': {
            'object_type': 'test-object', 'preflight_absent': True,
            'marker_path': '$.marker', 'principal_path': '$.owner',
            'match': {'$.marker': '{run_id}', '$.owner': '{principal_id}'},
            'lookup': {'id': 'lookup', 'request_id': 'read', 'query': {'marker': '{run_id}'}, 'success': {'statuses': [200]}},
            'selection': {'collection_path': '$.items', 'max_items': 10,
                          'complete': {'path': '$.total', 'operator': 'total_equals_length'},
                          'identity': {'object_id': '$.id'}},
        },
    })
    value['cleanup']['steps'] = [{'id': 'cleanup', 'request_id': 'delete', 'owned_operation': 'create', 'success': {'statuses': [204]}}]
    return value


def test_reviewable_exact_write_contract():
    assert validate_v3(write_contract()) == []


def lease_exclusive_contract():
    value = contract()
    value['runtime_scope']['mode'] = 'disposable'
    value['allowed_requests'].append({'id': 'create', 'method': 'POST', 'path': '/objects', 'effect': 'write'})
    value['steps'].insert(0, {
        'id': 'create', 'request_id': 'create', 'json_body': {'marker': '{run_id}'},
        'capture': {'object_id': {'path': '$.id', 'type': 'string', 'max_length': 64}},
        'success': {'statuses': [201]},
        'on_response_loss': {'strategy': 'disposable_environment'},
        'ownership': {'mode': 'lease_exclusive', 'object_type': 'test-object', 'preflight_absent': True},
    })
    value['cleanup'] = {
        'strategy': 'disposable_environment', 'on_every_exit': True,
        'environment_release_required': True, 'steps': [],
        'reason': 'The synthetic-empty lease is the complete ownership and cleanup boundary.',
    }
    return value


def test_reviewable_lease_exclusive_write_contract():
    assert validate_v3(lease_exclusive_contract()) == []


def test_lease_exclusive_contract_accepts_followup_mutation_of_created_object():
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
    assert validate_v3(value) == []


@pytest.mark.parametrize('mutation', [
    lambda c: c['runtime_scope'].update(mode='dedicated'),
    lambda c: c['cleanup'].update(environment_release_required=False),
    lambda c: c['cleanup'].update(strategy='exact_owned_ids'),
    lambda c: c['steps'][0]['ownership'].update(preflight_absent=False),
    lambda c: c['steps'][0]['ownership'].update(match={'$.marker': '{run_id}'}),
])
def test_lease_exclusive_write_requires_disposable_release_boundary(mutation):
    value = lease_exclusive_contract()
    mutation(value)
    assert validate_v3(value)


@pytest.mark.parametrize('mutation', [
    lambda c: c['steps'][0].pop('ownership'),
    lambda c: c['steps'][0]['ownership'].update(preflight_absent=False),
    lambda c: c['steps'][0]['ownership']['match'].update({'$.owner': 'anonymous'}),
    lambda c: c['steps'][0]['ownership']['selection'].pop('complete'),
    lambda c: c['steps'][0]['ownership']['selection'].update(max_items=100000),
    lambda c: c['steps'][0]['ownership']['selection'].update(identity={'other_id': '$.id'}),
    lambda c: c['steps'][0]['ownership']['lookup'].update(request_id='delete'),
    lambda c: c['steps'][0]['ownership'].update(shell='hidden command'),
    lambda c: c['steps'][0]['on_response_loss'].update(strategy='retry_same_request'),
    lambda c: c['cleanup'].update(steps=[]),
    lambda c: c['cleanup']['steps'][0].update(owned_operation='foreign'),
    lambda c: c['cleanup']['steps'].append(deepcopy(c['cleanup']['steps'][0])),
    lambda c: c['cleanup'].update(strategy='disposable_environment', environment_release_required=True),
])
def test_write_ownership_and_cleanup_are_not_silently_ignored(mutation):
    value = write_contract()
    mutation(value)
    assert validate_v3(value)
