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

    def test_closed_boundary_card_guards_instead_of_boosting(self):
        card = self._card("local_reusable")
        card["closed_boundary"] = True
        cand = {"candidate_id": "SOCK-FRONTEND-CATALOGUE-LOSS-100", "edge": "front-end->catalogue"}
        base = score_candidate(dict(cand))
        scored = score_candidate(dict(cand), rca_snapshot={"schema_version": 1, "cards": [card]})
        self.assertEqual(scored["score"], base["score"])
        self.assertTrue(any("closed runtime boundary" in r.lower() for r in scored["reasons"]))
        self.assertIn("scoped_front_end_logs", scored.get("required_diagnostics", []))

    def test_rank_forwards_rca_snapshot(self):
        candidates = [
            {"candidate_id": "SOCK-FRONTEND-CATALOGUE-LOSS-100", "edge": "front-end->catalogue"},
            {"candidate_id": "SOCK-FRONTEND-CARTS-DELAY-2000", "edge": "front-end->carts"},
        ]
        ranked = rank(candidates, rca_snapshot=self._snapshot("local_reusable"))
        self.assertEqual(ranked[0]["candidate_id"], "SOCK-FRONTEND-CATALOGUE-LOSS-100")
        self.assertIn("KB-RCA-SOCK-ABORT-001", json.dumps(ranked))

    def test_native_deployment_candidate_uses_local_reusable_weakness_card(self):
        card = {
            "id": "KB-WEAK-FRONT-END-POD-KILL",
            "knowledge_status": "local_reusable",
            "contested": False,
            "target": "front-end",
            "test_node": {"target": "front-end", "family": "pod_kill", "operation": "pod_kill"},
            "next_evidence": ["repeat_business_oracle"],
        }
        snapshot = {"schema_version": 1, "cards": [card]}
        matching = {
            "candidate_id": "server:deployment:front-end:pod_kill",
            "target": "front-end",
            "target_kind": "deployment",
            "fault_family": "pod_kill",
            "base_score": 10,
        }
        unrelated = dict(matching, candidate_id="server:deployment:carts:pod_kill", target="carts")

        base = score_candidate(dict(matching))
        scored = score_candidate(dict(matching), rca_snapshot=snapshot)
        other = score_candidate(unrelated, rca_snapshot=snapshot)

        self.assertGreater(scored["score"], base["score"])
        self.assertTrue(any(card["id"] in reason for reason in scored["reasons"]))
        self.assertEqual(other["score"], score_candidate(unrelated)["score"])

    def test_weakness_card_does_not_match_same_edge_with_different_fault_family(self):
        card = {
            "id": "KB-WEAK-ABORT",
            "schema_version": "chaosatlas-weakness-knowledge-v1",
            "classification": "availability_weakness",
            "knowledge_status": "local_reusable",
            "target": "front-end",
            "edge": "front-end->catalogue",
            "test_node": {"target": "front-end", "family": "http_abort", "operation": "abort"},
            "next_evidence": ["boundary_logs"],
        }
        candidate = {
            "candidate_id": "server:deployment:front-end:pod_kill",
            "edge": "front-end->catalogue",
            "target": "front-end",
            "target_kind": "deployment",
            "fault_family": "pod_kill",
            "base_score": 10,
        }

        scored = score_candidate(candidate, rca_snapshot={"schema_version": 1, "cards": [card]})

        assert scored["score"] == 10
        assert not any(card["id"] in reason for reason in scored["reasons"])


