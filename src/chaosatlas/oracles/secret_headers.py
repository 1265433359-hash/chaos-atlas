"""Resolve only explicitly referenced Secret keys in a verified lease namespace."""

from __future__ import annotations

import base64
from copy import deepcopy
import re

from chaosatlas.oracles.replay import validate_auth_headers
from chaosatlas.oracles.runtime_binding import LeaseRuntime


class SecretHeaders:
    """No credential persistence, shell arguments, bulk reads, or raw errors."""

    def __init__(self, runtime: LeaseRuntime, references: list[dict]):
        if not isinstance(runtime, LeaseRuntime):
            raise ValueError('Secret headers require a public lease runtime')
        self.runtime = runtime
        self._references = {}
        self._audit = {}
        for ref in deepcopy(references):
            exact = set(ref) == {'id', 'source', 'secret_name', 'secret_uid', 'principal_id', 'header_keys'} and ref.get('source') == 'runtime_secret_ref'
            lease_owned = set(ref) == {'id', 'source', 'secret_name', 'principal_role', 'header_keys'} and ref.get('source') == 'lease_owned_secret_ref'
            if not exact and not lease_owned:
                raise ValueError('exact or lease-owned Secret reference required')
            if not isinstance(ref['id'], str) or ref['id'] in self._references:
                raise ValueError('duplicate or invalid credential reference')
            if not isinstance(ref['secret_name'], str) or not re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,252}', ref['secret_name']):
                raise ValueError('unsafe Secret name')
            if exact and (not isinstance(ref['secret_uid'], str) or not ref['secret_uid'] or len(ref['secret_uid']) > 128):
                raise ValueError('Secret UID pin required')
            if not isinstance(ref['header_keys'], dict) or not ref['header_keys']:
                raise ValueError('explicit authentication header keys required')
            validate_auth_headers({k: 'validation-only' for k in ref['header_keys']})
            for key in ref['header_keys'].values():
                if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,253}', key):
                    raise ValueError('unsafe Secret data key')
            if lease_owned and (not isinstance(ref['principal_role'], str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', ref['principal_role'])):
                raise ValueError('safe logical principal role required')
            self._references[ref['id']] = ref

    @property
    def audit(self):
        return deepcopy(self._audit)

    def __call__(self, reference_id):
        ref = self._references[reference_id]
        lease = self.runtime._lease()
        binding = self.runtime._read_identity(lease)
        lease_owned = ref['source'] == 'lease_owned_secret_ref'
        if lease_owned:
            if lease['plan'].get('mode') == 'adopted-test-replica':
                raise ValueError('lease-owned credentials require a disposable lease')
        elif ref['principal_id'] != binding['principal_id']:
            raise ValueError('Secret reference principal differs from runtime')
        provider = self.runtime.manager.providers.get(lease['provider'])
        value, error = provider._json(lease['plan'], ['-n', binding['namespace'], 'get', 'secret', ref['secret_name']], lease=lease)
        if error or not isinstance(value, dict):
            raise ValueError('referenced Secret unavailable')
        metadata = value.get('metadata') or {}
        if lease_owned:
            registered = [item for item in lease.get('resources') or []
                          if item.get('kind') == 'Secret'
                          and item.get('namespace') == binding['namespace']
                          and item.get('name') == ref['secret_name']]
            labels = metadata.get('labels') or {}
            annotations = metadata.get('annotations') or {}
            if (
                len(registered) != 1
                or not registered[0].get('actual_uid')
                or metadata.get('uid') != registered[0]['actual_uid']
                or metadata.get('namespace') != binding['namespace']
                or metadata.get('name') != ref['secret_name']
                or any(labels.get(key) != str(expected) for key, expected in (lease.get('owner_labels') or {}).items())
                or annotations.get('chaosatlas.dev/principal-role') != ref['principal_role']
                or annotations.get('chaosatlas.dev/principal-id') != binding['principal_id']
            ):
                raise ValueError('Secret identity is outside the verified lease principal binding')
            expected_uid = registered[0]['actual_uid']
        else:
            if metadata.get('uid') != ref['secret_uid'] or metadata.get('namespace') != binding['namespace'] or metadata.get('name') != ref['secret_name']:
                raise ValueError('Secret identity differs from approved reference')
            expected_uid = ref['secret_uid']
        data = value.get('data')
        if not isinstance(data, dict) or set(data) != set(ref['header_keys'].values()):
            raise ValueError('referenced authentication Secret key set differs from contract')
        try:
            headers = {name: base64.b64decode(value['data'][key], validate=True).decode('utf-8') for name, key in ref['header_keys'].items()}
            validate_auth_headers(headers)
        except (KeyError, ValueError, UnicodeError, TypeError):
            raise ValueError('referenced authentication material missing or invalid') from None
        self._audit[reference_id] = {'secret_name': ref['secret_name'], 'secret_uid': expected_uid,
                                     'namespace_uid': binding['namespace_uid'], 'principal_id': binding['principal_id'],
                                     'key_names': sorted(ref['header_keys'].values()),
                                     'binding_source': ref['source']}
        if lease_owned:
            self._audit[reference_id]['principal_role'] = ref['principal_role']
        return headers
