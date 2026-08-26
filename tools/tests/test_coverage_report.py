from __future__ import annotations

import json
from pathlib import Path

from tools.coverage_report import build_coverage_report


def _write(root: Path, name: str, payload: dict) -> None:
    path = root / name / "rca.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"claim_scope": "runtime", "payload": payload}), encoding="utf-8")


def _payload(*, family: str, weakness: str, cleanup: str = "verified", rca: str = "confirmed") -> dict:
    return {
        "project_id": "demo",
        "claim_scope": "runtime",
        "rca_status": rca,
        "weakness_id": weakness,
        "test_node": {"target": "api", "target_kind": "deployment", "family": family},
        "hypotheses": [{"scope": {"edge": "deployment:api"}}],
        "symptom": {"oracle": "HTTP / on api"},
        "cleanup_status": cleanup,
        "attestation": {"baseline": True, "injection": True, "observation": True, "recovery": True, "cleanup": cleanup == "verified", "independent_oracle": True, "valid": cleanup == "verified"},
    }


def test_coverage_report_separates_runs_weaknesses_and_problem_surfaces(tmp_path: Path):
    _write(tmp_path, "r1", _payload(family="pod_kill", weakness="WS-1"))
    _write(tmp_path, "r2", _payload(family="container_kill", weakness="WS-2"))
    _write(tmp_path, "r3", _payload(family="pod_kill", weakness="WS-1"))
    _write(tmp_path, "blocked", _payload(family="network_loss", weakness="WS-3", cleanup="blocked"))

    report = build_coverage_report(tmp_path)

    assert report["artifact_count"] == 4
    assert report["eligible_run_count"] == 3
    assert report["confirmed_weakness_count"] == 2
    assert report["independent_problem_count"] == 1
    assert report["projects"]["demo"]["families"] == ["container_kill", "pod_kill"]
    assert report["families"]["pod_kill"]["eligible_run_count"] == 2
    assert report["families"]["container_kill"]["eligible_run_count"] == 1


def test_coverage_report_ignores_malformed_json(tmp_path: Path):
    path = tmp_path / "bad" / "rca.json"
    path.parent.mkdir()
    path.write_text("not-json", encoding="utf-8")

    report = build_coverage_report(tmp_path)

    assert report["artifact_count"] == 1
    assert report["parse_error_count"] == 1
    assert report["eligible_run_count"] == 0
