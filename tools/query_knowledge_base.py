"""Query the knowledge base across all projects and return retrieval-ready results.

This is the minimal "LLM consumption" interface for the knowledge base: given a
natural-language-ish query, it returns matching cards with their evidence paths,
confidence, and scope boundaries, so a downstream LLM (or human) can make a
decision WITHOUT re-running the experiments.

Usage:
    python tools/query_knowledge_base.py --query "payment delay"
    python tools/query_knowledge_base.py --family NetworkChaos --operation delay --project online-boutique
    python tools/query_knowledge_base.py --root-cause missing_timeout
    python tools/query_knowledge_base.py --list
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KB_DIRS = [
    ROOT / "artifacts" / "train-ticket" / "knowledge_base",
    ROOT / "artifacts" / "online-boutique" / "knowledge_base",
    ROOT / "artifacts" / "opentelemetry-demo" / "knowledge_base",
]


def load_cards() -> list[dict]:
    cards = []
    for kb in KB_DIRS:
        if not kb.is_dir():
            continue
        for path in sorted(kb.glob("KB-*.json")):
            try:
                cards.append(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
    return cards


def card_summary(card: dict) -> dict:
    """Reduce a card to the fields an LLM needs for a decision."""
    tn = card.get("test_node", {})
    rt = card.get("runtime_result", {})
    return {
        "id": card.get("id"),
        "project": card.get("project"),
        "version": card.get("version"),
        "status": card.get("status"),
        "confidence": card.get("confidence"),
        "test_node": {
            "family": tn.get("family"),
            "operation": tn.get("operation"),
            "latency": tn.get("latency"),
            "selector": tn.get("selector", {}).get("label", tn.get("selector")),
        },
        "hypothesis": card.get("hypothesis"),
        "runtime_result": rt.get("classification", rt),
        "root_cause": card.get("root_cause"),
        "scope": card.get("scope", {}).get("exclusions"),
        "evidence": [e.get("artifact") for e in card.get("evidence", [])],
    }


def matches(card: dict, args) -> bool:
    tn = card.get("test_node", {})
    text = " ".join(
        str(v)
        for v in [
            card.get("id"),
            card.get("project"),
            card.get("hypothesis"),
            card.get("root_cause"),
            tn.get("family"),
            tn.get("operation"),
            tn.get("latency"),
        ]
    ).lower()
    if args.query:
        for token in args.query.lower().split():
            if token not in text:
                return False
    if args.family and args.family.lower() not in (tn.get("family") or "").lower():
        return False
    if args.operation and args.operation.lower() not in (tn.get("operation") or "").lower():
        return False
    if args.project and args.project.lower() not in (card.get("project") or "").lower():
        return False
    if args.root_cause and args.root_cause.lower() not in (card.get("root_cause") or "").lower():
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", help="free-text tokens (all must match)")
    parser.add_argument("--family", help="test node family, e.g. NetworkChaos")
    parser.add_argument("--operation", help="test node operation, e.g. delay")
    parser.add_argument("--project", help="substring of project repo")
    parser.add_argument("--root-cause", help="root cause label, e.g. missing_timeout")
    parser.add_argument("--list", action="store_true", help="list all cards")
    parser.add_argument("--json", action="store_true", help="raw JSON output")
    parser.add_argument(
        "--judgment",
        action="store_true",
        help="query judgment-experience rules instead of cards (see --dimension/--adjustment)",
    )
    parser.add_argument(
        "--selection",
        action="store_true",
        help="query SELECTION-experience rules (where to test first, from corpus+experiments)",
    )
    parser.add_argument("--dimension", choices=("business_path", "contract", "recovery", "observability", "risk", "fault_family", "fault_intensity", "transferability"))
    parser.add_argument("--adjustment", choices=("upgrade", "confirm", "downgrade", "n_a"))
    args = parser.parse_args()

    if args.judgment:
        return query_judgment(args)
    if args.selection:
        return query_selection(args)

    cards = load_cards()
    if args.list:
        for c in sorted(cards, key=lambda c: c.get("id", "")):
            if not matches(c, args):
                continue
            print(f'{c.get("id")}: {c.get("project")} | {c.get("test_node", {}).get("family")} {c.get("test_node", {}).get("operation")} | {c.get("status")}')
        print(f"\nTotal: {len(cards)} cards")
        return 0

    hits = [c for c in cards if matches(c, args)]
    if not hits:
        print(f"No cards match (total {len(cards)} loaded)")
        return 1

    summaries = [card_summary(c) for c in sorted(hits, key=lambda c: c.get("id", ""))]
    if args.json:
        print(json.dumps(summaries, indent=2, ensure_ascii=False))
    else:
        for s in summaries:
            print(json.dumps(s, indent=2, ensure_ascii=False))
            print("-" * 60)
        print(f"Matched {len(hits)} card(s) from {len(cards)} total")
    return 0


def query_judgment(args) -> int:
    from judgment_experience import DIMENSIONS, EXPERIENCE_PATH, load, query

    doc = load(EXPERIENCE_PATH)
    if not doc.get("entries"):
        print("judgment experience not seeded; run: python tools/judgment_experience.py --seed")
        return 1
    entries = query(doc, args.dimension, args.adjustment)
    if args.query:
        tokens = args.query.lower().split()
        entries = [
            e for e in entries
            if all(
                tok in " ".join(
                    str(v) for v in (e.get("rule"), e.get("en_rule"), e.get("id"), e.get("evidence_cases", []))
                ).lower()
                for tok in tokens
            )
        ]
    if not entries:
        print(f"No judgment rules match (total {len(doc.get('entries', []))} seeded)")
        return 1
    for e in entries:
        print(json.dumps(e, indent=2, ensure_ascii=False))
        print("-" * 60)
    print(f"Matched {len(entries)} judgment rule(s) from {len(doc.get('entries', []))} total")
    return 0


def query_selection(args) -> int:
    from selection_experience import EXPERIENCE_PATH, load, query

    doc = load(EXPERIENCE_PATH)
    if not doc.get("entries"):
        print("selection experience not seeded; run: python tools/selection_experience.py --seed")
        return 1
    entries = query(doc, args.dimension, args.query)
    if not entries:
        print(f"No selection rules match (total {len(doc.get('entries', []))} seeded)")
        return 1
    for e in entries:
        print(json.dumps(e, indent=2, ensure_ascii=False))
        print("-" * 60)
    print(f"Matched {len(entries)} selection rule(s) from {len(doc.get('entries', []))} total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
