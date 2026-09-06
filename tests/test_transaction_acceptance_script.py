import json

import pytest

from scripts.run_transaction_oracle_acceptance import _finalize_transaction, _load_fixtures


def test_external_byte_fixture_reference_is_loaded_without_entering_contract(tmp_path):
    payload = tmp_path / 'synthetic.png'
    payload.write_bytes(b'not-a-real-image-but-bounded-for-loader-test')
    manifest = tmp_path / 'fixtures.json'
    manifest.write_text(json.dumps({
        'synthetic_png': {'source': 'file', 'path': 'synthetic.png'},
        'fixture_sha256': 'synthetic-test-only',
    }), encoding='utf-8')
    result = _load_fixtures(
        manifest,
        {'synthetic_png': {'type': 'bytes', 'max_length': 1024},
         'fixture_sha256': {'type': 'string', 'max_length': 64}},
        tmp_path / 'repository',
    )
    assert result['synthetic_png'] == payload.read_bytes()
    assert result['fixture_sha256'] == 'synthetic-test-only'


@pytest.mark.parametrize('descriptor', [
    'plain-path-is-not-accepted',
    {'source': 'inline', 'path': 'synthetic.png'},
    {'source': 'file', 'path': 'synthetic.png', 'value': 'hidden'},
])
def test_byte_fixture_rejects_ambiguous_or_inline_material(tmp_path, descriptor):
    (tmp_path / 'synthetic.png').write_bytes(b'x')
    manifest = tmp_path / 'fixtures.json'
    manifest.write_text(json.dumps({'payload': descriptor}), encoding='utf-8')
    with pytest.raises(ValueError):
        _load_fixtures(manifest, {'payload': {'type': 'bytes', 'max_length': 10}}, tmp_path / 'repository')


def test_prepare_failure_reuses_completed_cleanup_instead_of_calling_it_twice():
    completed = {'status': 'cleaned', 'cleanup_confirmed': True, 'environment_released': True}

    class Workflow:
        def cleanup_fixture(self, _context):
            raise AssertionError('cleanup must not be repeated')

    replay = type('Replay', (), {'_run_id': 'run-test'})()
    assert _finalize_transaction(Workflow(), replay, 'run-test', {'cleanup': completed}) is completed
