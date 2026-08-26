import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knowledge_updater import (
    SE_PATH,
    evidence_from_candidate,
    match_selection,
    match_judgment,
    policy_evidence_reference,
)


class KnowledgeUpdaterTests(unittest.TestCase):
    def test_evidence_normalization(self):
        ev = evidence_from_candidate("OB-PAYMENT-LOSS-100", 3, "weakness", None)
        self.assertEqual(ev["project"], "OB")
        self.assertEqual(ev["fault"], "loss")
        self.assertEqual(ev["service"], "PAYMENT")
        self.assertEqual(ev["severity"], 3)

    def test_selection_matching(self):
        ev = evidence_from_candidate("OTEL-EMAIL-LOSS-100", 3, "weakness", None)
        ids = [eid for eid, _ in match_selection(ev)]
        self.assertIn("SE-NETWORK-FAMILY-001", ids)
        self.assertIn("SE-LOSS-STRONGEST-001", ids)
        self.assertIn("SE-SIDEEFFECT-COUPLING-001", ids)

    def test_judgment_matching(self):
        ev = evidence_from_candidate("OTEL-EMAIL-LOSS-100", 3, "weakness", None)
        ids = [eid for eid, _ in match_judgment(ev)]
        self.assertIn("JE-COUPLING-001", ids)

    def test_dry_run_does_not_write(self):
        import json as _json

        before = _json.loads(Path(SE_PATH).read_text(encoding="utf-8"))
        # dry-run via a fresh call that must not persist
        from knowledge_updater import backfill

        backfill(candidate_ids=["OB-PAYMENT-LOSS-100"], dry_run=True)
        after = _json.loads(Path(SE_PATH).read_text(encoding="utf-8"))
        self.assertEqual(before, after)

    def test_policy_evidence_reference_keeps_runtime_details_out_of_library_entry(self):
        ref = policy_evidence_reference({
            "candidate_id": "candidate-a",
            "classification": "confirmed_weakness",
            "causal_cluster_id": "cluster-a",
            "result_sha256": "c" * 64,
            "runtime_observation": {"availableReplicas": 0},
        })
        self.assertEqual(ref["candidate_id"], "candidate-a")
        self.assertEqual(ref["causal_cluster_id"], "cluster-a")
        self.assertNotIn("runtime_observation", ref)


if __name__ == "__main__":
    unittest.main()


class SeveritySyncTests(unittest.TestCase):
    """Prevents severity-table drift that caused OB-SHIPPING misclassification."""

    def test_severity_tables_in_sync(self):
        from compare_selection_methods import SEVERITY as S1
        from llm_interpret_evidence import SEVERITY as S2

        self.assertEqual(set(S1.keys()), set(S2.keys()))
        for cid in S1:
            self.assertEqual(S1[cid], S2[cid], f"severity mismatch for {cid}")
