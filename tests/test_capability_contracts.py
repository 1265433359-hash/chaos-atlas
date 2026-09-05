import pytest

from chaosatlas.capabilities.contracts import (
    aggregate_capability_status,
    canonical_catalog_ids,
    normalize_capability_status,
    strongest_evidence_grade,
    validate_capability_record,
    validate_catalog_coverage,
)


def test_catalog_contract_contains_exactly_32_core_and_9_extensions():
    core, extensions = canonical_catalog_ids()
    assert len(core) == len(set(core)) == 32
    assert len(extensions) == len(set(extensions)) == 9
    assert set(core).isdisjoint(extensions)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("blocked_by_platform_prerequisite", "blocked"),
        ("not_reachable", "blocked"),
        ("supported", "supported"),
        ("canary_required", "canary_required"),
        ("blocked", "blocked"),
        ("unsupported", "unsupported"),
        ("inapplicable", "inapplicable"),
    ],
)
def test_status_normalization_preserves_original(raw, expected):
    assert normalize_capability_status(raw) == (expected, raw)


def test_status_and_evidence_order_are_explicit():
    assert aggregate_capability_status(["blocked", "supported", "inapplicable"]) == "supported"
    assert strongest_evidence_grade(["E0", "E3", "E1"]) == "E3"
    with pytest.raises(ValueError, match="cannot originate"):
        strongest_evidence_grade(["E2"], discovery_only=True)
    with pytest.raises(ValueError, match="unknown evidence"):
        strongest_evidence_grade(["E9"])


def test_record_and_aggregate_coverage_validation_fail_closed():
    record = {
        "project_id": "p",
        "project_revision": "r",
        "fault_id": "pod_kill",
        "catalog_scope": "core",
        "capability_status": "blocked",
        "evidence_grade": "E0",
        "risk_level": "medium",
        "required_isolation": "L1",
        "reason_code": "missing",
        "reason": "missing prerequisite",
        "candidate_eligible": False,
        "prerequisites": [],
        "oracle_ids": [],
        "evidence_refs": [],
    }
    assert validate_capability_record(record) == []
    assert validate_catalog_coverage([{"fault_id": "pod_kill"}])
