"""H1 regressions: synthetic-test-only; never application or approval evidence."""

import pytest

from chaosatlas.isolation.contracts import with_hash
from chaosatlas.oracles.builder import OracleBuilder
from chaosatlas.oracles.replay import ResponseLost, TransactionReplayer
from chaosatlas.oracles.transaction_contracts import (
    evaluate_assertions, freeze_approved_contract, record_human_approval,
    validate_transaction_contract,
)


def synthetic_contract():
    return freeze_approved_contract(record_human_approval(
        OracleBuilder().build(project_id="immich", project_revision="synthetic-test-only"),
        {"decision": "approved", "reviewer": "synthetic-test-only",
         "reviewed_at": "2026-09-06T00:00:00+00:00"},
    ))


class LostTransport:
    def __init__(self):
        self.sent = 0

    def send(self, **kwargs):
        self.sent += 1
        raise ResponseLost("synthetic response loss")


def replay(transport, **fixtures):
    return TransactionReplayer(
        synthetic_contract(), transport,
        credential_headers=lambda _: {"x-api-key": "synthetic-test-only"},
        fixtures={"synthetic_png": b"synthetic-test-only", "fixture_timestamp": "2026-09-06T00:00:00Z", **fixtures},
    )


def test_h1_second_response_loss_must_not_confirm_cleanup():
    transport = LostTransport()
    result = replay(transport).prepare(run_id="synthetic-run")
    assert transport.sent == 2
    assert result["status"] == "prepare_failed"
    assert result["cleanup"]["cleanup_confirmed"] is False


def test_h1_fixture_run_identity_conflict_rejected_before_send():
    transport = LostTransport()
    with pytest.raises(ValueError, match="reserved|identity|fixture"):
        replay(transport, run_id="foreign-run").prepare(run_id="synthetic-run")
    assert transport.sent == 0


def test_h1_invalid_json_path_rejected_at_validation_and_evaluation():
    contract = OracleBuilder().build(project_id="immich", project_revision="synthetic-test-only")
    contract["assertions"][1]["path"] = "not-a-json-path"
    contract = with_hash(contract, "contract_sha256")
    assert any("path" in error for error in validate_transaction_contract(contract))
    result = evaluate_assertions(
        {"assertions": [contract["assertions"][1]]},
        {"upload-synthetic-image": {"json": {"unrelated": "value"}}}, {},
    )
    assert result["status"] == "fail"
