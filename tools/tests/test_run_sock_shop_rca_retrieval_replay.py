"""Tests for the same-project RCA retrieval replay."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from run_sock_shop_rca_retrieval_replay import run_replay  # noqa: E402
from test_build_sock_shop_rca_snapshot import _card, _write_round  # noqa: E402

GUARD_ID = "KB-RCA-sock-shop-front-end-podchaos-pod-kill"


def _round(root: Path) -> Path:
    return _write_round(
        root,
        [_card()],
        intents={
            "intents": [
                {
                    "kind": "guard",
                    "source_card_id": GUARD_ID,
                    "stop_rule": "guard: closed_runtime_boundary_no_reinjection; stop after two valid reproductions",
                }
            ]
        },
    )


class RetrievalReplayTests(unittest.TestCase):
    def test_replay_passes_with_closed_guard_card(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_replay(_round(Path(tmp)))
        report = result["report"]
        self.assertTrue(report["guard_active"])
        self.assertTrue(report["no_score_boost_on_closed_boundary"])
        self.assertTrue(report["unrelated_candidates_unchanged"])
        self.assertTrue(report["passed"])
        self.assertEqual(
            report["guarded_candidate_ids"],
            ["SOCK-FRONT-END-POD-KILL-1", "SOCK-FRONT-END-POD-KILL-2"],
        )

    def test_replay_fails_when_guard_boundary_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _write_round(Path(tmp), [_card()], intents={"intents": []})
            with self.assertRaises(ValueError):
                run_replay(root)

    def test_rankings_are_deterministic(self):
        # source_round embeds the temp path, so determinism is asserted on the
        # decision outputs, not the provenance strings.
        with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
            first = run_replay(_round(Path(tmp1)))["report"]
            second = run_replay(_round(Path(tmp2)))["report"]
        key = lambda r: json.dumps({k: r[k] for k in ("ranking_with_snapshot", "ranking_without_snapshot")}, sort_keys=True)
        self.assertEqual(key(first), key(second))


if __name__ == "__main__":
    unittest.main()
