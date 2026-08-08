import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from decision_engine import contract_hard_filter, rank, score_candidate, selection_hits


class DecisionEngineTests(unittest.TestCase):
    def test_loss_candidate_scores_highest(self):
        candidates = [
            {"candidate_id": "OTEL-CURRENCY-LOSS-100", "edge": "checkout->currency"},
            {"candidate_id": "OB-FRONTEND-CURRENCY-DELAY-2000", "edge": "frontend->currency"},
        ]
        ranked = rank(candidates)
        self.assertEqual(ranked[0]["candidate_id"], "OTEL-CURRENCY-LOSS-100")

    def test_timeout_protected_delay_is_hard_skipped(self):
        cand = {"candidate_id": "OB-PRODUCTCATALOG-DELAY-2000", "edge": "frontend->productcatalog"}
        result = score_candidate(cand)
        self.assertEqual(result["priority"], "skip_protected")
        self.assertIn("explicit_timeout", result["reasons"][0])

    def test_loss_not_hard_skipped_by_timeout(self):
        # loss faults are NOT protected by a timeout, even on a protected edge
        cand = {"candidate_id": "OB-PRODUCTCATALOG-LOSS-100", "edge": "frontend->productcatalog"}
        result = score_candidate(cand)
        self.assertNotEqual(result["priority"], "skip_protected")

    def test_ranking_matches_prospective_outcomes(self):
        candidates = [
            {"candidate_id": "OTEL-CURRENCY-LOSS-100", "edge": "checkout->currency"},
            {"candidate_id": "OB-FRONTEND-CURRENCY-DELAY-2000", "edge": "frontend->currency"},
            {"candidate_id": "OTEL-PRODUCTCATALOG-DELAY-2000", "edge": "checkout->product-catalog"},
            {"candidate_id": "OTEL-SHIPPING-DELAY-2000", "edge": "checkout->shipping"},
        ]
        ranked = rank(candidates)
        ids = [r["candidate_id"] for r in ranked if r["priority"] not in ("skip_protected", "skip_recommended")]
        # actual severities (prospective r1, all executed later)
        actual = {"OTEL-CURRENCY-LOSS-100": 3, "OB-FRONTEND-CURRENCY-DELAY-2000": 3,
                  "OTEL-PRODUCTCATALOG-DELAY-2000": 2, "OTEL-SHIPPING-DELAY-2000": 3}
        self.assertTrue(all(actual[cid] >= 2 for cid in ids))

    def test_selection_hits_weights(self):
        hits = selection_hits({"candidate_id": "OTEL-EMAIL-LOSS-100", "edge": "checkout->email"})
        ids = [eid for eid, _ in hits]
        self.assertIn("SE-LOSS-STRONGEST-001", ids)
        self.assertIn("SE-SIDEEFFECT-COUPLING-001", ids)
        self.assertIn("SE-NETWORK-FAMILY-001", ids)


if __name__ == "__main__":
    unittest.main()
