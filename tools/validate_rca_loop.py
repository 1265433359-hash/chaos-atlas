"""Validator for RCA loop artifacts (cases, hypotheses, action plans).

Offline schema, path-boundary, sensitive-value and status-consistency checks.
It never modifies the artifacts it validates and never talks to a cluster,
container runtime, LLM or network.

Usage:
    python tools/validate_rca_loop.py --root artifacts/sock-shop/rca_loop
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.rca_loop import (
    RCA_STATES,
    _contains_sensitive_value,
    _path_errors,
    evaluate_rca_transition,
    plan_next_action,
)
from tools.sock_shop_rca import actions_for_case, hypotheses_for_case

ROOT = Path(__file__).resolve().parents[1]

_CASE_REQUIRED = (
    "schema_version",
    "weakness_id",
    "project_id",
    "project_commit",
    "round_id",
    "test_node",
    "symptom",
    "weakness_status",
    "rca_status",
    "knowledge_status",
    "evidence_refs",
    "hypothesis_ids",
    "next_actions",
)

_HYPOTHESIS_REQUIRED = (
    "hypothesis_id",
    "weakness_id",
    "claim",
    "mechanism_class",
    "expected_observations",
    "falsifiers",
    "required_evidence",
    "evidence_for",
    "evidence_against",
    "unsupported_claims",
    "status",
)

_TIMEOUT_MECHANISM_MARKERS = ("timeout",)

_DIRECT_MECHANISM_EVIDENCE_KINDS = {"source_span", "manifest", "config", "config_facts"}
_TIMEOUT_EVIDENCE_KINDS = {"source_span", "config", "config_facts"}


def _source_ref_errors(evidence: dict[str, Any]) -> list[str]:
    errors = [f"evidence {evidence.get('evidence_id')}: {detail}" for detail in _path_errors(evidence.get("source_ref"))]
    if _contains_sensitive_value(str(evidence.get("interpretation") or "")):
        errors.append(f"evidence {evidence.get('evidence_id')}: sensitive values in interpretation")
    if _contains_sensitive_value(str(evidence.get("source_ref") or "")):
        errors.append(f"evidence {evidence.get('evidence_id')}: sensitive values in source_ref")
    return errors


def _resolve_anchors(root: Path) -> list[Path]:
    return [root.resolve(), ROOT]


def _source_ref_unresolved(evidence: dict[str, Any], anchors: list[Path]) -> bool:
    ref = str(evidence.get("source_ref") or "")
    if not ref:
        return False
    return not any((anchor / ref).is_file() for anchor in anchors)


def validate_case(case: dict[str, Any], root: Path) -> list[str]:
    """Validate one RCA case artifact; returns a list of error strings."""

    errors: list[str] = []
    for field in _CASE_REQUIRED:
        if field not in case:
            errors.append(f"case {case.get('weakness_id', '<unknown>')}: missing field {field}")
    if case.get("weakness_status") not in {"candidate", "confirmed", "protected", "unsupported", "environment_blocked", "rejected"}:
        errors.append(f"case {case.get('weakness_id')}: invalid weakness_status {case.get('weakness_status')!r}")
    if case.get("rca_status") not in RCA_STATES:
        errors.append(f"case {case.get('weakness_id')}: invalid rca_status {case.get('rca_status')!r}")
    if case.get("knowledge_status") not in {"none", "provisional", "local_reusable", "cross_project_pending", "cross_project_reusable", "contested"}:
        errors.append(f"case {case.get('weakness_id')}: invalid knowledge_status {case.get('knowledge_status')!r}")

    anchors = _resolve_anchors(root)
    supports = 0
    for evidence in case.get("evidence_refs", []):
        errors.extend(_source_ref_errors(evidence))
        if evidence.get("polarity") == "supports":
            supports += 1
        if evidence.get("polarity") != "unavailable" and _source_ref_unresolved(evidence, anchors):
            errors.append(
                f"evidence {evidence.get('evidence_id')}: unresolved source_ref {evidence.get('source_ref')}"
            )

    if case.get("rca_status") == "bounded":
        boundary = bool(case.get("symptom"))
        transition = evaluate_rca_transition(
            current="pending",
            target="bounded",
            boundary_confirmed=boundary,
            supporting_evidence=supports,
            required_evidence_complete=False,
            discriminating_action=False,
            high_severity_contradiction=False,
        )
        if not transition["allowed"]:
            errors.append(
                f"case {case.get('weakness_id')}: rca_status=bounded not supported "
                f"({transition['reason']}; supports={supports})"
            )

    if _contains_sensitive_value(json.dumps(case, ensure_ascii=True)):
        errors.append(f"case {case.get('weakness_id')}: sensitive values detected")
    return errors


def validate_hypothesis(hypothesis: dict[str, Any], case: dict[str, Any]) -> list[str]:
    """Validate one hypothesis against its parent case."""

    errors: list[str] = []
    hid = hypothesis.get("hypothesis_id", "<unknown>")
    for field in _HYPOTHESIS_REQUIRED:
        if field not in hypothesis:
            errors.append(f"hypothesis {hid}: missing field {field}")
    if hypothesis.get("weakness_id") != case.get("weakness_id"):
        errors.append(f"hypothesis {hid}: weakness_id does not match case {case.get('weakness_id')}")
    if hypothesis.get("status") not in RCA_STATES:
        errors.append(f"hypothesis {hid}: invalid status {hypothesis.get('status')!r}")
    for list_field in ("expected_observations", "falsifiers", "required_evidence"):
        if not hypothesis.get(list_field):
            errors.append(f"hypothesis {hid}: {list_field} must not be empty")

    mechanism = str(hypothesis.get("mechanism_class") or "")
    level = str(hypothesis.get("mechanism_level") or "")
    if any(marker in mechanism.lower() for marker in _TIMEOUT_MECHANISM_MARKERS):
        # A timeout-named mechanism claim needs direct source/config evidence,
        # not a boundary-level symptom (spec section 6.3).
        direct = any(
            ev.get("kind") in _TIMEOUT_EVIDENCE_KINDS
            and ev.get("polarity") == "supports"
            and ev.get("evidence_id") in hypothesis.get("evidence_for", [])
            for ev in case.get("evidence_refs", [])
        )
        if not direct:
            errors.append(
                f"hypothesis {hid}: timeout-named mechanism {mechanism!r} has no "
                "source/config evidence; keep the claim at the service boundary"
            )
    if (
        hypothesis.get("status") in {"confirmed", "bounded"}
        and level in {"source", "service_internal"}
        and not hypothesis.get("evidence_for")
    ):
        errors.append(f"hypothesis {hid}: internal mechanism level without direct evidence")

    known_ids = {ev.get("evidence_id") for ev in case.get("evidence_refs", [])}
    for ref in list(hypothesis.get("evidence_for", [])) + list(hypothesis.get("evidence_against", [])):
        if ref not in known_ids:
            errors.append(f"hypothesis {hid}: unknown evidence reference {ref}")
    return errors


def validate_action_plan(plan: dict[str, Any], cases: list[dict[str, Any]]) -> list[str]:
    """Validate the action plan against the planner's deterministic selection."""

    errors: list[str] = []
    cases_by_id = {case.get("weakness_id"): case for case in cases}
    seen: set[str] = set()
    for entry in plan.get("case_plans", []):
        weak_id = entry.get("weakness_id")
        case = cases_by_id.get(weak_id)
        if case is None:
            errors.append(f"action plan references unknown case {weak_id}")
            continue
        seen.add(str(weak_id))
        sub_plan = entry.get("plan", {})
        actions = actions_for_case(case, hypotheses_for_case(case))
        recomputed = plan_next_action(
            actions,
            available_preconditions={
                "frozen_verdicts",
                "frozen_manifest",
                "captured_ready_samples",
                "captured_window",
            },
        )
        selected = sub_plan.get("selected") or {}
        if sub_plan.get("status") == "planned":
            if selected.get("action_id") != (recomputed.get("selected") or {}).get("action_id"):
                errors.append(
                    f"case {weak_id}: selected action {selected.get('action_id')!r} does not "
                    "match the deterministic planner output"
                )
            if not selected.get("cleanup"):
                errors.append(f"case {weak_id}: selected action lacks a cleanup contract")
            if not selected.get("output_schema"):
                errors.append(f"case {weak_id}: selected action lacks an output schema")
    for weak_id in cases_by_id:
        if weak_id not in seen:
            errors.append(f"action plan is missing a plan for case {weak_id}")
    return errors


