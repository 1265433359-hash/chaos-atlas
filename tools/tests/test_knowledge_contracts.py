from __future__ import annotations

import json
from pathlib import Path

from tools.chaosatlas_adapters import KnowledgeProvider
from tools.knowledge_migration_audit import audit_knowledge_roots, build_consumption_report
from tools.validate_knowledge_base import validate


def _card(*, card_id: str = "KB-WEAK-local", project: str = "sock-shop", commit: str = "commit-a", status: str = "local_reusable") -> dict:
    return {
        "schema_version": "chaosatlas-weakness-knowledge-v1",
        "id": card_id,
        "project": project,
        "project_commit": commit,
        "case_family": "native_deployment_pod_kill",
        "weakness_id": f"WS-{project}-front-end-pod-kill",
        "target": "front-end",
        "target_kind": "deployment",
        "classification": "availability_weakness",
        "weakness_status": "confirmed",
        "rca_status": "confirmed",
        "knowledge_status": status,
        "mechanism_level": "service_boundary",
        "mechanism_claim": "single replica can degrade availability during pod kill",
        "test_node": {
            "family": "pod_kill",
            "operation": "pod_kill",
            "target": "front-end",
            "target_kind": "deployment",
        },
        "applicability_conditions": ["same project and commit"],
        "exclusion_conditions": ["cross_project_transfer_requires_existing_feedback_protocol"],
        "evidence_runs": [
            {"run_id": "run-a", "seed": 1, "run_fingerprint": "fp-a", "evidence_refs": ["runtime/a"]},
            {"run_id": "run-b", "seed": 2, "run_fingerprint": "fp-b", "evidence_refs": ["runtime/b"]},
        ],
        "valid_reproductions": 2,
        "counter_evidence": [],
        "promotion_audit": {"allowed": True, "next_status": "local_reusable"},
        "next_evidence": ["repeat_business_oracle"],
        "stop_rule": "stop after two valid reproductions or one clean falsification",
        "regression_intents": [{"kind": "reproduce"}, {"kind": "guard"}],
    }


def _write_card(root: Path, card: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{card['id']}.json").write_text(json.dumps(card), encoding="utf-8")


def test_validate_flat_weakness_root_accepts_new_card_schema(tmp_path: Path) -> None:
    root = tmp_path / "sock-shop-runtime"
    _write_card(root, _card())

    report = validate(root)

    assert report["valid"] is True, report
    assert report["schema_family"] == "chaosatlas-weakness-knowledge-v1"
    assert report["card_count"] == 1


def test_validate_flat_weakness_root_rejects_project_or_commit_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "sock-shop-runtime"
    _write_card(root, _card(project="online-boutique", commit="commit-b"))

    report = validate(root, expected_project="sock-shop", expected_commit="commit-a")

    assert report["valid"] is False
    assert any("project_mismatch" in error for error in report["errors"])
    assert any("project_commit_mismatch" in error for error in report["errors"])


def test_knowledge_provider_filters_foreign_project_and_commit(tmp_path: Path) -> None:
    _write_card(tmp_path, _card(card_id="KB-WEAK-local"))
    _write_card(tmp_path, _card(card_id="KB-WEAK-foreign", project="online-boutique"))
    _write_card(tmp_path, _card(card_id="KB-WEAK-old", commit="commit-old"))

    retrieval = KnowledgeProvider().retrieve(
        project_id="sock-shop",
        project_commit="commit-a",
        candidate_space={"candidate_count": 1, "candidates": [{"candidate_id": "front-end:pod_kill", "fault_family": "pod_kill"}]},
        root=tmp_path,
    )

    assert [card["id"] for card in retrieval["cards"]] == ["KB-WEAK-local"]
    assert {item["reason"] for item in retrieval["rejected_cards"]} == {"project_mismatch", "project_commit_mismatch"}


def test_migration_audit_keeps_foreign_cards_cross_project_pending(tmp_path: Path) -> None:
    sock_root = tmp_path / "sock-shop"
    online_root = tmp_path / "online-boutique"
    _write_card(sock_root, _card(card_id="KB-WEAK-sock"))
    _write_card(online_root, _card(card_id="KB-WEAK-online", project="online-boutique", commit="commit-online"))

    report = audit_knowledge_roots(
        {"sock-shop": sock_root, "online-boutique": online_root},
        target_project="online-boutique",
        target_commit="commit-online",
    )

    assert report["valid"] is True, report
    by_id = {item["id"]: item for item in report["cards"]}
    assert by_id["KB-WEAK-online"]["consumption"] == "local_reusable"
    assert by_id["KB-WEAK-sock"]["consumption"] == "cross_project_pending"
    assert report["accepted_card_ids"] == ["KB-WEAK-online"]
    assert report["cross_project_pending_card_ids"] == ["KB-WEAK-sock"]


def test_consumption_report_exposes_accepted_and_rejected_knowledge() -> None:
    report = build_consumption_report(
        {
            "cards": [{"id": "KB-local", "knowledge_status": "local_reusable"}],
            "rejected_cards": [
                {"id": "KB-foreign", "reason": "project_mismatch"},
                {"id": "KB-old", "reason": "project_commit_mismatch"},
            ],
        },
        project_id="sock-shop",
        project_commit="commit-a",
    )

    assert report["schema_version"] == "chaosatlas-knowledge-consumption-v1"
    assert report["accepted_card_ids"] == ["KB-local"]
    assert report["rejected_card_ids"] == ["KB-foreign", "KB-old"]
    assert report["rejection_reasons"] == {
        "project_mismatch": 1,
        "project_commit_mismatch": 1,
    }
    assert report["cross_project_pending"] is True
