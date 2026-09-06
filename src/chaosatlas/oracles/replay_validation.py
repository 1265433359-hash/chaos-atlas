"""Strict v3 executable DSL validation; historical contracts remain audit data."""

from __future__ import annotations

import json
import math
import re
from typing import Any

V3_SCHEMA = 'chaosatlas-transaction-oracle-v3'
INTERPRETER = 'transaction-http-3.0'
NAME = re.compile(r'[a-zA-Z][a-zA-Z0-9_-]{0,63}')
PATH = re.compile(r'\$(?:\.[A-Za-z_][A-Za-z0-9_-]*|\[(?:0|[1-9][0-9]*)\])*')
VARIABLE = re.compile(r'\{([A-Za-z][A-Za-z0-9_-]*)\}')
RESERVED = {'run_id', 'lease_id', 'principal_id', 'attempt_id'}
TOP = set('schema_version oracle_id project_id project_revision status evidence_sources credential_refs allowed_requests steps assertions ownership cleanup approval contract_sha256 timeouts probe_steps interpreter_version inputs runtime_scope probe_assertions'.split())
STEP = set('id request_id json_body multipart query path_variables capture success on_response_loss ownership required_variables acceptable_statuses absence precondition'.split())
CHECK = set('id operator path expected expected_from assertion_ref step_id'.split())
OPERATORS = {'status_equals', 'status_in', 'json_path_equals', 'json_path_exists', 'sha256_equals', 'count_equals', 'body_contains', 'eventually'}


