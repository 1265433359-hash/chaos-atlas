from __future__ import annotations

from tools.feedback_protocol import (
    build_feedback_card,
    build_next_kb,
    classify_outcome,
    knowledge_projection,
    validate_ablation_pair,
    validate_knowledge_card_boundary,
)


def valid_result(**overrides):
    value = {
        "project_id": "P02",
        "project_commit": "a" * 40,
        "round_id": "r1",
        "canonical_signature": "sig-1",
        "target": "lab/service/api",
        "target_kind": "service",
        "fault_family": "network_delay",
        "oracle_label": "weakness",
        "valid_reproductions": 2,
        "evidence": {key: True for key in ("baseline", "injection", "observation", "recovery", "cleanup", "independent_oracle")},
    }
    value.update(overrides)
    return value


def test_environment_is_not_protection_and_confirmed_requires_full_evidence() -> None:
    assert classify_outcome(valid_result(environment_blocked=True)) == "environment_blocked"
    assert classify_outcome(valid_result(oracle_label="environment_blocked")) == "environment_blocked"
    assert classify_outcome(valid_result(evidence={"baseline": True})) == "unsupported"
    assert classify_outcome(valid_result()) == "confirmed_weakness"


def test_feedback_requires_review_and_blocks_same_project() -> None:
    card = build_feedback_card(valid_result(), review_status="human_reviewed")
    base = {"kb_version": "v1", "cards": []}
    blocked = build_next_kb(base, [card], current_project="P02", target_projects=["P02"], round_id="r1", project_order=["P01", "P02", "P03"])
    assert blocked["cards"] == []
    assert blocked["provenance"]["rejected"][0]["reason"] == "same_project_feedback_forbidden"

    accepted = build_next_kb(base, [card], current_project="P03", target_projects=["P03"], round_id="r1", project_order=["P01", "P02", "P03"])
    assert [item["card_id"] for item in accepted["cards"]] == [card["card_id"]]
    assert "evidence" not in accepted["cards"][0]
    assert accepted["cards"][0]["abstraction"] == card["abstraction"]
    assert accepted["provenance"]["same_round_leakage"] is False


def test_feedback_rejects_missing_order_and_future_project_cards() -> None:
    card = build_feedback_card(valid_result(project_id="P04"), review_status="human_reviewed")
    base = {"kb_version": "v1", "cards": []}
    no_order = build_next_kb(base, [card], current_project="P03", target_projects=["P03"], round_id="r1")
    assert no_order["provenance"]["rejected"][0]["reason"] == "project_order_required"
    future = build_next_kb(base, [card], current_project="P03", target_projects=["P03"], round_id="r1", project_order=["P01", "P02", "P03", "P04"])
    assert future["provenance"]["rejected"][0]["reason"] == "future_project_feedback_forbidden"


def test_projection_rejects_runtime_fields_but_keeps_audit_card() -> None:
    card = build_feedback_card(valid_result(), review_status="human_reviewed")
    assert "evidence" in card
    assert "evidence" not in knowledge_projection(card)
    card["abstraction"]["mutation_path"] = "secret-runtime-path"
    assert validate_knowledge_card_boundary(card)["valid"] is False


def test_ablation_pair_requires_byte_identical_shared_views() -> None:
    shared = {"project_id": "P02", "seed": 1001, "common_input": {"x": 1}, "topology_evidence": {"nodes": []}, "runtime_contract": {"x": 1}, "knowledge_view": {"facts": {"new": "fact"}}}
    nokb = dict(shared, knowledge_view=None)
    assert validate_ablation_pair(shared, nokb)["valid"] is True
    altered = dict(nokb, runtime_contract={"x": 2})
    assert validate_ablation_pair(shared, altered)["valid"] is False
