from __future__ import annotations

from pathlib import Path

from tools.train_ticket_latency_fixture import build_train_ticket_latency_fixture


REPO_ROOT = Path(__file__).resolve().parents[2]
TRAIN_TICKET_ROOT = REPO_ROOT / "artifacts" / "train-ticket"


def test_train_ticket_latency_fixture_preserves_boundary_claim_scope() -> None:
    fixture = build_train_ticket_latency_fixture(TRAIN_TICKET_ROOT)

    assert fixture["project_id"] == "FudanSELab/train-ticket"
    assert fixture["claim_scope"] == "service:ts-station-service/network-edge"
    assert fixture["boundary"]["client_timeout_sec"] == 5.0
    assert fixture["boundary"]["production_slo_defined"] is False
    assert [item["nominal_delay"] for item in fixture["profiles"]] == ["100ms", "500ms", "2s"]
    assert fixture["timeout_case"]["classification"] == "client_timeout_server_completion_after_delay"
    assert fixture["timeout_case"]["defense_claim_type"] is None


def test_train_ticket_latency_fixture_cannot_emit_executable_guard() -> None:
    fixture = build_train_ticket_latency_fixture(TRAIN_TICKET_ROOT)

    assert fixture["knowledge_card"]["knowledge_status"] == "provisional"
    assert fixture["knowledge_card"]["rca_status"] == "bounded"
    assert [item["kind"] for item in fixture["regression"]["intents"]] == ["discriminate"]
    assert fixture["regression"]["rejected_cards"] == []
    assert fixture["knowledge_card"]["defense_claim_type"] is None
