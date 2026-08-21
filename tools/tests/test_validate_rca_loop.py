from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.rca_loop import sha256_json
from tools.sock_shop_rca import build_sock_shop_pilot
from tools.validate_rca_loop import (
    validate_artifact,
    validate_action_plan,
    validate_case,
    validate_hypothesis,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
VERDICT_PATH = REPO_ROOT / "artifacts" / "sock-shop" / "sock_shop_verdicts.json"


@pytest.fixture()
def pilot_root(tmp_path: Path) -> Path:
    build_sock_shop_pilot(
        verdict_path=VERDICT_PATH,
        output_root=tmp_path / "rca_loop",
        project_commit="sock-shop-fixture-commit",
        round_id="pilot-r1",
    )
    return tmp_path / "rca_loop"


def _load_case(root: Path) -> dict:
    return json.loads(next(iter((root / "cases").glob("*.json"))).read_text(encoding="utf-8"))


def test_valid_pilot_artifact_passes(pilot_root: Path) -> None:
    report = validate_artifact(pilot_root, write_report=True)
    assert report["valid"] is True, report["errors"]
    assert report["errors"] == []
    assert (pilot_root / "validation_report.json").is_file()
    written = json.loads((pilot_root / "validation_report.json").read_text(encoding="utf-8"))
    assert written["valid"] is True


def test_case_missing_weakness_status_fails(pilot_root: Path) -> None:
    case = _load_case(pilot_root)
    del case["weakness_status"]
    errors = validate_case(case, pilot_root)
    assert any("weakness_status" in e for e in errors)


def test_case_with_absolute_source_ref_fails(pilot_root: Path) -> None:
    case = _load_case(pilot_root)
    case["evidence_refs"][0]["source_ref"] = "C:/secrets/catalogue.log"
    errors = validate_case(case, pilot_root)
    assert any("source_ref" in e for e in errors)


def test_test_node_with_absolute_source_ref_fails(pilot_root: Path) -> None:
    case = _load_case(pilot_root)
    case["test_node"]["source_ref"] = "C:/secrets/manifest.yaml"
    errors = validate_case(case, pilot_root)
    assert any("test_node" in e and "source_ref" in e for e in errors)


def test_validate_artifact_is_pure_by_default(pilot_root: Path) -> None:
    report = validate_artifact(pilot_root)
    assert report["valid"] is True
    assert not (pilot_root / "validation_report.json").exists()


def test_case_with_parent_escape_source_ref_fails(pilot_root: Path) -> None:
    case = _load_case(pilot_root)
    case["evidence_refs"][0]["source_ref"] = "../../etc/passwd"
    errors = validate_case(case, pilot_root)
    assert errors


def test_case_with_sensitive_value_fails(pilot_root: Path) -> None:
    case = _load_case(pilot_root)
    case["evidence_refs"][0]["interpretation"] = "password=hunter2 leaked in log"
    errors = validate_case(case, pilot_root)
    assert any("sensitive" in e for e in errors)


def test_case_with_unresolvable_source_ref_fails(pilot_root: Path) -> None:
    case = _load_case(pilot_root)
    case["evidence_refs"][0]["polarity"] = "supports"
    case["evidence_refs"][0]["source_ref"] = "artifacts/sock-shop/does_not_exist.json"
    errors = validate_case(case, pilot_root)
    assert any("unresolved" in e for e in errors)


def test_unavailable_evidence_must_not_support_bounded(pilot_root: Path) -> None:
    case = _load_case(pilot_root)
    for evidence in case["evidence_refs"]:
        evidence["polarity"] = "unavailable"
    errors = validate_case(case, pilot_root)
    assert any("bounded" in e for e in errors)


def test_confirmed_case_requires_complete_hypothesis_evidence(pilot_root: Path) -> None:
    case = _load_case(pilot_root)
    case["rca_status"] = "confirmed"
    for hypothesis in case.get("hypotheses", []):
        hypothesis["status"] = "confirmed"
        hypothesis["evidence_for"] = []
        hypothesis["unsupported_claims"] = list(hypothesis.get("required_evidence", []))

    errors = validate_case(case, pilot_root)

    assert any("confirmed" in error and "evidence" in error for error in errors)


def test_hypothesis_weakness_id_mismatch_fails(pilot_root: Path) -> None:
    case = _load_case(pilot_root)
    hypothesis = json.loads(
        next(iter((pilot_root / "hypotheses").glob("*.json"))).read_text(encoding="utf-8")
    )
    hypothesis["weakness_id"] = "WS-other"
    errors = validate_hypothesis(hypothesis, case)
    assert any("weakness_id" in e for e in errors)


def test_hypothesis_timeout_mechanism_without_source_evidence_fails(pilot_root: Path) -> None:
    case = _load_case(pilot_root)
    hypothesis = json.loads(
        next(iter((pilot_root / "hypotheses").glob("*.json"))).read_text(encoding="utf-8")
    )
    hypothesis["mechanism_class"] = "missing_timeout"
    hypothesis["mechanism_level"] = "source"
    errors = validate_hypothesis(hypothesis, case)
    assert any("timeout" in e for e in errors)


def test_hypothesis_with_source_evidence_may_claim_timeout(pilot_root: Path) -> None:
    case = _load_case(pilot_root)
    hypothesis = json.loads(
        next(iter((pilot_root / "hypotheses").glob("*.json"))).read_text(encoding="utf-8")
    )
    hypothesis["mechanism_class"] = "verified_missing_timeout"
    hypothesis["evidence_for"] = [case["evidence_refs"][0]["evidence_id"]]
    case["evidence_refs"][0]["kind"] = "source_span"
    case["evidence_refs"][0]["polarity"] = "supports"
    errors = validate_hypothesis(hypothesis, case)
    assert not any("timeout" in e for e in errors)


def test_hypothesis_missing_required_lists_fails(pilot_root: Path) -> None:
    case = _load_case(pilot_root)
    hypothesis = json.loads(
        next(iter((pilot_root / "hypotheses").glob("*.json"))).read_text(encoding="utf-8")
    )
    del hypothesis["falsifiers"]
    errors = validate_hypothesis(hypothesis, case)
    assert any("falsifiers" in e for e in errors)


def test_action_plan_selected_action_must_match_planner(pilot_root: Path) -> None:
    plan = json.loads((pilot_root / "action_plan.json").read_text(encoding="utf-8"))
    cases = [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted((pilot_root / "cases").glob("*.json"))
    ]
    plan["case_plans"][0]["plan"]["selected"]["action_id"] = "A-tampered"
    errors = validate_action_plan(plan, cases)
    assert any("selected" in e for e in errors)


def test_validate_artifact_detects_tampered_case(pilot_root: Path) -> None:
    case_path = next(iter((pilot_root / "cases").glob("*.json")))
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["evidence_refs"][0]["source_ref"] = "C:/abs/path.log"
    case_path.write_text(json.dumps(case, indent=2), encoding="utf-8")
    report = validate_artifact(pilot_root)
    assert report["valid"] is False
    assert report["errors"]


def test_manifest_records_input_hash(pilot_root: Path) -> None:
    manifest = json.loads((pilot_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["input"]["verdict_sha256"] == sha256_json(
        json.loads(VERDICT_PATH.read_text(encoding="utf-8"))
    )
    report = validate_artifact(pilot_root)
    assert report["valid"] is True
