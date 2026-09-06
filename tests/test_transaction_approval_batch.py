"""All decisions and files here are synthetic-test-only, not user approval."""

from copy import deepcopy
import hashlib
import json

import pytest

from chaosatlas.oracles.approval_batch import SCHEMA, publish_approval
from chaosatlas.oracles.builder import OracleBuilder


def fixture(tmp_path):
    root = tmp_path / 'repo'
    entries = []
    for app in ('immich', 'medusa', 'rocketchat', 'erpnext'):
        contract = OracleBuilder().build(project_id=app, project_revision='synthetic-test-only')
        path = root / 'projects' / app / 'draft.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(contract), encoding='utf-8')
        entries.append({'path': path.relative_to(root).as_posix(), 'file_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                        'contract_sha256': contract['contract_sha256'], 'oracle_id': contract['oracle_id']})
    return root, {'schema_version': SCHEMA, 'contracts': entries}


def publish(root, manifest, **overrides):
    return publish_approval(root, manifest, **{
        'reviewer': 'synthetic-test-only', 'reviewed_at': '2020-01-01T00:00:00+00:00',
        'decision_reference': 'synthetic-test-only:no-real-authorization',
        'staging_root': root.parent / 'external', **overrides,
    })


def test_fourth_invalid_target_publishes_nothing(tmp_path):
    root, manifest = fixture(tmp_path)
    manifest['contracts'][3]['file_sha256'] = 'invalid'
    with pytest.raises(ValueError, match='file changed'):
        publish(root, manifest)
    assert not (root / 'projects/chaosatlas-apps/oracle-approvals').exists()
    assert not (root.parent / 'external').exists()


def test_atomic_batch_safe_retry_and_distinct_recording_time(tmp_path):
    root, manifest = fixture(tmp_path)
    bundle = publish(root, manifest)
    assert publish(root, manifest) == bundle
    assert len(list(bundle.iterdir())) == 5
    audit = json.loads((bundle / 'approval-batch.json').read_text(encoding='utf-8'))
    assert audit['recorded_at'] != audit['subject']['decision']['reviewed_at']
    assert all(json.loads((root / e['path']).read_text())['status'] == 'validated' for e in manifest['contracts'])


def test_interrupted_staging_cannot_publish_partial_approval(tmp_path, monkeypatch):
    root, manifest = fixture(tmp_path)
    from chaosatlas.isolation.lease_store import LeaseStore
    original = LeaseStore._atomic_write
    count = 0
    def fail_fourth(self, path, value):
        nonlocal count
        count += 1
        if count == 4:
            raise OSError('synthetic-test-only disk failure')
        original(self, path, value)
    monkeypatch.setattr(LeaseStore, '_atomic_write', fail_fourth)
    with pytest.raises(OSError):
        publish(root, manifest)
    assert not (root / 'projects/chaosatlas-apps/oracle-approvals').exists()
    assert list((root.parent / 'external').glob('*/immich-*.json'))
    monkeypatch.setattr(LeaseStore, '_atomic_write', original)
    assert publish(root, manifest).is_dir()


def test_retry_rejects_modified_published_contract(tmp_path):
    root, manifest = fixture(tmp_path)
    bundle = publish(root, manifest)
    (bundle / 'immich-asset-roundtrip-v2.json').write_text('{}')
    with pytest.raises(ValueError, match='was changed'):
        publish(root, manifest)


@pytest.mark.parametrize('mutation', [
    lambda m: m['contracts'].append(deepcopy(m['contracts'][0])),
    lambda m: m['contracts'][0].update(path='../outside.json'),
    lambda m: m['contracts'][0].update(contract_sha256='different'),
    lambda m: m.update(implicit_approval=True),
])
def test_ambiguous_or_changed_review_set_rejected(tmp_path, mutation):
    root, manifest = fixture(tmp_path)
    mutation(manifest)
    with pytest.raises(ValueError):
        publish(root, manifest)


def test_decision_timezone_required(tmp_path):
    root, manifest = fixture(tmp_path)
    with pytest.raises(ValueError, match='timezone'):
        publish(root, manifest, reviewed_at='2020-01-01T00:00:00')