def validate_artifact(root: Path) -> dict[str, Any]:
    """Validate the whole RCA artifact tree and write validation_report.json."""

    root = Path(root)
    errors: list[str] = []
    warnings: list[str] = []
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return {"valid": False, "errors": ["manifest.json is missing"], "warnings": []}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    cases: list[dict[str, Any]] = []
    for path in sorted((root / "cases").glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        cases.append(case)
        errors.extend(validate_case(case, root))
        for hypothesis in case.get("hypotheses", []):
            errors.extend(validate_hypothesis(hypothesis, case))
    if not cases:
        errors.append("no case artifacts found under cases/")

    for path in sorted((root / "hypotheses").glob("*.json")):
        hypothesis = json.loads(path.read_text(encoding="utf-8"))
        parent = next((c for c in cases if c.get("weakness_id") == hypothesis.get("weakness_id")), None)
        if parent is None:
            errors.append(f"hypothesis {hypothesis.get('hypothesis_id')}: no parent case")
        else:
            errors.extend(validate_hypothesis(hypothesis, parent))

    plan_path = root / "action_plan.json"
    if not plan_path.is_file():
        errors.append("action_plan.json is missing")
    else:
        errors.extend(validate_action_plan(json.loads(plan_path.read_text(encoding="utf-8")), cases))

    if manifest.get("knowledge_base_updated") is not False:
        warnings.append("manifest must keep knowledge_base_updated=false for provisional pilots")

    report = {"valid": not errors, "errors": errors, "warnings": warnings}
    (root / "validation_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    report = validate_artifact(args.root)
    for error in report["errors"]:
        print(f"ERROR: {error}", file=sys.stderr)
    for warning in report["warnings"]:
        print(f"WARNING: {warning}", file=sys.stderr)
    print(f"valid={report['valid']} errors={len(report['errors'])} warnings={len(report['warnings'])}")
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
