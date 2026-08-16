import hashlib
import json
from pathlib import Path

from tools.verify_two_arm_runtime import verify_reports


def test_verifier_resolves_reports_across_roots_and_checks_diagnostic_hashes(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    diagnostic = second / "diag.log"
    diagnostic.parent.mkdir(parents=True)
    diagnostic.write_text("ok\n", encoding="utf-8")
    mutation = second / "mutation.yaml"
    mutation.write_text("kind: PodChaos\n", encoding="utf-8")
    report = {
        "project_id": "demo",
        "seed": 1001,
        "arm": "ChaosAtlas-full",
        "mutation_id": "H1",
        "replicate": 1,
        "status": "completed",
        "mutation": {"path": str(mutation), "sha256": hashlib.sha256(mutation.read_bytes()).hexdigest()},
        "baseline": {"pass": True},
        "injection": {"applied": True, "injected": True},
        "recovery": {"recovered": True},
        "cleanup": {"absent_confirmed": True, "residual_resources": []},
        "washout": {"stable": True},
        "diagnostics": {"status": "captured", "files": [{"path": str(diagnostic), "sha256": hashlib.sha256(diagnostic.read_bytes()).hexdigest()}]},
        "human_review": "pending",
        "knowledge_base_updated": False,
    }
    report_path = second / "project" / "report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(json.dumps(report), encoding="utf-8")
    result = verify_reports([first, second], expected=1)
    assert result["status"] == "passed"
    assert result["reports"] == 1
    assert result["report_evidence"] == [
        {
            "path": str(report_path).replace("\\", "/"),
            "sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
            "project_id": "demo",
            "seed": 1001,
            "method": "ChaosAtlas-full",
            "mutation_id": "H1",
            "replicate": 1,
            "classification": "missing",
            "lifecycle_valid": True,
        }
    ]


def test_verifier_prefers_completed_duplicate_and_rejects_mutation_hash_mismatch(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    mutation = second / "mutation.yaml"
    mutation.parent.mkdir(parents=True)
    mutation.write_text("kind: PodChaos\n", encoding="utf-8")
    diagnostic = second / "diag.log"
    diagnostic.write_text("ok\n", encoding="utf-8")
    base = {
        "project_id": "demo",
        "seed": 1001,
        "arm": "ChaosAtlas-full",
        "mutation_id": "H1",
        "replicate": 1,
        "baseline": {"pass": True},
        "injection": {"applied": True, "injected": True},
        "recovery": {"recovered": True},
        "cleanup": {"absent_confirmed": True, "residual_resources": [], "global_scan_errors": []},
        "washout": {"stable": True},
        "mutation": {"path": str(mutation), "sha256": "0" * 64},
        "diagnostics": {"status": "captured", "files": [{"path": str(diagnostic), "sha256": hashlib.sha256(diagnostic.read_bytes()).hexdigest()}]},
        "human_review": "pending",
        "knowledge_base_updated": False,
    }
    failed = first / "report.json"
    failed.parent.mkdir(parents=True)
    failed.write_text(json.dumps({**base, "status": "failed"}), encoding="utf-8")
    completed = second / "report.json"
    completed.write_text(json.dumps({**base, "status": "completed"}), encoding="utf-8")

    result = verify_reports([first, second], expected=1)

    assert result["reports"] == 1
    assert result["status"] == "failed"
    assert any(reason.startswith("mutation_sha256:") for failure in result["failures"] for reason in failure["reasons"])
    assert all("status" not in failure["reasons"] for failure in result["failures"])
