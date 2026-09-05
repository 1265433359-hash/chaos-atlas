from scripts import run_dify_k8s_repeated_coverage as runner
import json


def test_candidate_selection_is_balanced_across_fault_families(monkeypatch):
    candidates = [
        {"candidate_id": "t1-a", "target": "t1", "fault_family": "a"},
        {"candidate_id": "t1-b", "target": "t1", "fault_family": "b"},
        {"candidate_id": "t2-a", "target": "t2", "fault_family": "a"},
        {"candidate_id": "t2-b", "target": "t2", "fault_family": "b"},
    ]
    monkeypatch.setattr(
        runner,
        "build_live_batch_plan",
        lambda **_: {"candidates": candidates},
    )
    monkeypatch.setattr(runner, "KubernetesProjectAdapter", lambda **_: object())

    profile = {"runtime_contract": {"supported_fault_families": ["a", "b"]}}
    result = runner._candidate_list(profile, "test-context", "all")

    assert [item["candidate_id"] for item in result] == ["t1-a", "t1-b", "t2-a", "t2-b"]


def test_hypothesis_budget_limits_unique_candidates_without_changing_repetitions():
    candidates = [
        {"candidate_id": "a"},
        {"candidate_id": "a"},
        {"candidate_id": "b"},
        {"candidate_id": "c"},
    ]

    selected = runner._select_candidates(candidates, 2)

    assert [item["candidate_id"] for item in selected] == ["a", "b"]
    assert len(selected) * 3 == 6


def test_hypothesis_budget_rejects_non_positive_values():
    try:
        runner._select_candidates([], 0)
    except ValueError as exc:
        assert str(exc) == "hypothesis budget must be positive"
    else:
        raise AssertionError("expected a positive hypothesis budget error")


def test_completed_trial_is_reused_only_with_verified_cleanup(tmp_path):
    trial_root = tmp_path / "trial"
    attempt = trial_root / "attempt-01"
    attempt.mkdir(parents=True)
    (attempt / "summary.json").write_text(json.dumps({"status": "live_completed"}))
    (attempt / "cleanup_report.json").write_text(json.dumps({"status": "verified"}))
    (attempt / "execute.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "payload": {
                    "phases": [
                        {
                            "faults": [
                                {
                                    "attestation": {
                                        key: True
                                        for key in (
                                            "baseline",
                                            "injection",
                                            "observation",
                                            "recovery",
                                            "cleanup",
                                            "independent_oracle",
                                            "comparison_eligible",
                                        )
                                    }
                                }
                            ]
                        }
                    ]
                },
            }
        )
    )

    result = runner._load_completed_trial(
        trial_root,
        hypothesis_index=1,
        family="pod_kill",
        target="api",
        repetition=1,
        candidate_id="candidate",
    )

    assert result is not None
    assert result["resumed"] is True
    assert result["attempt"] == 1


def test_completed_trial_is_not_reused_when_recovery_is_unconfirmed(tmp_path):
    trial_root = tmp_path / "trial"
    attempt = trial_root / "attempt-01"
    attempt.mkdir(parents=True)
    (attempt / "summary.json").write_text(json.dumps({"status": "live_completed"}))
    (attempt / "cleanup_report.json").write_text(json.dumps({"status": "verified"}))
    (attempt / "execute.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "payload": {
                    "phases": [
                        {
                            "faults": [
                                {
                                    "attestation": {
                                        "baseline": True,
                                        "injection": True,
                                        "observation": True,
                                        "recovery": False,
                                        "cleanup": True,
                                        "independent_oracle": True,
                                        "comparison_eligible": False,
                                    }
                                }
                            ]
                        }
                    ]
                },
            }
        )
    )

    assert runner._load_completed_trial(
        trial_root,
        hypothesis_index=1,
        family="stress_cpu",
        target="api",
        repetition=1,
        candidate_id="candidate",
    ) is None
