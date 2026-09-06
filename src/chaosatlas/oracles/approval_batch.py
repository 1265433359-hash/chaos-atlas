"""Publish an exact reviewed set atomically; never infer a human decision."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from chaosatlas.isolation.contracts import canonical_hash
from chaosatlas.isolation.lease_store import LeaseStore
from chaosatlas.oracles.transaction_contracts import (
    freeze_approved_contract, record_human_approval, validate_transaction_contract,
)
from chaosatlas.workspace import is_within, state_root

SCHEMA = 'chaosatlas-oracle-review-manifest-v1'


def publish_approval(root: Path, manifest: dict[str, Any], *, reviewer: str,
                     reviewed_at: str, decision_reference: str,
                     staging_root: Path | None = None) -> Path:
    """Publish by directory rename; interrupted staging remains external.

    The caller supplies the actual decision and known time. This function has
    no authority to infer approval from a plan selection or a default option.
    """
    root = root.resolve()
    if not all(isinstance(x, str) and x.strip() for x in (reviewer, reviewed_at, decision_reference)):
        raise ValueError('explicit reviewer, decision reference and decision time required')
    decision_time = datetime.fromisoformat(reviewed_at)
    if decision_time.tzinfo is None or decision_time > datetime.now(timezone.utc):
        raise ValueError('decision time must include timezone and cannot be in the future')
    if not isinstance(manifest, dict) or set(manifest) != {'schema_version', 'contracts'} or manifest['schema_version'] != SCHEMA:
        raise ValueError('invalid exact review manifest')
    entries = manifest['contracts']
    if not isinstance(entries, list) or not 1 <= len(entries) <= 64:
        raise ValueError('bounded nonempty review set required')
    prepared = []
    ids = set()
    paths = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {'path', 'file_sha256', 'contract_sha256', 'oracle_id'}:
            raise ValueError('exact path, file hash, semantic hash and Oracle ID required')
        path = (root / entry['path']).resolve()
        if not is_within(path, root / 'projects') or path in paths or entry['oracle_id'] in ids:
            raise ValueError('duplicate or out-of-project review target')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry['file_sha256']:
            raise ValueError('reviewed file changed')
        contract = json.loads(raw)
        if contract.get('contract_sha256') != entry['contract_sha256'] or contract.get('oracle_id') != entry['oracle_id']:
            raise ValueError('reviewed semantic identity changed')
        errors = validate_transaction_contract(contract)
        if errors or contract.get('status') != 'validated':
            raise ValueError('review target is not a validated contract')
        ids.add(entry['oracle_id'])
        paths.add(path)
        prepared.append(contract)

    decision = {'decision': 'approved', 'reviewer': reviewer, 'reviewed_at': reviewed_at,
                'decision_reference': decision_reference}
    subject = {'manifest': manifest, 'decision': decision}
    batch_id = canonical_hash(subject)
    target = root / 'projects' / 'chaosatlas-apps' / 'oracle-approvals' / batch_id
    external = (staging_root or (state_root() / 'approval-staging')).resolve()
    if is_within(external, root):
        raise ValueError('approval staging must be external')
    store = LeaseStore(external)
    with store.operation_lock('approval-' + batch_id[:48]):
        if target.exists():
            audit = json.loads((target / 'approval-batch.json').read_text(encoding='utf-8'))
            if audit.get('subject') != subject or not isinstance(audit.get('recorded_at'), str):
                raise ValueError('existing approval batch differs')
            hashes = {}
            for contract in prepared:
                frozen = freeze_approved_contract(record_human_approval(contract, {**decision, 'recorded_at': audit['recorded_at']}))
                existing = json.loads((target / f"{contract['oracle_id']}.json").read_text(encoding='utf-8'))
                if existing != frozen:
                    raise ValueError('existing frozen approval was changed')
                hashes[contract['oracle_id']] = frozen['contract_sha256']
            if audit.get('frozen_hashes') != hashes:
                raise ValueError('approval audit hashes changed')
            if {p.name for p in target.iterdir()} != {'approval-batch.json', *(f"{c['oracle_id']}.json" for c in prepared)}:
                raise ValueError('unexpected files in approval batch')
            return target
        recorded_at = datetime.now(timezone.utc).isoformat()
        frozen_set = [freeze_approved_contract(record_human_approval(c, {**decision, 'recorded_at': recorded_at})) for c in prepared]
        external.mkdir(parents=True, exist_ok=True)
        staged = Path(tempfile.mkdtemp(prefix=f'{batch_id}-', dir=external))
        for frozen in frozen_set:
            store._atomic_write(staged / f"{frozen['oracle_id']}.json", frozen)
        store._atomic_write(staged / 'approval-batch.json', {
            'schema_version': 'chaosatlas-oracle-approval-batch-v1',
            'subject': subject, 'recorded_at': recorded_at,
            'frozen_hashes': {c['oracle_id']: c['contract_sha256'] for c in frozen_set},
        })
        target.parent.mkdir(parents=True, exist_ok=True)
        # Cross-volume moves fail closed: copying a set is not atomic.
        os.rename(staged, target)
    return target
