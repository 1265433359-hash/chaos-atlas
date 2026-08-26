from __future__ import annotations

import json
import tempfile
from pathlib import Path

from tools.chaosatlas_hypothesis import build_hypothesis_input
from tools.phase32_knowledge_replay import _load_run, compare_runs


def test_load_run_normalizes_knowledge_consumption_alias() -> None:
    with tempfile.TemporaryDirectory(dir=Path.cwd()) as raw_root:
        root = Path(raw_root)
        for name, payload in {
            "summary.json": {"status": "dry_run_ready"},
            "retrieval.json": {},
            "knowledge_consumption.json": {"accepted_card_ids": []},
            "hypotheses.json": {},
            "evidence_plan.json": {},
            "regression_intents.json": {},
        }.items():
            (root / name).write_text(json.dumps(payload), encoding="utf-8")

        loaded = _load_run(root)

    assert "consumption" in loaded
    assert "knowledge_consumption" not in loaded
    assert "regression" in loaded
    assert "regression_intents" not in loaded


def test_hypothesis_input_removes_final_runtime_status_fields_from_knowledge_view() -> None:
    result = build_hypothesis_input(
        {"project_id": "demo"},
        {"status": "verified"},
        {"candidates": []},
        [{"id": "KB-1", "knowledge_status": "local_reusable", "classification": "availability_weakness", "rca_status": "confirmed", "hypothesis": "singleton risk"}],
    )

    view = result["knowledge_view"][0]
    assert view["id"] == "KB-1"
    assert view["hypothesis"] == "singleton risk"
    assert "knowledge_status" not in view
    assert "classification" not in view
    assert "rca_status" not in view
    assert "status" not in view


def test_compare_runs_records_knowledge_driven_priority_and_boundaries() -> None:
    with_run = {
        "summary": {"status": "dry_run_ready", "claim_scope": "static/synthetic"},
        "retrieval": {"cards": [{"id": "KB-POD", "knowledge_status": "local_reusable"}], "rejected_cards": []},
        "consumption": {"accepted_card_ids": ["KB-POD"], "rejected_card_ids": [], "claim_scope": "static"},
        "hypotheses": {"candidate_ids": ["checkout:pod_kill", "cart:container_kill"], "claim_scope": "advisory", "input": {"knowledge_view": [{"id": "KB-POD", "hypothesis": "singleton risk"}]}},
        "evidence_plan": {"selection": {"candidate_ids": ["checkout:pod_kill"]}, "claim_scope": "advisory"},
        "regression": {"intents": [{"candidate_id": "checkout:pod_kill", "executable": False}], "claim_scope": "synthetic"},
    }
    without_run = {
        "summary": {"status": "dry_run_ready", "claim_scope": "static/synthetic"},
        "retrieval": {"cards": [], "rejected_cards": []},
        "consumption": {"accepted_card_ids": [], "rejected_card_ids": [], "claim_scope": "static"},
        "hypotheses": {"candidate_ids": ["cart:container_kill", "checkout:pod_kill"], "claim_scope": "advisory"},
        "evidence_plan": {"selection": {"candidate_ids": ["cart:container_kill"]}, "claim_scope": "advisory"},
        "regression": {"intents": [{"candidate_id": "cart:container_kill", "executable": False}], "claim_scope": "synthetic"},
    }

    report = compare_runs(
        with_run,
        without_run,
        boundary={"accepted_card_ids": ["KB-POD"], "rejected_card_ids": ["KB-FOREIGN"], "rejection_reasons": {"project_mismatch": 1}},
        commit_boundary={"accepted_card_ids": [], "rejected_card_ids": ["KB-POD"], "rejection_reasons": {"project_commit_mismatch": 1}},
    )

    assert report["status"] == "passed"
    assert report["knowledge"]["accepted_count"] == 1
    assert report["comparison"]["top_candidate_changed"] is True
    assert report["comparison"]["evidence_selection_changed"] is True
    assert report["boundaries"]["cross_project_rejected"] is True
    assert report["boundaries"]["commit_mismatch_rejected"] is True
    assert report["safety"]["live_triggered"] is False
