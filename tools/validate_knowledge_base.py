"""Validate test-node-centered knowledge cards before LLM retrieval or injection."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    from project_onboarding import validate_project_profile
except ImportError:  # pragma: no cover - supports package imports
    from tools.project_onboarding import validate_project_profile


REQUIRED_CARD_FIELDS = {
    "id",
    "version",
    "status",
    "evidence_state",
    "project",
    "project_commit",
    "test_node",
    "test_node_centered_graph",
    "four_layer_validation",
    "next_evidence",
}
REQUIRED_TEST_NODE_FIELDS = {"family", "operation", "source_yaml"}
FORBIDDEN_VALUE_PATTERNS = [
    re.compile(r"(?i)(password|passwd|secret|token)\s*[:=]\s*[^$<{\[]+"),
    re.compile(r"(?i)AKIA[0-9A-Z]{16}"),
]


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def walk_strings(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from walk_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_strings(child)
    elif isinstance(value, str):
        yield value


NEW_REQUIRED_CARD_FIELDS = {
    "schema_version",
    "id",
    "project",
    "project_commit",
    "case_family",
    "weakness_id",
    "target",
    "target_kind",
    "classification",
    "weakness_status",
    "rca_status",
    "knowledge_status",
    "mechanism_level",
    "mechanism_claim",
    "test_node",
    "applicability_conditions",
    "exclusion_conditions",
    "evidence_runs",
    "valid_reproductions",
    "counter_evidence",
    "promotion_audit",
    "next_evidence",
    "stop_rule",
    "regression_intents",
}


def _validate_flat_weakness_root(
    root: Path,
    *,
    expected_project: str | None = None,
    expected_commit: str | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    card_checks: list[dict[str, Any]] = []
    paths = sorted(root.glob("KB-*.json"))
    if not paths:
        errors.append(f"missing flat weakness cards under {root}")
    seen_ids: set[str] = set()
    for path in paths:
        card_id = path.stem
        start_error = len(errors)
        start_warning = len(warnings)
        try:
            card = load_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{card_id}: invalid JSON: {exc}")
            card = {}
        if not isinstance(card, dict):
            errors.append(f"{card_id}: card must be an object")
            card = {}
        missing = sorted(NEW_REQUIRED_CARD_FIELDS - set(card))
        if missing:
            errors.append(f"{card_id}: missing card fields {missing}")
        if card.get("schema_version") != "chaosatlas-weakness-knowledge-v1":
            errors.append(f"{card_id}: schema_version must be chaosatlas-weakness-knowledge-v1")
        actual_id = card.get("id")
        if actual_id in seen_ids:
            errors.append(f"{card_id}: duplicate card id")
        if actual_id:
            seen_ids.add(str(actual_id))
            if str(actual_id) != card_id:
                errors.append(f"{card_id}: card.id does not match filename")
        if expected_project is not None and card.get("project") != expected_project:
            errors.append(f"{card_id}: project_mismatch expected {expected_project!r}, got {card.get('project')!r}")
        if expected_commit is not None and card.get("project_commit") != expected_commit:
            errors.append(f"{card_id}: project_commit_mismatch expected {expected_commit!r}, got {card.get('project_commit')!r}")
        test_node = card.get("test_node")
        if not isinstance(test_node, dict) or not test_node.get("family") or not test_node.get("operation"):
            errors.append(f"{card_id}: test_node must contain family and operation")
        runs = card.get("evidence_runs")
        if not isinstance(runs, list) or len(runs) < 2:
            errors.append(f"{card_id}: evidence_runs must contain at least two independent runs")
            runs = []
        else:
            run_ids = [str(item.get("run_id")) for item in runs if isinstance(item, dict) and item.get("run_id")]
            fingerprints = [str(item.get("run_fingerprint")) for item in runs if isinstance(item, dict) and item.get("run_fingerprint")]
            if len(run_ids) != len(set(run_ids)):
                errors.append(f"{card_id}: evidence run_id values must be distinct")
            if len(fingerprints) != len(set(fingerprints)):
                errors.append(f"{card_id}: evidence run_fingerprint values must be distinct")
            if len(run_ids) < 2 or len(fingerprints) < 2:
                errors.append(f"{card_id}: each evidence run needs run_id and run_fingerprint")
        if card.get("rca_status") != "confirmed":
            errors.append(f"{card_id}: rca_status must be confirmed")
        promotion = card.get("promotion_audit")
        if not isinstance(promotion, dict) or promotion.get("allowed") is not True:
            errors.append(f"{card_id}: promotion_audit.allowed must be true")
        if not isinstance(card.get("next_evidence"), list) or not card["next_evidence"]:
            errors.append(f"{card_id}: next_evidence must be a non-empty list")
        if not isinstance(card.get("regression_intents"), list) or not card["regression_intents"]:
            errors.append(f"{card_id}: regression_intents must be a non-empty list")
        for string in walk_strings(card):
            for pattern in FORBIDDEN_VALUE_PATTERNS:
                if pattern.search(string) and string not in {"secrets", "redaction"}:
                    warnings.append(f"{card_id}: review possible sensitive value in {string[:120]!r}")
                    break
        card_checks.append({
            "id": str(actual_id or card_id),
            "path": path.name,
            "status": card.get("knowledge_status"),
            "version": card.get("schema_version"),
            "errors": errors[start_error:],
            "warnings": warnings[start_warning:],
            "valid": not errors[start_error:],
        })
    return {
        "valid": not errors,
        "schema_family": "chaosatlas-weakness-knowledge-v1",
        "index": None,
        "root": str(root).replace("\\", "/"),
        "card_count": len(paths),
        "validated_cards": len(card_checks),
        "checks_ran": sorted({"flat_card_schema", "project_identity", "independent_evidence_runs", "promotion_audit", "rca", "regression_intents", "sensitive_value_scan"}),
        "errors": errors,
        "warnings": sorted(set(warnings)),
        "card_checks": card_checks,
    }


def validate(
    root: Path,
    profile: Path | None = None,
    *,
    expected_project: str | None = None,
    expected_commit: str | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    profile_report: dict[str, Any] | None = None
    if profile is not None:
        try:
            profile_value = load_json(profile)
            profile_report = validate_project_profile(profile_value)
        except (OSError, json.JSONDecodeError) as exc:
            profile_report = {"valid": False, "errors": [f"invalid project profile: {exc}"], "warnings": []}
        if profile_report and not profile_report.get("valid"):
            errors.extend(f"project_profile: {error}" for error in profile_report.get("errors", []))
        warnings.extend(f"project_profile: {warning}" for warning in profile_report.get("warnings", []))
    index_path = root / "index.json"
    if not index_path.exists():
        if any(root.glob("KB-*.json")):
            report = _validate_flat_weakness_root(root, expected_project=expected_project, expected_commit=expected_commit)
            if profile_report is not None:
                report["project_profile"] = profile_report
            return report
        report = {"valid": False, "errors": [f"missing {index_path}"], "warnings": []}
        if profile_report is not None:
            report["project_profile"] = profile_report
        return report

    index = load_json(index_path)
    cards = index.get("cards")
    if not isinstance(cards, list) or not cards:
        errors.append("index.cards must be a non-empty list")
        cards = []

    seen_ids: set[str] = set()
    validated = 0
    card_checks: list[dict[str, Any]] = []
    for entry in cards:
        if not isinstance(entry, dict):
            errors.append("each index card entry must be an object")
            continue
        card_id = entry.get("id")
        relative_path = entry.get("path")
        if not card_id or not relative_path:
            errors.append("index card must contain id and path")
            continue
        if card_id in seen_ids:
            errors.append(f"duplicate card id: {card_id}")
        seen_ids.add(card_id)
        error_start = len(errors)
        warning_start = len(warnings)
        card_path = root / relative_path
        if not card_path.exists():
            errors.append(f"{card_id}: missing card file {relative_path}")
            continue
        try:
            card = load_json(card_path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{card_id}: invalid JSON: {exc}")
            continue
        missing = sorted(REQUIRED_CARD_FIELDS - set(card))
        if missing:
            errors.append(f"{card_id}: missing card fields {missing}")
        if card.get("id") != card_id:
            errors.append(f"{card_id}: card.id does not match index")
        test_node = card.get("test_node")
        if not isinstance(test_node, dict):
            errors.append(f"{card_id}: test_node must be an object")
        else:
            missing_node = sorted(REQUIRED_TEST_NODE_FIELDS - set(test_node))
            if missing_node:
                errors.append(f"{card_id}: missing test_node fields {missing_node}")
            source_yaml = test_node.get("source_yaml")
            source_checked = False
            if source_yaml:
                source_path = root.resolve() / source_yaml.replace("\\", "/")
                if source_path.exists():
                    source_checked = True
                elif (ROOT / source_yaml.replace("\\", "/")).exists():
                    source_checked = True
                if not source_checked:
                    warnings.append(f"{card_id}: source_yaml is not present in the current workspace: {source_yaml}")
        graph = card.get("test_node_centered_graph")
        if not isinstance(graph, dict) or not graph.get("nodes") or not graph.get("edges"):
            errors.append(f"{card_id}: test_node_centered_graph must contain nodes and edges")
        validation = card.get("four_layer_validation")
        if not isinstance(validation, dict):
            errors.append(f"{card_id}: four_layer_validation must be an object")
        if not isinstance(card.get("next_evidence"), list) or not card["next_evidence"]:
            errors.append(f"{card_id}: next_evidence must be a non-empty list")
        for string in walk_strings(card):
            for pattern in FORBIDDEN_VALUE_PATTERNS:
                if pattern.search(string) and string not in {"secrets", "redaction"}:
                    warnings.append(f"{card_id}: review possible sensitive value in {string[:120]!r}")
                    break
        validated += 1
        card_checks.append(
            {
                "id": card_id,
                "path": relative_path,
                "status": card.get("status"),
                "version": card.get("version"),
                "errors": errors[error_start:],
                "warnings": warnings[warning_start:],
                "valid": not errors[error_start:],
            }
        )

    report = {
        "valid": not errors,
        "index": str(index_path).replace("\\", "/"),
        "card_count": len(cards),
        "validated_cards": validated,
        "checks_ran": sorted(
            {
                "index_and_card_path_resolution",
                "required_card_fields",
                "required_test_node_fields",
                "source_yaml_presence",
                "test_node_centered_graph",
                "four_layer_validation",
                "next_evidence",
                "sensitive_value_scan",
            }
        ),
        "errors": errors,
        "warnings": sorted(set(warnings)),
        "card_checks": card_checks,
    }
    if profile_report is not None:
        report["project_profile"] = profile_report
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT / "artifacts/train-ticket/knowledge_base",
        help="knowledge_base directory (absolute or relative to the repo root)",
    )
    parser.add_argument("--report", type=Path, help="optional JSON report path")
    parser.add_argument("--profile", type=Path, help="optional phase-0 project profile JSON")
    parser.add_argument("--expected-project")
    parser.add_argument("--expected-commit")
    args = parser.parse_args()
    report = validate(args.root, args.profile, expected_project=args.expected_project, expected_commit=args.expected_commit)
    report_path = args.report or args.root / "validation_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
