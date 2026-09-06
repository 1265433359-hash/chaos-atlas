import json

from chaosatlas.capabilities.evidence import CapabilityEvidenceIndex


def _write_run(root, name, *, status="live_completed", cleanup="verified", valid=True, latency=100):
    run = root / name
    run.mkdir(parents=True)
    (run / "summary.json").write_text(json.dumps({"status": status, "run_id": name, "selected_candidate_ids": ["c1"]}), encoding="utf-8")
    (run / "cleanup_report.json").write_text(json.dumps({"status": cleanup}), encoding="utf-8")
    (run / "finding_report.json").write_text(json.dumps({"attestation": {"valid": valid}, "result": "failure_observed"}), encoding="utf-8")
    (run / "onboard.json").write_text(json.dumps({"profile": {"project_id": "p", "project_commit": "r"}}), encoding="utf-8")
    (run / "candidate_space.json").write_text(json.dumps({"candidates": [{"candidate_id": "c1", "target": "web", "fault_family": "pod_kill", "parameters": {"latency": latency}}]}), encoding="utf-8")


def test_valid_runtime_evidence_reaches_e2_and_three_identical_runs_reach_e3(tmp_path):
    _write_run(tmp_path, "run-1")
    index = CapabilityEvidenceIndex.from_root(tmp_path)
    assert index.lookup(project_id="p", project_revision="r", target="web", fault_id="pod_kill")["evidence_grade"] == "E2"
    _write_run(tmp_path, "run-2")
    _write_run(tmp_path, "run-3")
    index = CapabilityEvidenceIndex.from_root(tmp_path)
    result = index.lookup(project_id="p", project_revision="r", target="web", fault_id="pod_kill")
    assert result["evidence_grade"] == "E3"
    assert result["stable_reproduction_count"] == 3


def test_invalid_or_different_parameter_runs_do_not_upgrade_the_same_identity(tmp_path):
    _write_run(tmp_path, "bad-cleanup", cleanup="failed")
    _write_run(tmp_path, "bad-attestation", valid=False)
    _write_run(tmp_path, "one", latency=100)
    _write_run(tmp_path, "two", latency=200)
    index = CapabilityEvidenceIndex.from_root(tmp_path)
    result = index.lookup(project_id="p", project_revision="r", target="web", fault_id="pod_kill")
    assert result["evidence_grade"] == "E2"
    assert result["stable_reproduction_count"] == 1


def test_missing_or_damaged_evidence_is_a_warning_not_an_exception(tmp_path):
    (tmp_path / "summary.json").write_text("not-json", encoding="utf-8")
    index = CapabilityEvidenceIndex.from_root(tmp_path)
    assert index.warnings
    assert CapabilityEvidenceIndex.from_root(tmp_path / "missing").warnings


def test_nested_run_requires_verified_outer_isolation_cleanup(tmp_path):
    partial_root = tmp_path / "partial-isolation"
    _write_run(partial_root / "run" / "runs", "partial-candidate")
    (partial_root / "isolation-lifecycle.json").write_text(json.dumps({
        "status": "partial",
        "cleanup_state": "cleanup_failed",
    }), encoding="utf-8")

    verified_root = tmp_path / "verified-isolation"
    _write_run(verified_root / "run" / "runs", "verified-candidate")
    (verified_root / "isolation-lifecycle.json").write_text(json.dumps({
        "status": "verified",
        "cleanup_state": "released",
    }), encoding="utf-8")

    index = CapabilityEvidenceIndex.from_root(tmp_path)
    result = index.lookup(project_id="p", project_revision="r", target="web", fault_id="pod_kill")

    assert result["valid_run_count"] == 1
    assert any("outer isolation lifecycle" in warning for warning in index.warnings)
