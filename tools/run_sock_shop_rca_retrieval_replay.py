"""Same-project RCA retrieval regression replay (offline, deterministic).

Replays a fixed Sock Shop candidate set through the decision engine with the
real rca_snapshot projected from the closed RCA round (runtime-live-r4-final).
The replay verifies both integration directions:

- retrieval: the front-end pod-kill candidate is matched by the
  KB-RCA-sock-shop-front-end-podchaos-pod-kill card;
- guard: the matching card carries closed_boundary=true (from its kind=guard
  regression intent), so the closed line is guarded against re-injection
  instead of being boosted, and unrelated candidates keep their baseline
  ranking.

No cluster access, no model call, no knowledge-base write.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_sock_shop_rca_snapshot import build_snapshot  # noqa: E402
from decision_engine import rank  # noqa: E402

REPO = Path(__file__).resolve().parents[1]

# Frozen same-project replay set. C1/C2 exercise the closed card's test node
# (family/operation match by candidate_id, edge match by scope edge); C3-C5
# must stay untouched by the card.
REPLAY_CANDIDATES = [
    {"candidate_id": "SOCK-FRONT-END-POD-KILL-1", "edge": "front-end deployment", "base_score": 50},
    {"candidate_id": "SOCK-FRONT-END-POD-KILL-2", "edge": None, "base_score": 45},
    {"candidate_id": "SOCK-FRONT-END-CATALOGUE-DELAY-500", "edge": "front-end->catalogue", "base_score": 50},
    {"candidate_id": "SOCK-FRONT-END-CARTS-LOSS-100", "edge": "front-end->carts", "base_score": 50},
    {"candidate_id": "SOCK-CATALOGUE-STRESS-CPU-80", "edge": "catalogue", "base_score": 50},
]

GUARD_CARD_ID = "KB-RCA-sock-shop-front-end-podchaos-pod-kill"


def run_replay(round_root: Path) -> dict:
    snapshot = build_snapshot(round_root)
    cards = {card["id"]: card for card in snapshot["cards"]}
    if GUARD_CARD_ID not in cards:
        raise ValueError(f"guard card {GUARD_CARD_ID} missing from round {round_root}")
    if not cards[GUARD_CARD_ID]["closed_boundary"]:
        raise ValueError("guard card lost its closed_boundary flag; replay cannot verify the guard")

    with_card = rank([dict(c) for c in REPLAY_CANDIDATES], rca_snapshot=snapshot)
    without_card = rank([dict(c) for c in REPLAY_CANDIDATES], rca_snapshot=None)

    def score_of(ranked, cid):
        return next(r for r in ranked if r["candidate_id"] == cid)["score"]

    guarded = [r for r in with_card if any(GUARD_CARD_ID in reason and "closed runtime boundary" in reason for reason in r["reasons"])]
    untouched = all(
        score_of(with_card, c["candidate_id"]) == score_of(without_card, c["candidate_id"])
        for c in REPLAY_CANDIDATES
        if "POD-KILL" not in c["candidate_id"]
    )
    no_boost = all(
        score_of(with_card, c["candidate_id"]) == score_of(without_card, c["candidate_id"])
        for c in REPLAY_CANDIDATES
        if "POD-KILL" in c["candidate_id"]
    )
    report = {
        "schema_version": 1,
        "tool": "run_sock_shop_rca_retrieval_replay",
        "source_round": str(round_root),
        "guard_card": GUARD_CARD_ID,
        "guarded_candidate_ids": [r["candidate_id"] for r in guarded],
        "guard_active": bool(guarded) and len(guarded) == 2,
        "no_score_boost_on_closed_boundary": no_boost,
        "unrelated_candidates_unchanged": untouched,
        "passed": bool(guarded) and len(guarded) == 2 and no_boost and untouched,
        "ranking_with_snapshot": with_card,
        "ranking_without_snapshot": without_card,
    }
    return {"snapshot": snapshot, "report": report}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--round-root",
        type=Path,
        default=REPO / "artifacts/sock-shop/rca_loop/runtime-live-r4-final",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO / "artifacts/sock-shop/rca_loop/retrieval-replay-r1",
    )
    args = parser.parse_args()
    result = run_replay(args.round_root)
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / "rca_snapshot.json").write_text(json.dumps(result["snapshot"], indent=2) + "\n", encoding="utf-8")
    (out / "candidates.json").write_text(json.dumps({"candidates": REPLAY_CANDIDATES}, indent=2) + "\n", encoding="utf-8")
    (out / "replay_report.json").write_text(json.dumps(result["report"], indent=2) + "\n", encoding="utf-8")
    report = result["report"]
    print(f"guard_active={report['guard_active']} no_boost={report['no_score_boost_on_closed_boundary']} "
          f"untouched={report['unrelated_candidates_unchanged']} passed={report['passed']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
