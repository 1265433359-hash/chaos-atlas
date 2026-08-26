import pytest

from tools.evaluate_closed_loop_policy import evaluate_replay


def test_replay_reports_clusters_yield_and_stop_reasons():
    denominator = {
        "project_id": "demo",
        "seed": 1001,
        "candidates": [
            {"candidate_id": "c1", "causal_cluster_id": "cluster-1"},
            {"candidate_id": "c2", "causal_cluster_id": "cluster-1"},
        ],
    }
    decisions = [{"policy_selected_candidate_ids": ["c1"], "stop_reason": None}, {"policy_selected_candidate_ids": [], "stop_reason": "resolved"}]
    runtime = [{"candidate_id": "c1", "classification": "confirmed_weakness"}]
    result = evaluate_replay(denominator, decisions, runtime)
    assert result["unique_causal_clusters"] == 1
    assert result["confirmed_weakness_yield"] == 1
    assert result["stop_reasons"]["resolved"] == 1


def test_replay_rejects_out_of_denominator_selection():
    denominator = {"project_id": "demo", "seed": 1001, "candidates": []}
    with pytest.raises(ValueError, match="denominator"):
        evaluate_replay(denominator, [{"policy_selected_candidate_ids": ["unknown"]}], [])
