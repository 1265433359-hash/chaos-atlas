from __future__ import annotations

from tools.open_discovery_evaluator import evaluate_compiled, summarize_projects


def test_evaluator_separates_known_novel_and_protected() -> None:
    compiled = {
        "status": "valid",
        "accepted": [
            {"project_id": "P02", "canonical_signature": "known", "novelty": "known_candidate", "target": "api", "fault_family": "network_delay"},
            {"project_id": "P02", "canonical_signature": "novel", "novelty": "novel_candidate", "target": "db", "fault_family": "network_loss"},
        ],
        "rejected_count": 0,
    }
    evidence = {
        "known": {"oracle_label": "protected", "evidence": {"independent_oracle": True, "observation": True}},
        "novel": {"oracle_label": "weakness", "valid_reproductions": 2, "evidence": {key: True for key in ("baseline", "injection", "observation", "recovery", "cleanup", "independent_oracle")}},
    }
    result = evaluate_compiled(compiled, evidence)
    assert result["confirmed_weaknesses"] == 1
    assert result["novel_issue_yield"] == 1
    assert result["protected_waste"] == 0.5


def test_summary_is_project_seed_grouped() -> None:
    result = summarize_projects([{"project_id": "P02", "arm": "A", "valid_hypotheses": 2, "confirmed_weaknesses": 1, "unique_issue_yield": 1, "novel_issue_yield": 0, "protected_waste": 0.5, "evidence_completeness": 1.0}, {"project_id": "P02", "arm": "A", "valid_hypotheses": 1, "confirmed_weaknesses": 0, "unique_issue_yield": 0, "novel_issue_yield": 0, "protected_waste": 0.0, "evidence_completeness": 0.0}])
    assert result[0]["seeds"] == 2
    assert result[0]["unit_of_analysis"].startswith("project_seed_group")


def test_unique_issue_yield_uses_oracle_issue_id_not_target_name() -> None:
    compiled = {"status": "valid", "accepted": [{"project_id": "P02", "canonical_signature": "a", "novelty": "novel_candidate", "target": "api", "fault_family": "network_delay"}, {"project_id": "P02", "canonical_signature": "b", "novelty": "novel_candidate", "target": "api", "fault_family": "network_loss"}], "rejected_count": 0}
    valid = {"oracle_label": "weakness", "valid_reproductions": 2, "evidence": {key: True for key in ("baseline", "injection", "observation", "recovery", "cleanup", "independent_oracle")}}
    result = evaluate_compiled(compiled, {"a": {**valid, "issue_id": "issue-a"}, "b": {**valid, "issue_id": "issue-b"}})
    assert result["unique_issue_yield"] == 2
