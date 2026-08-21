"""Apply card-closure outcomes to the two provisional Sock Shop RCA drafts.

Deterministic update driven entirely by the closure result.json dispositions;
fails closed when a disposition is inconclusive or a card is missing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO = Path(__file__).resolve().parents[1]
DRAFTS = REPO / "artifacts/sock-shop/rca_loop/knowledge_drafts"

DB_CARD = "KB-RCA-sock-shop-catalogue-catalogue-db-podchaos-pod-kill"
ABORT_CARD = "KB-RCA-sock-shop-front-end-catalogue-httpchaos-abort"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _recount(card: dict[str, Any]) -> None:
    counts: dict[str, int] = {}
    for ref in card.get("evidence_refs") or []:
        polarity = str(ref.get("polarity") or "neutral")
        counts[polarity] = counts.get(polarity, 0) + 1
    card["evidence_state"] = counts


def close_db_card(closure_root: Path) -> dict[str, Any]:
    result = _load(closure_root / "catalogue-db-r2/result.json")
    if result["disposition"] != "redundancy_mechanism_confirmed":
        raise ValueError(f"catalogue-db disposition '{result['disposition']}' is not promotable")
    card_path = DRAFTS / f"{DB_CARD}.json"
    card = _load(card_path)
    card["knowledge_status"] = "local_reusable"
    card["status"] = "local_reusable"
    card["version"] = int(card.get("version", 1)) + 1
    card["round_id"] = result["round_id"]
    refs = card.get("evidence_refs") or []
    refs.append({
        "evidence_id": "EV-SS-CATDB-CLOSURE-ARM-A-001",
        "kind": "business_path_replay",
        "polarity": "supports",
        "source_ref": "artifacts/sock-shop/rca_loop/card-closure/catalogue-db-r2/result.json#arm_a",
        "interpretation": "killing the only catalogue-db pod broke the front-end /catalogue oracle for 54 synchronized samples while no pre-injection Ready pod was serving",
    })
    refs.append({
        "evidence_id": "EV-SS-CATDB-CLOSURE-ARM-B-001",
        "kind": "counterfactual",
        "polarity": "supports",
        "source_ref": "artifacts/sock-shop/rca_loop/card-closure/catalogue-db-r2/result.json#arm_b",
        "interpretation": "with two self-seeding catalogue-db replicas the same kill left the business oracle served by the surviving Ready pod (co-proof samples)",
    })
    card["evidence_refs"] = refs
    _recount(card)
    card_path.write_text(json.dumps(card, indent=2, ensure_ascii=True, sort_keys=True) + "\n", encoding="utf-8")
    return card


def close_abort_card(closure_root: Path) -> dict[str, Any]:
    result = _load(closure_root / "http-abort-r1/result.json")
    if result["disposition"] != "transport_abort_propagates":
        raise ValueError(f"http-abort disposition '{result['disposition']}' is not promotable")
    card_path = DRAFTS / f"{ABORT_CARD}.json"
    card = _load(card_path)
    card["knowledge_status"] = "local_reusable"
    card["status"] = "local_reusable"
    card["version"] = int(card.get("version", 1)) + 1
    card["round_id"] = result["round_id"]
    refs = card.get("evidence_refs") or []
    refs.append({
        "evidence_id": "EV-SS-ABORT-CLOSURE-001",
        "kind": "business_path_replay",
        "polarity": "supports",
        "source_ref": "artifacts/sock-shop/rca_loop/card-closure/http-abort-r1/result.json",
        "interpretation": "confirmed HTTPChaos Response abort on the front-end->catalogue edge produced HTTP 500 at the business oracle with no graceful degradation; recovery confirmed after cleanup",
    })
    card["evidence_refs"] = refs
    exclusions = card.get("exclusion_conditions") or []
    note = "no redundancy counterfactual applies to an edge abort fault; the claim is bounded to the observed propagation without graceful degradation"
    if note not in exclusions:
        exclusions.append(note)
    card["exclusion_conditions"] = exclusions
    _recount(card)
    card_path.write_text(json.dumps(card, indent=2, ensure_ascii=True, sort_keys=True) + "\n", encoding="utf-8")
    return card


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--closure-root", type=Path,
                        default=REPO / "artifacts/sock-shop/rca_loop/card-closure")
    args = parser.parse_args()
    db = close_db_card(args.closure_root)
    abort = close_abort_card(args.closure_root)
    print(f"{db['id']}: v{db['version']} {db['knowledge_status']} ({db['evidence_state']})")
    print(f"{abort['id']}: v{abort['version']} {abort['knowledge_status']} ({abort['evidence_state']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
