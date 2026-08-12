from __future__ import annotations

import json
from pathlib import Path

from tools.summarize_p02_teacher_results import DEFAULT_INPUT, analyze, build_review_pack


def test_r2_evidence_is_complete_but_not_head_to_head_eligible() -> None:
    result = analyze(DEFAULT_INPUT)

    assert result["batch"] == {
        "status": "completed",
        "declared_runs": 15,
        "completed_runs": 15,
        "observed_reports": 15,
        "all_technically_valid": True,
    }
    assert result["comparison"]["runtime_head_to_head_eligible"] is False


def test_detects_identical_ablation_outputs_and_adapter_subset() -> None:
    result = analyze(DEFAULT_INPUT)
    comparison = result["comparison"]

    assert comparison["kb_vs_nokb_candidate_signatures_equal"] is True
    assert comparison["adapter_executable_signatures_subset_of_chaosatlas"] is True
    assert result["arms"]["ChaosAtlas-KB-open"]["targets"] == ["api-gateway", "discovery-server"]


def test_detects_reproducible_delayed_discovery_carryover() -> None:
    result = analyze(DEFAULT_INPUT)
    issue = next(item for item in result["issues"] if item["issue_id"] == "P02-ISSUE-002")

    assert issue["reproductions"] == 3
    assert issue["classification"] == "confirmed_delayed_business_outage_root_cause_pending"
    assert sorted(event["pre_injection_http_500"] for event in issue["events"]) == [8, 9, 37]


def _write_r3_report(root: Path, arm: str, washout_500: int) -> None:
    path = root / arm / "mutation-1" / "rep-1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = [{"status_code": 500}] * washout_500 + [{"status_code": 200}] * 10
    report = {
        "status": "completed",
        "started_at": "2026-08-13T00:00:00+00:00",
        "finished_at": "2026-08-13T00:02:00+00:00",
        "errors": [],
        "warnings": [],
        "experiment": {"arm": arm, "mutation_id": "mutation-1", "replicate": 1},
        "target": {"labels": {"app.kubernetes.io/name": "discovery-server"}},
        "baseline": [{"status_code": 200}] * 5,
        "requests": [{"status_code": 200}],
        "diagnostics": {"zipkin": {"status": "captured"}},
        "lifecycle": {
            "injected": True,
            "recovered": True,
            "post_recovery_http_200_count": 1,
            "cleanup": {"absent_confirmed": True},
            "post_cleanup_residual_chaos": [],
            "post_cleanup_washout": {
                "samples": samples,
                "non_200": washout_500,
                "http_500": washout_500,
                "stable": True,
            },
        },
    }
    path.write_text(json.dumps(report), encoding="utf-8")


def test_r3_attributes_delayed_failure_to_same_run_washout(tmp_path) -> None:
    arms = ["ChaosAtlas-KB-open", "ChaosAtlas-noKB-open", "ChaosEater-adapter-open"]
    (tmp_path / "batch-manifest.json").write_text(
        json.dumps({"status": "completed", "run_count": 3, "completed_runs": 3}),
        encoding="utf-8",
    )
    for index, arm in enumerate(arms, start=1):
        _write_r3_report(tmp_path, arm, washout_500=index)

    result = analyze(tmp_path)
    issue = next(item for item in result["issues"] if item["issue_id"] == "P02-ISSUE-002")

    assert result["delayed_effect_attribution"] == "same_run_post_cleanup_washout"
    assert result["comparison"]["execution_sequence_eligible"] is True
    assert result["comparison"]["runtime_head_to_head_eligible"] is False
    assert [event["post_cleanup_http_500"] for event in issue["events"]] == [1, 2, 3]
    assert all("next_run" not in event for event in issue["events"])
    assert result["input"] == str(tmp_path.resolve().relative_to(Path.cwd().resolve())).replace("\\", "/")


def test_review_pack_stays_pending_and_does_not_apply_knowledge() -> None:
    pack = build_review_pack(analyze(DEFAULT_INPUT))

    assert pack["status"] == "pending_human_review"
    assert pack["knowledge_update_applied"] is False
    assert all(item["human_decision"] == "pending" for item in pack["decisions"])
