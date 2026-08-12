from __future__ import annotations

from tools.summarize_p02_teacher_results import DEFAULT_INPUT, analyze


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
