"""Durable per-operation recovery state, using isolation's atomic writer and locks."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from chaosatlas.isolation.contracts import SAFE_ID, sensitive_paths, verify_hash, with_hash
from chaosatlas.isolation.lease_store import LeaseStore
from chaosatlas.workspace import is_within, state_root

SCHEMA = 'chaosatlas-transaction-recovery-v1'
TRANSITIONS = {
    'not_sent': {'intent_persisted'},
    'intent_persisted': {'outcome_unknown', 'not_sent'},
    'outcome_unknown': {'owned_confirmed', 'absent_confirmed', 'cleanup_blocked'},
    'owned_confirmed': {'cleanup_pending', 'cleanup_blocked'},
    'cleanup_pending': {'absent_confirmed', 'cleanup_blocked'},
    'cleanup_blocked': {'owned_confirmed', 'absent_confirmed', 'cleanup_pending'},
    'absent_confirmed': set(),
}
BINDING_KEYS = {'lease_id', 'cluster_uid', 'namespace_uid', 'namespace', 'context', 'service_uid', 'service', 'origin', 'principal_id', 'project_revision'}
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
        if set(value) != {'schema_version', 'run_id', 'attempt_id', 'contract_sha256', 'binding', 'operations', 'sequence', 'ledger_sha256'}:
            raise ValueError('transaction ledger unknown or missing fields')
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

    def _save(self, value: dict[str, Any]) -> dict[str, Any]:
        value = with_hash(value, 'ledger_sha256')
        self._validate(value)
        self.store._atomic_write(self._path(value['run_id']), value)
        return deepcopy(value)

    def create(self, run_id: str, *, attempt_id: str, contract_sha256: str, binding: dict[str, str]) -> dict[str, Any]:
        # Caller holds operation() across the complete transaction/recovery action.
        if self._path(run_id).exists():
            raise FileExistsError('existing transaction requires recovery; cannot prepare again')
        return self._save({
            'schema_version': SCHEMA, 'run_id': run_id, 'attempt_id': attempt_id,
            'contract_sha256': contract_sha256, 'binding': deepcopy(binding), 'operations': {}, 'sequence': 0,
        })

    def assert_binding(self, run_id: str, binding: dict[str, str], contract_sha256: str) -> dict[str, Any]:
        value = self.load(run_id)
        if value['binding'] != binding or value['contract_sha256'] != contract_sha256:
            raise ValueError('recovery target, principal or contract identity mismatch')
        return value

    def intent(self, run_id: str, operation_id: str, *, object_type: str, marker_sha256: str) -> dict[str, Any]:
        value = self.load(run_id)
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
