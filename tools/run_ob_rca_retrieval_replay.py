"""OB retrieval replay for the validated cross-project prior (offline).

Ranks a fixed Online Boutique candidate set with and without the OB
rca_snapshot built from the validated cross-project prior. Verifies:

- retrieval: kill/cpu candidates on OB match the prior card by
  family/operation;
- effect: the matching candidates get the local_reusable boost and the
  observation-window-artifact diagnostic; unrelated candidates keep their
  baseline scores.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_ob_rca_snapshot import build_snapshot  # noqa: E402
from decision_engine import rank  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
CROSS_PROJECT_DIR = REPO / "artifacts/sock-shop/rca_loop/cross-project-r1"

REPLAY_CANDIDATES = [
    {"candidate_id": "OB-PRODUCTCATALOG-POD-KILL-1", "edge": "frontend->productcatalog", "base_score": 50},
    {"candidate_id": "OB-PAYMENT-POD-KILL-1", "edge": "frontend->payment", "base_score": 45},
    {"candidate_id": "OB-CHECKOUT-DELAY-500", "edge": "frontend->checkout", "base_score": 50},
    {"candidate_id": "OB-CURRENCY-LOSS-100", "edge": "frontend->currency", "base_score": 50},
]


def run_replay(cross_project_dir: Path) -> dict:
    snapshot = build_snapshot(cross_project_dir)
    with_card = rank([dict(c) for c in REPLAY_CANDIDATES], rca_snapshot=snapshot)
    without_card = rank([dict(c) for c in REPLAY_CANDIDATES], rca_snapshot=None)

    def score_of(ranked, cid):
        return next(r for r in ranked if r["candidate_id"] == cid)["score"]

    card_id = snapshot["cards"][0]["id"]
    matched = [r for r in with_card if any(card_id in reason for reason in r["reasons"])]
    boosted = all(
        score_of(with_card, c["candidate_id"]) > score_of(without_card, c["candidate_id"])
        for c in REPLAY_CANDIDATES
        if "POD-KILL" in c["candidate_id"]
    )
    untouched = all(
        score_of(with_card, c["candidate_id"]) == score_of(without_card, c["candidate_id"])
        for c in REPLAY_CANDIDATES
        if "POD-KILL" not in c["candidate_id"]
    )
    diagnostics = {r["candidate_id"]: r.get("required_diagnostics", []) for r in matched}
    artifact_caveat = any(
        "observation-window-artifact" in d for ds in diagnostics.values() for d in ds
    )
    return {
        "snapshot": snapshot,
        "report": {
            "schema_version": 1,
            "tool": "run_ob_rca_retrieval_replay",
            "card_id": card_id,
            "matched_candidate_ids": [r["candidate_id"] for r in matched],
            "matching_candidates_boosted": boosted and len(matched) == 2,
            "unrelated_candidates_unchanged": untouched,
            "artifact_caveat_propagated": artifact_caveat,
            "passed": len(matched) == 2 and boosted and untouched and artifact_caveat,
            "ranking_with_snapshot": with_card,
            "ranking_without_snapshot": without_card,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cross-project-dir", type=Path, default=CROSS_PROJECT_DIR)
    parser.add_argument("--output-dir", type=Path,
                        default=REPO / "artifacts/sock-shop/rca_loop/cross-project-r1/ob-retrieval-replay-r1")
    args = parser.parse_args()
    result = run_replay(args.cross_project_dir)
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / "rca_snapshot.json").write_text(json.dumps(result["snapshot"], indent=2) + "\n", encoding="utf-8")
    (out / "candidates.json").write_text(json.dumps({"candidates": REPLAY_CANDIDATES}, indent=2) + "\n", encoding="utf-8")
    (out / "replay_report.json").write_text(json.dumps(result["report"], indent=2) + "\n", encoding="utf-8")
    report = result["report"]
    print(f"matched={report['matched_candidate_ids']} boost={report['matching_candidates_boosted']} "
          f"untouched={report['unrelated_candidates_unchanged']} caveat={report['artifact_caveat_propagated']} "
          f"passed={report['passed']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
