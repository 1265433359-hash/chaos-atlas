"""Build a decision-engine rca_snapshot from one RCA round's knowledge drafts.

The decision engine (tools/decision_engine.py) consumes an rca_snapshot
(``schema_version: 1, cards: [...]``). This tool projects a finished RCA
round's knowledge drafts into that snapshot format:

- only the fields the engine reads are projected (no evidence dumps);
- fail-closed on schema drift, unknown knowledge_status, or missing
  regression intents;
- ``closed_boundary`` is derived from the round's kind=guard regression
  intent (``closed_runtime_boundary_no_reinjection``) so the engine can
  guard a closed runtime line against re-injection instead of boosting it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
DRAFT_SCHEMA = "chaosatlas-rca-knowledge-draft-v1"
SNAPSHOT_SCHEMA = 1
ALLOWED_STATUS = {"local_reusable", "provisional", "contested", "cross_project_pending"}


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read {path.name}: {exc}") from exc


def _closed_card_ids(intents: dict[str, Any]) -> set[str]:
    closed: set[str] = set()
    for intent in intents.get("intents", []):
        if not isinstance(intent, dict):
            continue
        if intent.get("kind") != "guard":
            continue
        if "closed_runtime_boundary_no_reinjection" in str(intent.get("stop_rule", "")):
            card_id = intent.get("source_card_id")
            if card_id:
                closed.add(str(card_id))
    return closed


def build_snapshot(round_root: Path) -> dict[str, Any]:
    drafts_dir = round_root / "knowledge_drafts"
    if not drafts_dir.is_dir():
        raise ValueError(f"knowledge drafts directory not found: {drafts_dir}")
    intents_path = drafts_dir / "regression_intents.json"
    if not intents_path.is_file():
        raise ValueError("regression_intents.json missing; guard boundary cannot be derived (fail-closed)")
    closed = _closed_card_ids(_load(intents_path))

    draft_paths = sorted(drafts_dir.glob("KB-*.json"))
    if not draft_paths:
        raise ValueError("no knowledge draft cards found")

    cards: list[dict[str, Any]] = []
    for path in draft_paths:
        draft = _load(path)
        if draft.get("schema_version") != DRAFT_SCHEMA:
            raise ValueError(f"{path.name}: schema_version must be {DRAFT_SCHEMA}")
        card_id = str(draft.get("id") or "")
        if not card_id.startswith("KB-"):
            raise ValueError(f"{path.name}: draft id must start with KB-")
        status = draft.get("knowledge_status")
        if status not in ALLOWED_STATUS:
            raise ValueError(f"{path.name}: knowledge_status '{status}' is not projection-safe")
        test_node = draft.get("test_node")
        if not isinstance(test_node, dict) or not test_node.get("family") or not test_node.get("operation"):
            raise ValueError(f"{path.name}: test_node.family/operation are required for retrieval")
        scope = ((draft.get("test_node_centered_graph") or {}).get("scope") or {})
        cards.append(
            {
                "id": card_id,
                "knowledge_status": status,
                "contested": bool(draft.get("contested")),
                "weakness_id": draft.get("weakness_id"),
                "project": draft.get("project"),
                "edge": scope.get("edge"),
                "test_node": {
                    "family": test_node.get("family"),
                    "operation": test_node.get("operation"),
                    "target_role": test_node.get("target_role"),
                },
                "mechanism_claim": draft.get("mechanism_claim"),
                "applicability_conditions": draft.get("applicability_conditions", []),
                "stop_rule": draft.get("stop_rule"),
                "next_evidence": draft.get("next_evidence", []),
                "closed_boundary": card_id in closed,
                "source": {
                    "path": str(path.relative_to(round_root)).replace("\\", "/"),
                    "sha256": _sha256_file(path),
                },
            }
        )

    return {
        "schema_version": SNAPSHOT_SCHEMA,
        "tool": "build_sock_shop_rca_snapshot",
        "project": "sock-shop",
        "source_round": str(round_root),
        "cards": cards,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--round-root",
        type=Path,
        default=REPO / "artifacts/sock-shop/rca_loop/runtime-live-r4-final",
        help="RCA round directory containing knowledge_drafts/",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    snapshot = build_snapshot(args.round_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    for card in snapshot["cards"]:
        print(f"{card['id']}: status={card['knowledge_status']} closed_boundary={card['closed_boundary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
