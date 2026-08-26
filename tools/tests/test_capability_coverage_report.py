from __future__ import annotations

from tools.capability_coverage_report import build_report


def test_native_claim_requires_all_required_cells():
    report = build_report({"deployment_model": "verified", "hypothesis_generation": "verified", "scenario_compilation": "verified", "fault_execution": "verified", "ce_steady_state": "verified", "native_recovery": "verified", "attribution": "verified", "improvement_retest": "verified"}, {"execution": "not_run"})
    assert report["native_capability_coverage"]["claim"] == "full_native_capability"
    assert report["ce_profile_validation"]["cells"][0]["status"] == "not_run"


def test_blocked_native_cell_only_allows_partial_claim():
    report = build_report({"deployment_model": "verified", "hypothesis_generation": "blocked"})
    assert report["native_capability_coverage"]["claim"] == "partial_capability_coverage"

