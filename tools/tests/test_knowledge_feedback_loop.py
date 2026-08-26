from __future__ import annotations

import json

from tools.chaosatlas_adapters import KnowledgeProvider
from tools.chaosatlas_hypothesis import rank_candidates
from tools.compile_rca_regression import compile_regression_intents


def _candidates() -> dict:
    return {
        "candidate_count": 2,
        "candidates": [
            {"candidate_id": "candidate:network_loss", "fault_family": "network_loss"},
            {"candidate_id": "candidate:pod_kill", "fault_family": "pod_kill"},
        ],
    }


def test_local_reusable_card_is_retrieved_and_changes_candidate_order(tmp_path) -> None:
    card = {
        "id": "KB-local-pod-kill",
        "knowledge_status": "local_reusable",
        "project": "sock-shop",
        "test_node": {"family": "pod_kill", "operation": "pod_kill"},
        "next_evidence": ["same_oracle_reproduction"],
        "regression_recipe": {"oracle": "HTTP / on front-end"},
        "applicability_conditions": ["same project and commit"],
        "stop_rule": "stop after two valid reproductions",
        "rca_status": "confirmed",
    }
    (tmp_path / "KB-local-pod-kill.json").write_text(json.dumps(card), encoding="utf-8")

    retrieval = KnowledgeProvider().retrieve(project_id="sock-shop", candidate_space=_candidates(), root=tmp_path)
    ranked = rank_candidates(_candidates(), retrieval["cards"])
    intents = compile_regression_intents([card], snapshot={"cards": [card]})

    assert retrieval["cards"][0]["status"] == "local_reusable"
    assert retrieval["cards"][0]["knowledge_status"] == "local_reusable"
    assert ranked["candidate_ids"][0] == "candidate:pod_kill"
    assert [item["kind"] for item in intents["intents"]] == ["reproduce", "guard"]


def test_provisional_card_is_context_only_and_contested_card_is_not_retrieved(tmp_path) -> None:
    provisional = {
        "id": "KB-provisional-pod-kill",
        "knowledge_status": "provisional",
        "project": "sock-shop",
        "test_node": {"family": "pod_kill", "operation": "pod_kill"},
    }
    contested = {
        "id": "KB-contested-network-loss",
        "knowledge_status": "contested",
        "project": "sock-shop",
        "test_node": {"family": "network_loss", "operation": "network_loss"},
    }
    (tmp_path / "KB-provisional-pod-kill.json").write_text(json.dumps(provisional), encoding="utf-8")
    (tmp_path / "KB-contested-network-loss.json").write_text(json.dumps(contested), encoding="utf-8")

    retrieval = KnowledgeProvider().retrieve(project_id="sock-shop", candidate_space=_candidates(), root=tmp_path)
    ranked = rank_candidates(_candidates(), retrieval["cards"])

    assert [item["id"] for item in retrieval["cards"]] == ["KB-provisional-pod-kill"]
    assert ranked["candidate_ids"] == ["candidate:network_loss", "candidate:pod_kill"]
