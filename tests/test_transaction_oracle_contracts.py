import json
from pathlib import Path

import pytest

from chaosatlas.oracles.builder import OracleBuilder
from chaosatlas.oracles.transaction_contracts import (
    evaluate_assertions,
    freeze_approved_contract,
    make_draft,
    record_human_approval,
    validate_transaction_contract,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("app", ["immich", "medusa", "rocketchat", "erpnext"])
def test_four_transaction_oracle_drafts_are_validated_but_not_approved(app):
    profile = json.loads((ROOT / "projects" / "chaosatlas-apps" / app / "profile.json").read_text(encoding="utf-8-sig"))
    contract = OracleBuilder().build(project_id=app, project_revision=profile["project_commit"])
    assert validate_transaction_contract(contract) == []
    assert contract["status"] == "validated"
    assert contract["approval"] == {"required": True, "record": None}
    assert contract["project_revision"] == profile["project_commit"]


def test_contract_rejects_arbitrary_hosts_missing_cleanup_and_embedded_credentials():
    payload = {
        "oracle_id": "unsafe-oracle", "project_id": "x", "project_revision": "r", "evidence_sources": [], "credential_refs": [],
        "allowed_requests": [{"id": "x", "method": "GET", "path": "https://attacker.invalid/x"}], "steps": [{"id": "x", "request_id": "x"}],
        "assertions": [{"id": "x", "operator": "status_equals", "expected": 200}], "ownership": {}, "cleanup": {"strategy": "none", "on_every_exit": False},
        "approval": {"required": True, "record": None}, "api_token": "canary-oracle-secret",
    }
    errors = validate_transaction_contract(make_draft(payload))
    assert "credential material is forbidden; use credential_refs" in errors
    assert "absolute or host-changing request path is forbidden" in errors
    assert any("cleanup" in error for error in errors)


def test_approval_api_requires_concrete_external_record():
    contract = OracleBuilder().build(project_id="immich", project_revision="r")
    with pytest.raises(ValueError, match="concrete human approval"):
        record_human_approval(contract, {"decision": "approved"})


def test_changing_approved_semantics_invalidates_hash_and_approval_subject():
    contract = OracleBuilder().build(project_id="immich", project_revision="r")
    approved = record_human_approval(contract, {"decision": "approved", "reviewer": "human-reviewer", "reviewed_at": "2026-09-06T00:00:00+00:00"})
    assert validate_transaction_contract(approved) == []
    approved["assertions"][0]["expected"] = 500
    errors = validate_transaction_contract(approved)
    assert "contract hash mismatch" in errors
    assert "approved/frozen Oracle requires a matching human approval record" in errors


def test_approved_contract_can_be_frozen_without_changing_approval_subject():
    contract = OracleBuilder().build(project_id="immich", project_revision="r")
    approved = record_human_approval(contract, {"decision": "approved", "reviewer": "human-reviewer", "reviewed_at": "2026-09-06T00:00:00+00:00"})
    frozen = freeze_approved_contract(approved)
    assert frozen["status"] == "frozen"
    assert frozen["approval"]["record"] == approved["approval"]["record"]
    assert frozen["contract_sha256"] != approved["contract_sha256"]
    assert validate_transaction_contract(frozen) == []


def test_freeze_rejects_contract_without_human_approval():
    contract = OracleBuilder().build(project_id="immich", project_revision="r")
    with pytest.raises(ValueError, match="only an approved Oracle"):
        freeze_approved_contract(contract)


def test_oracle_self_check_accepts_normal_and_detects_wrong_hash():
    contract = OracleBuilder().build(project_id="immich", project_revision="r")
    observations = {"upload-synthetic-image": {"status": 201, "json": {"id": "asset-1"}}, "download-original": {"body_sha256": "fixture-hash"}}
    assert evaluate_assertions(contract, observations, {"fixture_sha256": "fixture-hash"})["status"] == "pass"
    bad = evaluate_assertions(contract, observations, {"fixture_sha256": "wrong-hash"})
    assert bad["status"] == "fail"
    assert bad["failed_assertions"] == ["original-byte-hash"]