def variables_in(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set().union(*(variables_in(item) for item in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(variables_in(item) for item in value)) if value else set()
    return set(VARIABLE.findall(value)) if isinstance(value, str) else set()


def validate_v3(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    def reject(message: str) -> None:
        errors.append(message)

    def fields(value: Any, allowed: set[str], label: str) -> bool:
        if not isinstance(value, dict):
            reject(f'{label}: object required')
            return False
        if set(value) - allowed:
            reject(f'{label}: unknown fields: ' + ','.join(sorted(set(value) - allowed)))
        return True

    def ids(items: Any, label: str) -> set[str]:
        if not isinstance(items, list) or not items or len(items) > 64:
            reject(f'{label}: bounded nonempty list required')
            return set()
        result: set[str] = set()
        for item in items:
            identifier = item.get('id') if isinstance(item, dict) else None
            if not isinstance(identifier, str) or not NAME.fullmatch(identifier) or identifier in result:
                reject(f'{label}: invalid or duplicate ID')
            else:
                result.add(identifier)
        return result

    def path(value: Any) -> None:
        if not isinstance(value, str) or len(value) > 512 or not PATH.fullmatch(value):
            reject('invalid JSON path')

    def checks(items: Any, available: set[str], label: str) -> None:
        ids(items, label)
        seen: set[str] = set()
        for item in items if isinstance(items, list) else []:
            if not fields(item, CHECK, label):
                continue
            op = item.get('operator')
            if op not in OPERATORS:
                reject(f'{label}: unknown operator')
            if op in {'json_path_equals', 'json_path_exists', 'count_equals'}:
                path(item.get('path'))
            if op not in {'json_path_exists', 'eventually'} and (('expected' in item) == ('expected_from' in item)):
                reject(f'{label}: exactly one expected value source required')
            if 'expected_from' in item and item['expected_from'] not in available:
                reject(f'{label}: undefined expected variable')
            if variables_in(item.get('expected')) - available:
                reject(f'{label}: undefined expected template variable')
            if op == 'eventually' and item.get('assertion_ref') not in seen:
                reject(f'{label}: invalid assertion dependency')
            if op == 'status_in' and (not isinstance(item.get('expected'), list) or not item['expected'] or any(type(x) is not int or not 100 <= x <= 599 for x in item['expected'])):
                reject(f'{label}: invalid expected status list')
            seen.add(str(item.get('id')))

    try:
        encoded = json.dumps(contract, allow_nan=False)
        if len(encoded.encode()) > 262144:
            reject('contract exceeds size limit')
    except (ValueError, TypeError):
        reject('contract requires finite JSON values')
    fields(contract, TOP, 'contract')
    if contract.get('interpreter_version') != INTERPRETER:
        reject('incompatible transaction interpreter')
    scope = contract.get('runtime_scope')
    if fields(scope, {'mode', 'service', 'source_revision', 'image_digest'}, 'runtime_scope'):
        if scope.get('mode') not in {'dedicated', 'disposable'} or not scope.get('service') or not scope.get('source_revision'):
            reject('runtime_scope requires mode, service and source revision')
    inputs = contract.get('inputs')
    available = set(RESERVED)
    if isinstance(inputs, dict):
        for name, spec in inputs.items():
            if not NAME.fullmatch(name) or name in RESERVED:
                reject('invalid or reserved input name')
            if fields(spec, {'type', 'max_length', 'minimum', 'maximum'}, 'input'):
                if spec.get('type') not in {'string', 'integer', 'number', 'boolean', 'bytes'}:
                    reject('invalid input type')
                if spec.get('type') in {'string', 'bytes'} and (type(spec.get('max_length')) is not int or not 1 <= spec['max_length'] <= 4194304):
                    reject('input requires bounded length')
                if spec.get('type') in {'number', 'integer'}:
                    if any(type(spec.get(k)) not in {int, float} or not math.isfinite(spec[k]) for k in ('minimum', 'maximum')):
                        reject('numeric input requires finite bounds')
                    elif spec['minimum'] > spec['maximum']:
                        reject('invalid numeric input range')
            available.add(name)
    else:
        reject('inputs must be declared')
    timeouts = contract.get('timeouts')
    if fields(timeouts, {'request_s', 'eventual_s', 'poll_interval_s'}, 'timeouts'):
        for key, limit in [('request_s', 30), ('eventual_s', 120), ('poll_interval_s', 10)]:
            value = timeouts.get(key)
            if type(value) not in {float, int} or not math.isfinite(value) or not 0 < value <= limit:
                reject(f'invalid bounded timeout: {key}')

    requests = contract.get('allowed_requests')
    request_ids = ids(requests, 'requests')
    request_map = {x['id']: x for x in requests if isinstance(x, dict) and 'id' in x} if isinstance(requests, list) else {}
    for item in request_map.values():
        fields(item, {'id', 'method', 'path', 'effect'}, 'request')
        if item.get('effect') not in {'read', 'write'} or item.get('method') not in {'GET', 'POST', 'PUT', 'PATCH', 'DELETE'}:
            reject('request requires explicit effect and method')
        p = item.get('path', '')
        if not isinstance(p, str) or not p.startswith('/') or any(x in p for x in ('//', '\\', '?', '#', '%', '..', '://')) or any(ord(x) < 33 for x in p):
            reject('unsafe request path template')
        elif '{' in VARIABLE.sub('segment', p) or '}' in VARIABLE.sub('segment', p):
            reject('invalid request path placeholder')

    def validate_step(step: Any, known: set[str], label: str) -> set[str]:
        if not fields(step, STEP, label):
            return set()
        if step.get('request_id') not in request_ids:
            reject(f'{label}: request outside allow-list')
        if 'json_body' in step and 'multipart' in step:
            reject(f'{label}: conflicting request bodies')
        refs = variables_in({k: step[k] for k in ('json_body', 'query', 'multipart', 'path_variables') if k in step})
        refs |= variables_in(request_map.get(step.get('request_id'), {}).get('path'))
        if refs - known:
            reject(f'{label}: undefined or forward variable')
        success = step.get('success')
        if fields(success, {'statuses', 'checks'}, f'{label}.success'):
            statuses = success.get('statuses')
            if not isinstance(statuses, list) or not statuses or any(type(s) is not int or not 100 <= s <= 599 for s in statuses):
                reject(f'{label}: bounded success statuses required')
            if 'checks' in success:
                checks(success['checks'], known, f'{label}.checks')
        captures = step.get('capture', {})
        if not isinstance(captures, dict):
            reject(f'{label}: capture object required')
            return set()
        for name, capture in captures.items():
            if name in known or not NAME.fullmatch(name):
                reject(f'{label}: capture shadows existing variable')
            if fields(capture, {'path', 'type', 'max_length'}, 'capture'):
                path(capture.get('path'))
                if capture.get('type') != 'string' or type(capture.get('max_length')) is not int or not 1 <= capture['max_length'] <= 256:
                    reject('capture must be bounded string identity')
        return set(captures)

    steps = contract.get('steps')
    step_ids = ids(steps, 'steps')
    for step in steps if isinstance(steps, list) else []:
        available |= validate_step(step, available, 'step')
    checks(contract.get('assertions'), available, 'assertions')
    checks(contract.get('probe_assertions'), available, 'probe_assertions')
    step_map = {x['id']: x for x in steps if isinstance(x, dict) and 'id' in x} if isinstance(steps, list) else {}
    probe = contract.get('probe_steps')
    if not isinstance(probe, list) or not probe or len(set(probe)) != len(probe) or set(probe) - step_ids:
        reject('invalid probe step IDs')
        probe = []
    for identifier in probe:
        step = step_map[identifier]
        if request_map.get(step.get('request_id'), {}).get('effect') != 'read' or step.get('capture'):
            reject('probe requires read-only steps without capture')
    for item in contract.get('probe_assertions', []):
        if isinstance(item, dict) and item.get('step_id') not in probe:
            reject('probe assertion must use this phase fresh observation')
    cleanup = contract.get('cleanup')
    if fields(cleanup, {'strategy', 'on_every_exit', 'environment_release_required', 'steps', 'reason'}, 'cleanup'):
        for step in cleanup.get('steps', []):
            validate_step(step, available, 'cleanup step')
    return sorted(set(errors))
