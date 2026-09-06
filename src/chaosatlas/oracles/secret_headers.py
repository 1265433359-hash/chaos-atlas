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
            if set(ref) != {'id', 'source', 'secret_name', 'secret_uid', 'principal_id', 'header_keys'} or ref['source'] != 'runtime_secret_ref':
                raise ValueError('exact versioned Secret reference required')
            if not isinstance(ref['id'], str) or ref['id'] in self._references:
                raise ValueError('duplicate or invalid credential reference')
            if not isinstance(ref['secret_name'], str) or not re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,252}', ref['secret_name']):
                raise ValueError('unsafe Secret name')
            if not isinstance(ref['secret_uid'], str) or not ref['secret_uid'] or len(ref['secret_uid']) > 128:
                raise ValueError('Secret UID pin required')
            if not isinstance(ref['header_keys'], dict) or not ref['header_keys']:
                raise ValueError('explicit authentication header keys required')
            validate_auth_headers({k: 'validation-only' for k in ref['header_keys']})
            for key in ref['header_keys'].values():
                if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,253}', key):
                    raise ValueError('unsafe Secret data key')
            self._references[ref['id']] = ref

    @property
    def audit(self):
        return deepcopy(self._audit)

    def __call__(self, reference_id):
        ref = self._references[reference_id]
        lease = self.runtime._lease()
        binding = self.runtime._read_identity(lease)
        if ref['principal_id'] != binding['principal_id']:
            raise ValueError('Secret reference principal differs from runtime')
        provider = self.runtime.manager.providers.get(lease['provider'])
        value, error = provider._json(lease['plan'], ['-n', binding['namespace'], 'get', 'secret', ref['secret_name']], lease=lease)
        if error or not isinstance(value, dict):
            raise ValueError('referenced Secret unavailable')
        metadata = value.get('metadata') or {}
        if metadata.get('uid') != ref['secret_uid'] or metadata.get('namespace') != binding['namespace'] or metadata.get('name') != ref['secret_name']:
            raise ValueError('Secret identity differs from approved reference')
        try:
            headers = {name: base64.b64decode(value['data'][key], validate=True).decode('utf-8') for name, key in ref['header_keys'].items()}
            validate_auth_headers(headers)
        except (KeyError, ValueError, UnicodeError, TypeError):
            raise ValueError('referenced authentication material missing or invalid') from None
        self._audit[reference_id] = {'secret_name': ref['secret_name'], 'secret_uid': ref['secret_uid'],
                                     'namespace_uid': binding['namespace_uid'], 'principal_id': binding['principal_id'],
                                     'key_names': sorted(ref['header_keys'].values())}
        return headers