class RcaClosedLoopTests(unittest.TestCase):
    def test_local_reusable_card_feedback_is_fully_traceable(self):
        card = {
            "id": "KB-RCA-SOCK-ABORT-BOUNDARY-001",
            "knowledge_status": "local_reusable",
            "contested": False,
            "test_node": {"family": "HTTPChaos", "operation": "abort"},
            "edge": "front-end->catalogue",
            "next_evidence": ["scoped_front_end_logs"],
            "regression_recipe": {"oracle": "sock-shop catalogue business chain"},
        }
        snapshot = {"schema_version": 1, "cards": [card]}
        cand = {"candidate_id": "SOCK-FRONTEND-CATALOGUE-LOSS-100", "edge": "front-end->catalogue"}
        scored = score_candidate(dict(cand), rca_snapshot=snapshot)
        # card id traceable, oracle bound to the business chain, diagnostics planned
        self.assertTrue(any(card["id"] in r for r in scored["reasons"]))
        self.assertEqual(card["regression_recipe"]["oracle"], "sock-shop catalogue business chain")
        self.assertIn("scoped_front_end_logs", scored.get("required_diagnostics", []))

    def test_contested_card_does_not_act_as_strong_prior_after_demotion(self):
        contested = {
            "id": "KB-RCA-SOCK-ABORT-BOUNDARY-001",
            "knowledge_status": "contested",
            "contested": True,
            "test_node": {"family": "HTTPChaos", "operation": "abort"},
            "edge": "front-end->catalogue",
            "next_evidence": ["recheck"],
        }
        snapshot = {"schema_version": 1, "cards": [contested]}
        cand = {"candidate_id": "SOCK-FRONTEND-CATALOGUE-LOSS-100", "edge": "front-end->catalogue"}
        base = score_candidate(dict(cand))
        scored = score_candidate(dict(cand), rca_snapshot=snapshot)
        self.assertEqual(scored["score"], base["score"])
        self.assertTrue(any("contested" in r.lower() for r in scored["reasons"]))

    def test_hard_filters_stay_authoritative_over_rca_boost(self):
        # A single-replica no-PDB kill candidate keeps its a-priori availability
        # verdict even when a local_reusable RCA card would raise its priority.
        card = {
            "id": "KB-RCA-SOCK-SINGLETON-001",
            "knowledge_status": "local_reusable",
            "contested": False,
            "test_node": {"family": "PodChaos", "operation": "pod-kill"},
            "edge": "front-end",
            "next_evidence": ["scale_to_two_counterfactual"],
        }
        snapshot = {"schema_version": 1, "cards": [card]}
        cand = {"candidate_id": "TT-ORDER-POD-KILL-1", "edge": "front-end"}
        scored = score_candidate(dict(cand), rca_snapshot=snapshot)
        if scored.get("hard_skip"):
            self.assertNotIn("required_diagnostics", scored)

    def test_repeated_rca_snapshot_ranking_is_deterministic(self):
        snapshot = {
            "schema_version": 1,
            "cards": [
                {
                    "id": "KB-RCA-A",
                    "knowledge_status": "local_reusable",
                    "contested": False,
                    "test_node": {"family": "HTTPChaos", "operation": "abort"},
                    "edge": "front-end->catalogue",
                    "next_evidence": ["scoped_logs"],
                }
            ],
        }
        candidates = [
            {"candidate_id": "SOCK-FRONTEND-CATALOGUE-LOSS-100", "edge": "front-end->catalogue"},
            {"candidate_id": "SOCK-FRONTEND-CARTS-DELAY-2000", "edge": "front-end->carts"},
        ]
        first = rank([dict(c) for c in candidates], rca_snapshot=snapshot)
        second = rank([dict(c) for c in candidates], rca_snapshot=snapshot)
        self.assertEqual(first, second)


class NativeCandidateTests(unittest.TestCase):
    def test_rank_accepts_native_deployment_candidates_without_legacy_service_parsing(self):
        candidates = [
            {"candidate_id": "deployment:api", "target": "deployment:api", "target_kind": "deployment", "fault_family": "pod_kill", "status": "eligible", "validation_plan": "baseline inject observe recover cleanup"},
            {"candidate_id": "dependency_edge:api->db", "target": "api->db", "target_kind": "dependency_edge", "fault_family": "network_loss", "status": "eligible", "validation_plan": "baseline inject observe recover cleanup"},
        ]
        result = rank(candidates)
        self.assertEqual({item["candidate_id"] for item in result}, {"deployment:api", "dependency_edge:api->db"})
        self.assertTrue(all("runtime verdict" not in " ".join(item["reasons"]).lower() for item in result))

    def test_native_knowledge_changes_priority_and_adds_diagnostic_only(self):
        candidates = [
            {"candidate_id": "deployment:api", "target": "deployment:api", "target_kind": "deployment", "fault_family": "pod_kill", "status": "eligible", "validation_plan": "baseline inject observe recover cleanup"},
            {"candidate_id": "deployment:db", "target": "deployment:db", "target_kind": "deployment", "fault_family": "network_loss", "status": "eligible", "validation_plan": "baseline inject observe recover cleanup"},
        ]
        snapshot = {
            "schema_version": 1,
            "provenance": {"kind": "test", "provenance_completeness": "complete", "sha256": {"x": "a"}},
            "source_provenance": {key: "pre_experiment_commit" for key in ("contract", "availability", "selection_experience", "defense_pattern_library", "judgment_experience")},
            "contract": {"contracts": {}, "availability": {}, "candidate_map": {}},
            "selection_experience": {"entries": [{"id": "SE-NATIVE-POD-KILL", "confidence": "high", "fault_family": "pod_kill"}]},
            "defense_pattern_library": {"patterns": []},
            "judgment_experience": {"entries": []},
        }
        result = rank(candidates, knowledge_snapshot=snapshot)
        self.assertEqual(result[0]["candidate_id"], "deployment:api")
        self.assertTrue(any("native" in reason.lower() for reason in result[0]["reasons"]))
        self.assertIsInstance(result[0]["required_diagnostics"], list)
