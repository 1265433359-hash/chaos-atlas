from copy import deepcopy

import pytest

from chaosatlas.oracles.builder import OracleBuilder
from test_transaction_v3_validation import write_contract


def test_builder_v3_returns_validated_structured_draft():
    payload = write_contract()
    payload.pop('schema_version', None)
    payload.pop('status', None)
    payload.pop('contract_sha256', None)
    payload.update(oracle_id='synthetic-v3', evidence_sources=['synthetic-test-only'], credential_refs=[], ownership={'synthetic_only': True})
    result = OracleBuilder().build_v3(project_id='synthetic', project_revision='synthetic-test-only', structured_payload=payload)
    assert result['schema_version'] == 'chaosatlas-transaction-oracle-v3'
    assert result['status'] == 'validated'
    assert result['project_id'] == 'synthetic'


@pytest.mark.parametrize('field', ['python', 'shell', 'command', 'arbitrary_request'] )
def test_builder_v3_rejects_unreviewed_executable_fields(field):
    payload = write_contract()
    payload.pop('schema_version', None)
    payload.pop('status', None)
    payload.pop('contract_sha256', None)
    payload.update(oracle_id='synthetic-v3', evidence_sources=['synthetic-test-only'], credential_refs=[], ownership={'synthetic_only': True})
    payload['steps'][0][field] = 'not allowed'
    with pytest.raises(ValueError):
        OracleBuilder().build_v3(project_id='synthetic', project_revision='synthetic-test-only', structured_payload=payload)
