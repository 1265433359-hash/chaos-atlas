"""V3 session interpreter used by the public transaction replayer.

No candidate selection, fault execution or project-specific endpoint lives here.
"""

from __future__ import annotations

from copy import deepcopy
import math
import time
import uuid
from typing import Any

from chaosatlas.isolation.contracts import SAFE_ID, canonical_hash
from chaosatlas.oracles.ownership import OwnershipUncertain, select_owned
from chaosatlas.oracles.recovery_ledger import RecoveryLedger
from chaosatlas.oracles.replay import UrllibHttpTransport, render_path, validate_auth_headers
from chaosatlas.oracles.transaction_contracts import _json_path, evaluate_assertions, validate_transaction_contract


def render(value, variables):
    from chaosatlas.oracles.replay_validation import VARIABLE
    if isinstance(value, dict):
        return {k: render(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [render(v, variables) for v in value]
    if not isinstance(value, str):
        return value
    match = VARIABLE.fullmatch(value)
    if match:
        return deepcopy(variables[match.group(1)])
    return VARIABLE.sub(lambda m: str(variables[m.group(1)]), value)


class ReplaySession:
    """Exact-ownership protocol. Synthetic sessions never earn live claims."""

    def __init__(self, contract, transport, *, credential_headers, fixtures, runtime,
                 ledger: RecoveryLedger, journal, sleep=time.sleep, monotonic=time.monotonic,
                 synthetic_test_only=False):
        self._contract = deepcopy(contract)
        errors = validate_transaction_contract(self._contract)
        if errors or self._contract.get('status') != 'frozen':
            raise ValueError('v3 requires a valid frozen contract: ' + '; '.join(errors))
        if not callable(journal) or not isinstance(ledger, RecoveryLedger):
            raise ValueError('durable ledger and explicit evidence journal required')
        # Live credentials/runtime integration must land and be tested before this
        # interpreter is opened to application HTTP. A fake may not claim live.
        record = self._contract['approval']['record']
        if not synthetic_test_only or isinstance(transport, UrllibHttpTransport) or record.get('reviewer') != 'synthetic-test-only':
            raise ValueError('v3 live execution remains gated pending credential and runtime integration')
        self.transport, self.runtime, self.ledger, self.journal = transport, runtime, ledger, journal
        self._sleep, self._monotonic = sleep, monotonic
        self._fixtures = deepcopy(fixtures)
        specs = self._contract['inputs']
        if set(fixtures) != set(specs):
            raise ValueError('fixtures must exactly match declared ordinary inputs')
        for key, value in fixtures.items():
            spec = specs[key]
            types = {'string': str, 'integer': int, 'number': (int, float), 'boolean': bool, 'bytes': bytes}
            expected = types[spec['type']]
            valid = type(value) in expected if isinstance(expected, tuple) else type(value) is expected
            if not valid:
                raise ValueError('fixture type mismatch')
            if spec['type'] in {'string', 'bytes'} and len(value) > spec['max_length']:
                raise ValueError('fixture exceeds length limit')
            if spec['type'] in {'integer', 'number'} and (not math.isfinite(value) or not spec['minimum'] <= value <= spec['maximum']):
                raise ValueError('fixture outside finite bounds')
        self._headers = {}
        for reference in self._contract['credential_refs']:
            headers = credential_headers(reference['id'])
            validate_auth_headers(headers)
            if {k.lower() for k in headers} & {k.lower() for k in self._headers}:
                raise ValueError('duplicate resolved credential header')
            self._headers.update(headers)
        self._requests = {s['id']: s for s in self._contract['allowed_requests']}
        self._steps = {s['id']: s for s in self._contract['steps']}
        self._variables = {}
        self._observations = {}
        self._run_id = None

    @property
    def contract(self):
        return deepcopy(self._contract)

    @property
    def variables(self):
        return deepcopy(self._variables)

    def _binding(self):
        binding = self.runtime.verify(self._contract['runtime_scope'], self.transport)
        if binding['project_revision'] != self._contract['project_revision']:
            raise ValueError('contract revision differs from verified runtime')
        return binding

    def _emit(self, event, step, **fields):
        self.journal({'schema_version': 'chaosatlas-transaction-journal-v3', 'event': event,
                      'run_id': self._run_id, 'step_id': step['id'], **fields})

    def _send(self, step, deadline=None):
        self._binding()
        request = self._requests[step['request_id']]
        timeout = self._contract['timeouts']['request_s']
        if deadline is not None:
            timeout = min(timeout, deadline - self._monotonic())
        if timeout <= 0:
            raise TimeoutError('bounded phase deadline exhausted')
        path = render_path(request['path'], self._variables)
        self._emit('request', step, request_id=request['id'], method=request['method'], path_sha256=canonical_hash(path))
        observation = self.transport.send(method=request['method'], path=path,
            query=render(step.get('query', {}), self._variables),
            json_body=render(step.get('json_body'), self._variables),
            multipart=render(step.get('multipart', {}), self._variables),
            headers=dict(self._headers), timeout_s=timeout).as_assertion_value()
        if deadline is not None and self._monotonic() > deadline:
            raise TimeoutError('response arrived after phase deadline')
        self._emit('response', step, status=observation['status'], body_sha256=observation['body_sha256'])
        if observation['status'] not in step['success']['statuses']:
            raise ValueError('step success status not satisfied')
        checks = [{**c, 'step_id': step['id']} for c in step['success'].get('checks', [])]
        if checks and evaluate_assertions({'assertions': checks}, {step['id']: observation}, self._variables)['status'] != 'pass':
            raise ValueError('step success fields not satisfied')
        return observation

    def _read(self, step, assertions):
        checks = [c for c in assertions if c.get('step_id') == step['id']]
        if not any(c['operator'] == 'eventually' for c in checks):
            return self._send(step)
        direct = [c for c in checks if c['operator'] != 'eventually']
        deadline = self._monotonic() + self._contract['timeouts']['eventual_s']
        while True:
            observation = self._send(step, deadline)
            result = evaluate_assertions({'assertions': direct}, {step['id']: observation}, self._variables)
            if result['status'] == 'pass':
                return observation
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                raise TimeoutError('eventual assertion deadline exhausted')
            self._sleep(min(self._contract['timeouts']['poll_interval_s'], remaining))

    def _select(self, creator, identity=None, deadline=None):
        spec = creator['ownership']
        observation = self._send(spec['lookup'], deadline)
        return select_owned(observation['json'], spec['selection'], render(spec['match'], self._variables), expected_identity=identity)

    def _creator(self, step):
        return step if 'ownership' in step else self._steps[step['owned_operation']]

    def _write(self, step):
        creator = self._creator(step)
        spec = creator['ownership']
        if step is creator:
            if self._select(creator)['status'] != 'not_found':
                raise OwnershipUncertain('preexisting object does not grant deletion ownership')
            identity = None
        else:
            previous = self.ledger.load(self._run_id)['operations'][creator['id']]
            identity = previous['identity']
            if self._select(creator, identity)['status'] != 'owned':
                raise OwnershipUncertain('owned object missing before mutation')
        self.ledger.intent(self._run_id, step['id'], object_type=spec['object_type'],
                           marker_sha256=canonical_hash(render(spec['match'], self._variables)))
        self.ledger.transition(self._run_id, step['id'], 'outcome_unknown')
        observation = self._send(step)
        selected = self._select(creator, identity)
        if selected['status'] != 'owned':
            raise OwnershipUncertain('write ownership not confirmed')
        self.ledger.transition(self._run_id, step['id'], 'owned_confirmed', identity=selected['identity'], ownership_sha256=selected['evidence_sha256'])
        self._variables.update(selected['identity'])
        # Captures in the direct response must agree with authoritative lookup.
        # Missing/bad response still permits exact cleanup, never business pass.
        for name, capture in step.get('capture', {}).items():
            actual = _json_path(observation['json'], capture['path'])
            if type(actual) is not str or len(actual) > capture['max_length'] or actual != selected['identity'][name]:
                raise OwnershipUncertain('response capture contradicts exact lookup')
        return observation

    def prepare(self, *, run_id):
        if not isinstance(run_id, str) or not SAFE_ID.fullmatch(run_id):
            raise ValueError('invalid generated run identity')
        if self._run_id is not None and self._run_id != run_id and not self.ledger.cleanup_confirmed(self._run_id):
            raise ValueError('unresolved earlier transaction requires recovery before prepare')
        binding = self._binding()
        with self.ledger.operation(run_id):
            attempt = 'attempt-' + uuid.uuid4().hex
            self.ledger.create(run_id, attempt_id=attempt, contract_sha256=self._contract['contract_sha256'], binding=binding)
            self._run_id = run_id
            self._variables = {**self._fixtures, 'run_id': run_id, 'attempt_id': attempt,
                               'lease_id': binding['lease_id'], 'principal_id': binding['principal_id']}
            self._observations = {}
            try:
                for step in self._contract['steps']:
                    observation = self._write(step) if self._requests[step['request_id']]['effect'] == 'write' else self._read(step, self._contract['assertions'])
                    self._observations[step['id']] = observation
                result = evaluate_assertions(self._contract, self._observations, self._variables)
                if result['status'] != 'pass':
                    return {'status': 'oracle_failed', 'assertion_result': result['status'], 'cleanup': self._cleanup_locked()}
                return {'status': 'prepared', 'assertion_result': 'pass', 'claim_scope': 'synthetic_test_only'}
            except BaseException as exc:
                cleanup = self._cleanup_locked()
                if not isinstance(exc, Exception):
                    raise
                return {'status': 'prepare_failed', 'reason_code': type(exc).__name__, 'cleanup': cleanup}

    def probe(self, phase):
        if self._run_id is None:
            raise ValueError('prepare required')
        with self.ledger.operation(self._run_id):
            self.ledger.assert_binding(self._run_id, self._binding(), self._contract['contract_sha256'])
            observations = {}
            # Each phase gets fresh observations only, never preparation history.
            for identifier in self._contract['probe_steps']:
                observations[identifier] = self._read(self._steps[identifier], self._contract['probe_assertions'])
            result = evaluate_assertions({'assertions': self._contract['probe_assertions']}, observations, self._variables)
            return {**result, 'phase': phase, 'claim_scope': 'synthetic_test_only'}

    def _cleanup_locked(self):
        errors = []
        try:
            self.ledger.assert_binding(self._run_id, self._binding(), self._contract['contract_sha256'])
        except Exception as exc:
            return {'status': 'cleanup_failed', 'cleanup_confirmed': False,
                    'errors': [{'reason_code': type(exc).__name__}], 'environment_released': None}
        for cleanup in self._contract['cleanup']['steps']:
            creator = self._steps[cleanup['owned_operation']]
            operations = self.ledger.load(self._run_id)['operations']
            relevant = [key for key in operations if self._creator(self._steps[key])['id'] == creator['id']]
            if not relevant or all(operations[key]['state'] in {'not_sent', 'absent_confirmed'} for key in relevant):
                continue
            try:
                identity = operations[creator['id']].get('identity') or None
                selected = self._select(creator, identity)
                if selected['status'] == 'not_found' and not identity:
                    raise OwnershipUncertain('unknown commit cannot be cleared by one empty lookup')
                if selected['status'] == 'owned':
                    self._variables.update(selected['identity'])
                    for key in relevant:
                        state = operations[key]['state']
                        if state == 'intent_persisted':
                            self.ledger.transition(self._run_id, key, 'outcome_unknown')
                            state = 'outcome_unknown'
                        if state in {'outcome_unknown', 'cleanup_blocked'}:
                            self.ledger.transition(self._run_id, key, 'owned_confirmed', identity=selected['identity'], ownership_sha256=selected['evidence_sha256'])
                            state = 'owned_confirmed'
                        if state == 'owned_confirmed':
                            self.ledger.transition(self._run_id, key, 'cleanup_pending')
                    try:
                        self._send(cleanup)
                    except Exception:
                        # A delete response loss is resolved by a new absence
                        # read, not by blindly retrying the deletion.
                        pass
                    deadline = self._monotonic() + self._contract['timeouts']['eventual_s']
                    while True:
                        selected = self._select(creator, selected.get('identity') or identity, deadline)
                        if selected['status'] == 'not_found':
                            break
                        remaining = deadline - self._monotonic()
                        if remaining <= 0:
                            raise TimeoutError('object absence not confirmed')
                        self._sleep(min(self._contract['timeouts']['poll_interval_s'], remaining))
                for key in relevant:
                    if self.ledger.load(self._run_id)['operations'][key]['state'] not in {'absent_confirmed', 'not_sent'}:
                        self.ledger.transition(self._run_id, key, 'absent_confirmed', absence_sha256=selected['evidence_sha256'])
            except Exception as exc:
                errors.append({'operation_id': creator['id'], 'reason_code': type(exc).__name__})
        confirmed = self.ledger.cleanup_confirmed(self._run_id)
        if self._contract['cleanup'].get('environment_release_required'):
            confirmed = False
            errors.append({'reason_code': 'verified_environment_release_not_integrated'})
        return {'status': 'cleaned' if confirmed else 'cleanup_failed', 'cleanup_confirmed': confirmed,
                'environment_released': None, 'errors': errors, 'claim_scope': 'synthetic_test_only'}

    def cleanup(self):
        if self._run_id is None:
            return {'status': 'not_required', 'cleanup_confirmed': True}
        with self.ledger.operation(self._run_id):
            return self._cleanup_locked()

    def recover(self, *, run_id):
        with self.ledger.operation(run_id):
            value = self.ledger.rebind_local_tunnel(run_id, self._binding(), self._contract['contract_sha256'])
            self._run_id = run_id
            self._variables = {'run_id': run_id, 'attempt_id': value['attempt_id'],
                               'lease_id': value['binding']['lease_id'], 'principal_id': value['binding']['principal_id']}
            for entry in value['operations'].values():
                self._variables.update(entry.get('identity', {}))
            return self._cleanup_locked()
