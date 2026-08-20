from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.compile_rca_regression import (
    compile_regression_intents,
    project_knowledge_draft,
)
from tools.rca_loop import sha256_json
from tools.sock_shop_rca import build_sock_shop_pilot

REPO_ROOT = Path(__file__).resolve().parents[2]
VERDICT_PATH = REPO_ROOT / "artifacts" / "sock-shop" / "sock_shop_verdicts.json"


def _card(**overrides: object) -> dict[str, object]:
    card: dict[str, object] = {
        "id": "KB-RCA-001",
        "knowledge_status": "provisional",
        "weakness_status": "confirmed",
        "rca_status": "bounded",
        "applicability_conditions": ["real_business_path"],
        "regression_recipe": {"oracle": "sock-shop-catalogue"},
        "next_evidence": ["scoped_catalogue_logs"],
        "stop_rule": "stop after two valid reproductions",
        "regression_intents": [],
        "counter_evidence": [],
        "exclusion_conditions": [],
    }
    card.update(overrides)
    return card


def test_provisional_card_generates_discrimination_intent_only() -> None:
    card = _card()
    result = compile_regression_intents([card], snapshot={"cards": [card]})
    assert [item["kind"] for item in result["intents"]] == ["discriminate"]
    assert result["intents"][0]["source_card_id"] == "KB-RCA-001"


def test_confirmed_provisional_card_generates_reproduce_intent() -> None:
    card = _card(rca_status="confirmed", next_evidence=[])
    result = compile_regression_intents([card], snapshot={"cards": [card]})
    assert [item["kind"] for item in result["intents"]] == ["reproduce"]


def test_local_reusable_card_generates_reproduce_and_guard() -> None:
    card = _card(knowledge_status="local_reusable", rca_status="confirmed")
    result = compile_regression_intents([card], snapshot={"cards": [card]})
    assert [item["kind"] for item in result["intents"]] == ["reproduce", "guard"]
    guard = result["intents"][1]
    assert "closed_runtime_boundary_no_reinjection" in guard["stop_rule"]


def test_contested_card_generates_no_executable_intent() -> None:
    card = _card(knowledge_status="contested")
    result = compile_regression_intents([card], snapshot={"cards": [card]})
    assert result["intents"] == []
    assert card["id"] in result["rejected_cards"]


def test_every_intent_carries_oracle_evidence_stop_rule_and_snapshot_hash() -> None:
    card = _card(knowledge_status="local_reusable", rca_status="confirmed")
    snapshot = {"cards": [card]}
    result = compile_regression_intents([card], snapshot=snapshot)
    expected_hash = sha256_json(snapshot)
    assert result["snapshot_sha256"] == expected_hash
    for intent in result["intents"]:
        assert intent["snapshot_sha256"] == expected_hash
        assert intent["source_card_id"] == "KB-RCA-001"
        assert intent["oracle"] == "sock-shop-catalogue"
        assert intent["required_evidence"]
        assert intent["stop_rule"]
        assert intent["kind"] in {"reproduce", "discriminate", "guard"}


def test_project_knowledge_draft_has_required_card_fields(tmp_path: Path) -> None:
    build_sock_shop_pilot(
        verdict_path=VERDICT_PATH,
        output_root=tmp_path / "rca_loop",
        project_commit="sock-shop-fixture-commit",
        round_id="pilot-r1",
    )
    root = tmp_path / "rca_loop"
    case = json.loads(next(iter((root / "cases").glob("*.json"))).read_text(encoding="utf-8"))
    draft = project_knowledge_draft(case, case["hypotheses"], case["next_actions"])
    for field in (
        "id",
        "version",
        "status",
        "evidence_state",
        "project",
        "project_commit",
        "test_node",
        "test_node_centered_graph",
        "four_layer_validation",
        "next_evidence",
        "weakness_status",
        "rca_status",
        "knowledge_status",
        "mechanism_level",
        "applicability_conditions",
        "exclusion_conditions",
        "counter_evidence",
        "regression_intents",
        "stop_rule",
    ):
        assert field in draft, field
    assert draft["knowledge_status"] == "provisional"
    assert draft["weakness_status"] == case["weakness_status"]
    assert draft["rca_status"] == case["rca_status"]
    assert draft["next_evidence"]
    assert "password" not in json.dumps(draft).lower()


def test_project_knowledge_draft_never_upgrades_status(tmp_path: Path) -> None:
    build_sock_shop_pilot(
        verdict_path=VERDICT_PATH,
        output_root=tmp_path / "rca_loop",
        project_commit="sock-shop-fixture-commit",
        round_id="pilot-r1",
    )
    case = json.loads(
        next(iter((tmp_path / "rca_loop" / "cases").glob("*.json"))).read_text(encoding="utf-8")
    )
    case["knowledge_status"] = "local_reusable"  # tampered input
    draft = project_knowledge_draft(case, case["hypotheses"], case["next_actions"])
    # bounded pilot cases can only project provisional drafts
    assert draft["knowledge_status"] == "provisional"


def test_compile_cli_writes_drafts_and_intents(tmp_path: Path) -> None:
    from tools.compile_rca_regression import main as compile_main

    build_sock_shop_pilot(
        verdict_path=VERDICT_PATH,
        output_root=tmp_path / "rca_loop",
        project_commit="sock-shop-fixture-commit",
        round_id="pilot-r1",
    )
    rc = compile_main(
        [
            "--rca-root",
            str(tmp_path / "rca_loop"),
            "--output",
            str(tmp_path / "rca_loop" / "knowledge_drafts"),
        ]
    )
    assert rc == 0
    drafts = list((tmp_path / "rca_loop" / "knowledge_drafts").glob("KB-RCA-*.json"))
    assert len(drafts) == 3
    intents = json.loads(
        (tmp_path / "rca_loop" / "knowledge_drafts" / "regression_intents.json").read_text(encoding="utf-8")
    )
    assert intents["snapshot_sha256"]
    assert len(intents["intents"]) == 3
    # rerunning into the same non-empty output must be refused
    with pytest.raises(FileExistsError):
        compile_main(
            [
                "--rca-root",
                str(tmp_path / "rca_loop"),
                "--output",
                str(tmp_path / "rca_loop" / "knowledge_drafts"),
            ]
        )
