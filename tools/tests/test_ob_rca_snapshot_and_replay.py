"""Tests for the OB rca_snapshot builder and retrieval replay."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build_ob_rca_snapshot import build_snapshot  # noqa: E402
from run_ob_rca_retrieval_replay import run_replay  # noqa: E402


def _cross_dir(root: Path, *, verdict="prior_validated") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "ob_validation_decision.json").write_text(json.dumps({
        "verdict": verdict,
        "source_card": "KB-RCA-sock-shop-front-end-podchaos-pod-kill",
        "validation_run": "ob-validation-r4",
    }), encoding="utf-8")
    (root / "kb_projection.json").write_text(json.dumps({
        "cards": [{
            "card_id": "FA-test",
            "source_project_id": "sock-shop",
            "abstraction": {
                "applicability": "single-replica deployment without a pod disruption budget under kill or cpu fault families",
                "expected_effect": "full outage window until a replacement pod becomes Ready",
            },
        }]
    }), encoding="utf-8")
    return root


class SnapshotTests(unittest.TestCase):
    def test_validated_prior_maps_to_local_reusable_card(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = build_snapshot(_cross_dir(Path(tmp)))
        card = snapshot["cards"][0]
        self.assertEqual(card["knowledge_status"], "local_reusable")
        self.assertFalse(card["closed_boundary"])
        self.assertEqual(card["test_node"]["operation"], "pod-kill")
        self.assertIn("single-replica deployment", card["mechanism_claim"])

    def test_unvalidated_verdict_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                build_snapshot(_cross_dir(Path(tmp), verdict="not_validated"))

    def test_missing_abstraction_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _cross_dir(Path(tmp))
            projection = json.loads((root / "kb_projection.json").read_text(encoding="utf-8"))
            del projection["cards"][0]["abstraction"]["applicability"]
            (root / "kb_projection.json").write_text(json.dumps(projection), encoding="utf-8")
            with self.assertRaises(ValueError):
                build_snapshot(root)


class ReplayTests(unittest.TestCase):
    def test_replay_matches_boosts_and_propagates_caveat(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = run_replay(_cross_dir(Path(tmp)))["report"]
        self.assertEqual(report["matched_candidate_ids"],
                         ["OB-PRODUCTCATALOG-POD-KILL-1", "OB-PAYMENT-POD-KILL-1"])
        self.assertTrue(report["matching_candidates_boosted"])
        self.assertTrue(report["unrelated_candidates_unchanged"])
        self.assertTrue(report["artifact_caveat_propagated"])
        self.assertTrue(report["passed"])


if __name__ == "__main__":
    unittest.main()
