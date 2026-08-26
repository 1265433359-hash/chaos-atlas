"""Audit flat weakness knowledge cards before cross-project consumption."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from tools.validate_knowledge_base import validate


def build_consumption_report(
    retrieval: Mapping[str, Any],
    *,
    project_id: str,
    project_commit: str | None,
) -> dict[str, Any]:
    """Create a stable, audit-friendly view of knowledge consumed by one run."""
    cards = [item for item in retrieval.get("cards") or [] if isinstance(item, dict)]
    rejected = [item for item in retrieval.get("rejected_cards") or [] if isinstance(item, dict)]
    accepted_ids = [str(item.get("id")) for item in cards if item.get("id")]
    rejected_ids = [str(item.get("id")) for item in rejected if item.get("id")]
    reason_counts: dict[str, int] = {}
    for item in rejected:
        reason = str(item.get("reason") or "unknown")
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    return {
        "schema_version": "chaosatlas-knowledge-consumption-v1",
        "project_id": project_id,
        "project_commit": project_commit,
        "accepted_card_ids": accepted_ids,
        "accepted_count": len(accepted_ids),
        "rejected_card_ids": rejected_ids,
        "rejected_count": len(rejected_ids),
        "rejection_reasons": dict(sorted(reason_counts.items())),
        "cross_project_pending": any(
            reason in {"project_mismatch", "project_commit_mismatch", "project_identity_missing"}
            for reason in reason_counts
        ),
        "knowledge_status": "read_only",
        "claim_scope": "static",
        "policy": "only same project and matching commit cards may affect candidate ranking",
    }


def audit_knowledge_roots(
    roots: Mapping[str, Path],
    *,
    target_project: str,
    target_commit: str,
) -> dict[str, Any]:
    """Validate several card roots and keep foreign cards pending.

    This is deliberately an audit-only operation.  It never rewrites cards or
    creates executable cross-project intents.
    """
    cards: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []
    accepted: list[str] = []
    pending: list[str] = []

    for root_project, raw_root in roots.items():
        root = Path(raw_root)
        report = validate(root, expected_project=str(root_project))
        errors.extend(f"{root}: {error}" for error in report.get("errors", []))
        warnings.extend(f"{root}: {warning}" for warning in report.get("warnings", []))
        for card_check in report.get("card_checks", []):
            card_path = root / str(card_check.get("path") or "")
            try:
                card = json.loads(card_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            card_id = str(card.get("id") or card_path.stem)
            same_project = card.get("project") == target_project
            same_commit = card.get("project_commit") == target_commit
            consumption = "local_reusable" if same_project and same_commit and card.get("knowledge_status") == "local_reusable" else "cross_project_pending"
            entry = {
                "id": card_id,
                "root_project": str(root_project),
                "root": str(root).replace("\\", "/"),
                "project": card.get("project"),
                "project_commit": card.get("project_commit"),
                "knowledge_status": card.get("knowledge_status"),
                "consumption": consumption,
                "executable": consumption == "local_reusable",
                "errors": card_check.get("errors", []),
            }
            cards.append(entry)
            if entry["executable"]:
                accepted.append(card_id)
            else:
                pending.append(card_id)

    return {
        "schema_version": "chaosatlas-knowledge-migration-audit-v1",
        "valid": not errors,
        "target_project": target_project,
        "target_commit": target_commit,
        "root_count": len(roots),
        "card_count": len(cards),
        "cards": cards,
        "accepted_card_ids": accepted,
        "cross_project_pending_card_ids": pending,
        "errors": errors,
        "warnings": sorted(set(warnings)),
        "policy": "foreign cards remain cross_project_pending until independent runtime evidence and explicit review",
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--target-project", required=True)
    parser.add_argument("--target-commit", required=True)
    parser.add_argument("--root", action="append", nargs=2, metavar=("PROJECT", "PATH"), required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = audit_knowledge_roots(
        {project: Path(path) for project, path in args.root},
        target_project=args.target_project,
        target_commit=args.target_commit,
    )
    output = args.report or Path("knowledge_migration_audit.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
