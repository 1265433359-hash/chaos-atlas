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
        # Phase-4 fix (stale assertion): OB-PRODUCTCATALOG was corrected in the
        # A2 audit to no_timeout (main.go:161 is connection-level, not per-request),
        # so its delay is NOT hard-skipped. The genuinely protected edge today is
        # OB-frontend->adservice (100ms per-request timeout, rpc.go:120) and the
        # Sock orders->payment/shipping Future.get edges.
        cand = {"candidate_id": "OB-FRONTEND-ADSERVICE-DELAY-2000", "edge": "frontend->adservice"}
        result = score_candidate(cand)
        self.assertEqual(result["priority"], "skip_protected")
        self.assertIn("explicit_timeout", result["reasons"][0])

    def test_connection_level_timeout_is_not_a_contract(self):
        # A2 regression: productcatalog's 3s WithTimeout guards connection setup
        # only; a delay candidate there must NOT be hard-skipped.
        cand = {"candidate_id": "OB-PRODUCTCATALOG-DELAY-2000", "edge": "frontend->productcatalog"}
        result = score_candidate(cand)
        self.assertNotEqual(result["priority"], "skip_protected")

    def test_loss_not_hard_skipped_by_timeout(self):
        # loss faults are NOT protected by a timeout, even on a protected edge
        cand = {"candidate_id": "OB-FRONTEND-ADSERVICE-LOSS-100", "edge": "frontend->adservice"}
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


class RcaSnapshotTests(unittest.TestCase):
    def _card(self, status):
        return {
            "id": "KB-RCA-SOCK-ABORT-001",
            "knowledge_status": status,
            "contested": False,
            "weakness_id": "WS-sock-shop-front-end-catalogue-httpchaos-abort",
            "test_node": {"family": "HTTPChaos", "operation": "abort"},
            "edge": "front-end->catalogue",
            "next_evidence": ["scoped_front_end_logs"],
        }

    def _snapshot(self, status):
        return {"schema_version": 1, "cards": [self._card(status)]}

    def test_local_reusable_card_boosts_matching_candidate(self):
        cand = {"candidate_id": "SOCK-FRONTEND-CATALOGUE-LOSS-100", "edge": "front-end->catalogue"}
        base = score_candidate(dict(cand))
        scored = score_candidate(dict(cand), rca_snapshot=self._snapshot("local_reusable"))
        self.assertGreater(scored["score"], base["score"])
        self.assertTrue(any("KB-RCA-SOCK-ABORT-001" in r for r in scored["reasons"]))
        self.assertIn("scoped_front_end_logs", scored.get("required_diagnostics", []))

    def test_provisional_card_never_changes_score_or_order(self):
        cand = {"candidate_id": "SOCK-FRONTEND-CATALOGUE-LOSS-100", "edge": "front-end->catalogue"}
        base = score_candidate(dict(cand))
        scored = score_candidate(dict(cand), rca_snapshot=self._snapshot("provisional"))
        self.assertEqual(scored["score"], base["score"])
        self.assertTrue(any("provisional" in r.lower() for r in scored["reasons"]))

    def test_contested_card_is_ignored_as_strong_prior(self):
        cand = {"candidate_id": "SOCK-FRONTEND-CATALOGUE-LOSS-100", "edge": "front-end->catalogue"}
        base = score_candidate(dict(cand))
        scored = score_candidate(dict(cand), rca_snapshot=self._snapshot("contested"))
        self.assertEqual(scored["score"], base["score"])
        self.assertTrue(any("contested" in r.lower() for r in scored["reasons"]))

    def test_rank_forwards_rca_snapshot(self):
        candidates = [
            {"candidate_id": "SOCK-FRONTEND-CATALOGUE-LOSS-100", "edge": "front-end->catalogue"},
            {"candidate_id": "SOCK-FRONTEND-CARTS-DELAY-2000", "edge": "front-end->carts"},
        ]
        ranked = rank(candidates, rca_snapshot=self._snapshot("local_reusable"))
        self.assertEqual(ranked[0]["candidate_id"], "SOCK-FRONTEND-CATALOGUE-LOSS-100")
        self.assertIn("KB-RCA-SOCK-ABORT-001", json.dumps(ranked))
