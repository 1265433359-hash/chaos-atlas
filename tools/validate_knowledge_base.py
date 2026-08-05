"""Validate test-node-centered knowledge cards before LLM retrieval or injection."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


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


def validate(root: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    index_path = root / "index.json"
    if not index_path.exists():
        return {"valid": False, "errors": [f"missing {index_path}"], "warnings": []}

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
            if source_yaml and not (Path(source_yaml).exists() or (root.parent.parent / source_yaml).exists()):
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

    return {
        "valid": not errors,
        "index": str(index_path).replace("\\", "/"),
        "card_count": len(cards),
        "validated_cards": validated,
        "errors": errors,
        "warnings": sorted(set(warnings)),
        "card_checks": card_checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("artifacts/train-ticket/knowledge_base"),
        help="knowledge_base directory",
    )
    parser.add_argument("--report", type=Path, help="optional JSON report path")
    args = parser.parse_args()
    report = validate(args.root)
    report_path = args.report or args.root / "validation_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
