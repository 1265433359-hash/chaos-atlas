from __future__ import annotations

import hashlib
from pathlib import Path

from tools.unified_experiment_protocol import (
    REQUIRED_LIFECYCLE_FIELDS,
    comparison_eligibility,
    validate_lifecycle_report,
)


def valid_report(mutation_path: Path | None = None) -> dict:
    mutation_path = mutation_path or Path("mutation.yaml")
    return {
        "schema_version": "unified-lifecycle-v1",
        "project_id": "P09",
        "namespace": "chaosatlas-p09",
        "arm": "P09-unified",
        "mutation_id": "api-pod-kill",
        "replicate": 1,
        "mutation": {
            "path": str(mutation_path),
            "sha256": "a" * 64,
        },
        "baseline": {"pass": True},
        "injection": {"applied": True, "injected": True},
        "observation": {"samples": [{"status_code": 200}]},
        "recovery": {"recovered": True},
        "cleanup": {"absent_confirmed": True, "residual_resources": []},
        "washout": {"stable": True},
        "diagnostics": {"status": "not_configured"},
        "human_review": "pending",
        "status": "completed",
    }


def test_completed_report_requires_all_lifecycle_sections() -> None:
    report = {
        "status": "completed",
        "human_review": "pending",
        "baseline": {"pass": True},
        "injection": {"applied": True},
        "recovery": {"recovered": True},
        "cleanup": {"absent_confirmed": True, "residual_resources": []},
        "washout": {"stable": True},
    }

    result = validate_lifecycle_report(report)

    assert result["valid"] is False
    assert "schema_version" in result["errors"]
    assert comparison_eligibility(report)["eligible"] is False


def test_completed_report_is_comparison_eligible_when_all_checks_pass(tmp_path: Path) -> None:
    mutation = tmp_path / "mutation.yaml"
    mutation.write_bytes(b"apiVersion: chaos-mesh.org/v1alpha1\n")
    report = valid_report(mutation)
    report["mutation"]["sha256"] = hashlib.sha256(mutation.read_bytes()).hexdigest()

    result = validate_lifecycle_report(report)

    assert result["valid"] is True
    assert comparison_eligibility(report) == {"eligible": True, "reasons": []}


def test_failed_injection_is_not_comparison_eligible(tmp_path: Path) -> None:
    mutation = tmp_path / "mutation.yaml"
    mutation.write_bytes(b"mutation\n")
    report = valid_report(mutation)
    report["mutation"]["sha256"] = hashlib.sha256(mutation.read_bytes()).hexdigest()
    report["injection"]["applied"] = False

    result = comparison_eligibility(report)

    assert result["eligible"] is False
    assert "injection.applied" in result["reasons"]


def test_unconfirmed_injection_is_not_comparison_eligible(tmp_path: Path) -> None:
    mutation = tmp_path / "mutation.yaml"
    mutation.write_bytes(b"mutation\n")
    report = valid_report(mutation)
    report["mutation"]["sha256"] = hashlib.sha256(mutation.read_bytes()).hexdigest()
    report["injection"]["injected"] = False

    result = comparison_eligibility(report)

    assert result["eligible"] is False
    assert "injection.injected" in result["reasons"]


def test_residual_chaos_blocks_comparison(tmp_path: Path) -> None:
    mutation = tmp_path / "mutation.yaml"
    mutation.write_bytes(b"mutation\n")
    report = valid_report(mutation)
    report["mutation"]["sha256"] = hashlib.sha256(mutation.read_bytes()).hexdigest()
    report["cleanup"]["residual_resources"] = [
        {"kind": "PodChaos", "name": "leftover"}
    ]

    result = comparison_eligibility(report)

    assert result["eligible"] is False
    assert "cleanup.residual_resources" in result["reasons"]


def test_mutation_hash_must_match_file_bytes(tmp_path: Path) -> None:
    mutation = tmp_path / "mutation.yaml"
    mutation.write_bytes(b"apiVersion: chaos-mesh.org/v1alpha1\n")
    report = valid_report(mutation)
    report["mutation"]["sha256"] = "0" * 64

    result = validate_lifecycle_report(report)

    assert result["valid"] is False
    assert "mutation.sha256" in result["errors"]


def test_required_fields_are_explicit_and_stable() -> None:
    assert REQUIRED_LIFECYCLE_FIELDS == (
        "schema_version",
        "project_id",
        "namespace",
        "arm",
        "mutation_id",
        "replicate",
        "mutation",
        "baseline",
        "injection",
        "observation",
        "recovery",
        "cleanup",
        "washout",
        "diagnostics",
        "human_review",
        "status",
    )
