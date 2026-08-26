from __future__ import annotations

import copy

import pytest

from tools.project_runtime_projection import project_runtime_results


def candidate(candidate_id: str) -> dict:
    return {
        "candidate_id": candidate_id,
        "project_id": "online-boutique",
        "target": "cartservice",
        "fault_family": "pod_kill",
        "estimated_cost": 1.0,
    }


def report(candidate_id: str, replicate: int, classification: str = "weakness_observed") -> dict:
    return {
        "schema_version": "unified-lifecycle-v1",
        "project_id": "online-boutique",
        "mutation_id": candidate_id,
        "replicate": replicate,
        "status": "completed",
        "baseline": {"pass": True},
        "injection": {"applied": True, "injected": True},
        "observation": {"classification": classification},
        "recovery": {"recovered": True, "resource_recovered": True},
        "cleanup": {"absent_confirmed": True},
        "washout": {"stable": True},
        "errors": [],
        "eligibility": {"eligible": True},
        "_source_path": f"source-{replicate}.json",
        "_source_sha256": f"{replicate:x}" * 64,
    }


def test_projects_two_complete_weakness_replicates():
    result = project_runtime_results(
        [candidate("c1")],
        [report("c1", 1), report("c1", 2)],
        "online-boutique",
    )

    projected = result["runtime_results"]
    assert len(projected) == 1
    assert projected[0]["candidate_id"] == "c1"
    assert projected[0]["classification"] == "confirmed_weakness"
    assert projected[0]["source_classification"] == "weakness_observed"
    assert projected[0]["source_report_count"] == 2
    assert len(projected[0]["source_reports"]) == 2
    assert result["audit"]["source_report_count"] == 2


def test_rejects_unknown_candidate_and_incomplete_lifecycle():
    with pytest.raises(ValueError, match="unknown candidate"):
        project_runtime_results(
            [candidate("c1")],
            [report("other", 1), report("other", 2)],
            "online-boutique",
        )

    broken = copy.deepcopy(report("c1", 2))
    broken["cleanup"]["absent_confirmed"] = False
    with pytest.raises(ValueError, match="lifecycle"):
        project_runtime_results(
            [candidate("c1")],
            [report("c1", 1), broken],
            "online-boutique",
        )


def test_rejects_mixed_or_non_weakness_pairs():
    with pytest.raises(ValueError, match="weakness_observed"):
        project_runtime_results(
            [candidate("c1")],
            [report("c1", 1), report("c1", 2, "no_business_impact_observed")],
            "online-boutique",
        )


def test_rejects_duplicate_replicate_numbers():
    with pytest.raises(ValueError, match="duplicate replicate"):
        project_runtime_results(
            [candidate("c1")],
            [report("c1", 1), report("c1", 1)],
            "online-boutique",
        )
