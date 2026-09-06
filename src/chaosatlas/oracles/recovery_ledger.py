"""Durable per-operation recovery state, using isolation's atomic writer and locks."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from chaosatlas.isolation.contracts import SAFE_ID, canonical_hash, sensitive_paths, verify_hash, with_hash
from chaosatlas.isolation.lease_store import LeaseStore
from chaosatlas.workspace import is_within, state_root

SCHEMA = 'chaosatlas-transaction-recovery-v2'
TRANSITIONS = {
    'not_sent': {'intent_persisted'},
    'intent_persisted': {'outcome_unknown', 'not_sent'},
    'outcome_unknown': {'owned_confirmed', 'absent_confirmed', 'cleanup_blocked'},
    'owned_confirmed': {'cleanup_pending', 'cleanup_blocked', 'absent_confirmed'},
    'cleanup_pending': {'absent_confirmed', 'cleanup_blocked'},
    'cleanup_blocked': {'owned_confirmed', 'absent_confirmed', 'cleanup_pending'},
    'absent_confirmed': set(),
}
BINDING_KEYS = {'lease_id', 'cluster_uid', 'namespace_uid', 'namespace', 'context', 'service_uid', 'service', 'origin', 'principal_id', 'project_revision', 'service_spec_sha256'}
ENTRY_KEYS = {'state', 'object_type', 'marker_sha256', 'identity', 'ownership_sha256', 'absence_sha256', 'reason_code'}


class RecoveryLedger:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root).resolve() if root else state_root() / 'transactions'
        repository = Path(__file__).resolve().parents[3]
        if is_within(self.root, repository):
            raise ValueError('transaction ledger must stay outside repository')
        self.store = LeaseStore(self.root)

    def _path(self, run_id: str) -> Path:
        if not SAFE_ID.fullmatch(run_id):
            raise ValueError('unsafe transaction run identity')
        return self.root / 'ledgers' / f'{run_id}.json'

    @contextmanager
    def operation(self, run_id: str):
        self._path(run_id)
        with self.store.operation_lock(run_id):
            yield

    def load(self, run_id: str) -> dict[str, Any]:
        try:
            value = json.loads(self._path(run_id).read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise ValueError('transaction recovery ledger unavailable or corrupt') from exc
        self._validate(value)
        if value['run_id'] != run_id:
            raise ValueError('transaction recovery run identity mismatch')
        return value

    def _validate(self, value: Any) -> None:
        if not isinstance(value, dict) or value.get('schema_version') != SCHEMA or not verify_hash(value, 'ledger_sha256'):
            raise ValueError('transaction ledger integrity failure')
        if set(value) != {'schema_version', 'run_id', 'attempt_id', 'project_id', 'lifecycle', 'contract_sha256', 'binding', 'operations', 'sequence', 'ledger_sha256'}:
            raise ValueError('transaction ledger unknown or missing fields')
        if not isinstance(value['project_id'], str) or not SAFE_ID.fullmatch(value['project_id']) or value['lifecycle'] not in {'active', 'closed'}:
            raise ValueError('invalid project recovery lifecycle')
        if sensitive_paths(value):
            raise ValueError('credential material forbidden in recovery ledger')
        binding = value['binding']
        if not isinstance(binding, dict) or set(binding) != BINDING_KEYS or any(not isinstance(x, str) or not x or len(x) > 1024 for x in binding.values()):
            raise ValueError('transaction ledger requires exact runtime binding')
        if not isinstance(value['operations'], dict):
            raise ValueError('invalid operations')
        for identifier, entry in value['operations'].items():
            if not SAFE_ID.fullmatch(identifier) or not isinstance(entry, dict) or set(entry) - ENTRY_KEYS:
                raise ValueError('invalid recovery operation')
            if entry.get('state') not in TRANSITIONS:
                raise ValueError('invalid recovery state')
            identity = entry.get('identity', {})
            if not isinstance(identity, dict) or any(not isinstance(x, str) or not x or len(x) > 256 for x in identity.values()):
                raise ValueError('invalid owned identity')
            if entry['state'] in {'owned_confirmed', 'cleanup_pending'} and (not identity or not entry.get('ownership_sha256')):
                raise ValueError('owned state requires identity and ownership evidence')
            if entry['state'] == 'absent_confirmed' and not entry.get('absence_sha256'):
                raise ValueError('absent state requires absence evidence')
            if value['lifecycle'] == 'closed' and entry['state'] not in {'not_sent', 'absent_confirmed'}:
                raise ValueError('closed transaction cannot contain unresolved operations')

    def _save(self, value: dict[str, Any]) -> dict[str, Any]:
        value = with_hash(value, 'ledger_sha256')
        self._validate(value)
        self.store._atomic_write(self._path(value['run_id']), value)
        return deepcopy(value)

    def create(self, run_id: str, *, project_id: str, attempt_id: str, contract_sha256: str, binding: dict[str, str]) -> dict[str, Any]:
        # Caller holds operation() across the complete transaction/recovery action.
        if self._path(run_id).exists():
            raise FileExistsError('existing transaction requires recovery; cannot prepare again')
        with self.store.operation_lock('project-' + canonical_hash(project_id)[:48]):
            # Mark active before the first write. An empty operations map can be
            # a crashed pre-write run, not permission to start another session.
            for path in (self.root / 'ledgers').glob('*.json'):
                existing = self.load(path.stem)
                if existing['project_id'] == project_id and existing['lifecycle'] == 'active':
                    raise ValueError('project has an active transaction; recover it before preparing another')
            return self._save({
                'schema_version': SCHEMA, 'run_id': run_id, 'attempt_id': attempt_id,
                'project_id': project_id, 'lifecycle': 'active',
                'contract_sha256': contract_sha256, 'binding': deepcopy(binding), 'operations': {}, 'sequence': 0,
            })

    def assert_binding(self, run_id: str, binding: dict[str, str], contract_sha256: str) -> dict[str, Any]:
        value = self.load(run_id)
        if value['binding'] != binding or value['contract_sha256'] != contract_sha256:
            raise ValueError('recovery target, principal or contract identity mismatch')
        return value

    def intent(self, run_id: str, operation_id: str, *, object_type: str, marker_sha256: str) -> dict[str, Any]:
        value = self.load(run_id)
        if value['lifecycle'] != 'active':
            raise ValueError('closed transaction cannot start a new operation')
        if operation_id in value['operations']:
            raise ValueError('operation already recorded; reconcile before retry')
        value['operations'][operation_id] = {
            'state': 'intent_persisted', 'object_type': object_type,
            'marker_sha256': marker_sha256, 'identity': {},
        }
        value['sequence'] += 1
        return self._save(value)

    def transition(self, run_id: str, operation_id: str, state: str, **evidence: Any) -> dict[str, Any]:
        value = self.load(run_id)
        entry = value['operations'][operation_id]
        if state not in TRANSITIONS.get(entry['state'], set()):
            raise ValueError('invalid transaction recovery transition')
        if set(evidence) - (ENTRY_KEYS - {'state', 'object_type', 'marker_sha256'}):
            raise ValueError('unknown recovery evidence field')
        entry.update(deepcopy(evidence))
        entry['state'] = state
        value['sequence'] += 1
        return self._save(value)

    def cleanup_confirmed(self, run_id: str) -> bool:
        value = self.load(run_id)
        return all(entry['state'] in {'not_sent', 'absent_confirmed'} for entry in value['operations'].values())

    def close_run(self, run_id: str) -> dict[str, Any]:
        value = self.load(run_id)
        if not self.cleanup_confirmed(run_id):
            raise ValueError('unresolved transaction cannot close')
        value['lifecycle'] = 'closed'
        value['sequence'] += 1
        return self._save(value)

    def rebind_local_tunnel(self, run_id: str, binding: dict[str, str], contract_sha256: str) -> dict[str, Any]:
        """After verifying live UIDs, allow only the local ephemeral port to change.

        Caller holds operation() and has just verified the new lease tunnel.
        No namespace, cluster, principal, service or revision may change.
        """
        from urllib.parse import urlsplit
        value = self.load(run_id)
        old = value['binding']
        if value['contract_sha256'] != contract_sha256 or {k: v for k, v in old.items() if k != 'origin'} != {k: v for k, v in binding.items() if k != 'origin'}:
            raise ValueError('recovery target, principal or contract identity mismatch')
        for origin in (old['origin'], binding['origin']):
            parsed = urlsplit(origin)
            if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not parsed.port or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
                raise ValueError('only a verified local tunnel can be rebound')
        value['binding'] = deepcopy(binding)
        value['sequence'] += 1
        return self._save(value)
