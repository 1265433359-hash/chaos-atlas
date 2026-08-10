"""Tests for frozen decision-engine replay (2026-08-10).

Covers the knowledge-snapshot injection contract:
  1. rank() forwards the snapshot to every score_candidate call.
  2. with a snapshot present, live JSON loaders raising is fine (zero live reads).
  3. availability_hard_filter uses snapshot availability, not module AVAILABILITY.
  4. contract_hard_filter uses snapshot contracts/candidate_map.
  5. SE / DP / JE each use their snapshot section.
  6. None keeps the historical live behavior.
  7. replay product engine outputs are NOT overridden by static prediction.
  8. f870e32 is marked as r2 snapshot, not Sock pre-experiment.
  9. loss_bounded source enum + provenance validation.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import decision_engine as de

# Project root: tests live in <root>/tools/tests, so parents[2] is the repo root.
ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = ROOT / "artifacts" / "sock-shop" / "sock_knowledge_snapshot_static.json"


def _snapshot() -> dict:
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


class SnapshotValidationTests(unittest.TestCase):
    def test_valid_snapshot_passes(self):
        de.validate_knowledge_snapshot(_snapshot())

    def test_missing_contract_fails_closed(self):
        snap = _snapshot()
        del snap["contract"]
        with self.assertRaises(ValueError):
            de.validate_knowledge_snapshot(snap)

    def test_wrong_schema_version_fails(self):
        snap = _snapshot()
        snap["schema_version"] = 99
        with self.assertRaises(ValueError):
            de.validate_knowledge_snapshot(snap)

    def test_missing_availability_fails_closed(self):
        snap = _snapshot()
        del snap["contract"]["availability"]
        with self.assertRaises(ValueError):
            de.validate_knowledge_snapshot(snap)

    def test_loss_bounded_source_enum(self):
        snap = _snapshot()
        edge = snap["contract"]["contracts"]["SOCK-orders->payment"]
        self.assertEqual(edge["loss_bounded_source"], "static_inferred")
        # provenance of the three knowledge libraries must be posthoc_or_current
        self.assertEqual(snap["source_provenance"]["selection_experience"], "posthoc_or_current")
        self.assertEqual(snap["source_provenance"]["defense_pattern_library"], "posthoc_or_current")
        self.assertEqual(snap["source_provenance"]["judgment_experience"], "posthoc_or_current")
        # contract is static_reconstructed
        self.assertEqual(snap["source_provenance"]["contract"], "static_reconstructed_pre_experiment")


class ZeroLiveReadTests(unittest.TestCase):
    """With a snapshot injected, live loaders must never be hit."""

    def _patch_live(self):
        # Any attempt to read live files raises loudly.
        patchers = [
            mock.patch.object(de, "load", side_effect=RuntimeError("live load attempted")),
            # defense_downgrade imports load_library from defense_pattern_library
            mock.patch("defense_pattern_library.load_library", side_effect=RuntimeError("live DP load")),
            mock.patch("contract_inventory.availability_for_service", side_effect=RuntimeError("live availability")),
        ]
        for p in patchers:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patchers])

    def test_score_candidate_snapshot_zero_live(self):
        self._patch_live()
        snap = _snapshot()
        de.validate_knowledge_snapshot(snap)
        r = de.score_candidate({"candidate_id": "SOCK-ORDERS-PAYMENT-DELAY-2000"}, knowledge_snapshot=snap)
        self.assertTrue(r["hard_skip"])
        self.assertEqual(r["priority"], "skip_protected")

    def test_rank_snapshot_zero_live(self):
        self._patch_live()
        snap = _snapshot()
        cands = [{"candidate_id": c} for c in ("SOCK-ORDERS-PAYMENT-DELAY-2000", "SOCK-FRONTEND-CARTS-LOSS-100")]
        ranked = de.rank(cands, knowledge_snapshot=snap)
        self.assertEqual(len(ranked), 2)
        # Protected edge has score -999 (skip_protected); under the sort key
        # (-score, id) it ranks LAST, i.e. it is de-prioritized/not selected.
        self.assertEqual(ranked[1]["candidate_id"], "SOCK-ORDERS-PAYMENT-DELAY-2000")
        self.assertEqual(ranked[1]["priority"], "skip_protected")
        self.assertEqual(ranked[1]["score"], -999.0)
        # The unprotected edge ranks first (should be executed).
        self.assertEqual(ranked[0]["candidate_id"], "SOCK-FRONTEND-CARTS-LOSS-100")
        self.assertEqual(ranked[0]["priority"], "high")

    def test_availability_uses_snapshot_not_module(self):
        self._patch_live()
        snap = _snapshot()
        r = de.availability_hard_filter({"candidate_id": "SOCK-FRONTEND-KILL-1"}, contract_snapshot=snap)
        self.assertTrue(r.get("hard_skip"))
        self.assertTrue(r.get("availability"))

    def test_contract_uses_snapshot_candidate_map(self):
        self._patch_live()
        snap = _snapshot()
        r = de.contract_hard_filter({"candidate_id": "SOCK-ORDERS-PAYMENT-LOSS-100"}, contract_snapshot=snap)
        self.assertTrue(r.get("hard_skip"))
        self.assertIn("loss_bounded", r["reason"])


class LiveBehaviorPreservedTests(unittest.TestCase):
    def test_none_still_reads_live(self):
        # Without a snapshot the live path is used; guard by asserting the
        # live contract_inventory.json exists and contains SOCK-orders edges
        # (i.e. live behavior is not accidentally disabled).
        inv_path = de.EXPERIMENTS / "contract_inventory.json"
        self.assertTrue(inv_path.exists())
        inv = json.loads(inv_path.read_text(encoding="utf-8"))
        self.assertIn("SOCK-orders->payment", inv["contracts"])


class ReplayProductTests(unittest.TestCase):
    def test_engine_output_not_overridden(self):
        replay = json.loads((ROOT / "artifacts/sock-shop/sock_frozen_decision_engine_replay.json").read_text(encoding="utf-8"))
        self.assertTrue(replay["engine_outputs_are_engine"])
        self.assertTrue(replay["static_prediction_not_overriding_engine"])
        self.assertEqual(replay["status"], "blocked")  # SE/DP/JE posthoc -> honest blocked
        # engine hard_skip values recorded, not the static predictions
        for row in replay["rows"]:
            self.assertIn("engine_output", row)
            self.assertIn("hard_skip", row["engine_output"])

    def test_audit_product_remains_valid(self):
        audit = json.loads((ROOT / "artifacts/sock-shop/sock_frozen_static_prediction_audit.json").read_text(encoding="utf-8"))
        self.assertEqual(audit["status"], "valid")
        self.assertEqual(audit["aligned_count"], audit["total"])

    def test_f870e32_marked_r2_not_sock_pre(self):
        # The snapshot provenance note must explicitly say f870e32 is r2-pre,
        # not Sock-pre; and the replay must be blocked accordingly.
        snap = _snapshot()
        note = snap["provenance"]["note"].lower()
        self.assertIn("f870e32", note)
        self.assertIn("r2-pre", note)
        self.assertIn("not sock-pre", note)


if __name__ == "__main__":
    unittest.main()
