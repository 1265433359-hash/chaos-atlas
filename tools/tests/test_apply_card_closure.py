"""Tests for the deterministic provisional-card closure update."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apply_card_closure import close_abort_card, close_db_card  # noqa: E402

DB_CARD = "KB-RCA-sock-shop-catalogue-catalogue-db-podchaos-pod-kill"
ABORT_CARD = "KB-RCA-sock-shop-front-end-catalogue-httpchaos-abort"


def _closure_root(root: Path, *, db_disposition="redundancy_mechanism_confirmed",
                  abort_disposition="transport_abort_propagates") -> Path:
    (root / "catalogue-db-r2").mkdir(parents=True)
    (root / "http-abort-r1").mkdir()
    (root / "catalogue-db-r2/result.json").write_text(json.dumps({"disposition": db_disposition, "round_id": "card-closure-catalogue-db-r1"}), encoding="utf-8")
    (root / "http-abort-r1/result.json").write_text(json.dumps({"disposition": abort_disposition, "round_id": "card-closure-http-abort-r1"}), encoding="utf-8")
    return root


def _drafts(root: Path) -> Path:
    drafts = root / "knowledge_drafts"
    drafts.mkdir(parents=True)
    for card_id in (DB_CARD, ABORT_CARD):
        (drafts / f"{card_id}.json").write_text(json.dumps({
            "id": card_id, "knowledge_status": "provisional", "version": 1,
            "evidence_refs": [], "round_id": "pilot-r1",
        }), encoding="utf-8")
    return drafts


class ClosureTests(unittest.TestCase):
    def test_successful_closure_promotes_cards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _closure_root(root)
            import apply_card_closure
            original = apply_card_closure.DRAFTS
            apply_card_closure.DRAFTS = _drafts(root)
            try:
                db = close_db_card(root)
                abort = close_abort_card(root)
            finally:
                apply_card_closure.DRAFTS = original
        self.assertEqual(db["knowledge_status"], "local_reusable")
        self.assertEqual(db["version"], 2)
        self.assertEqual(db["evidence_state"], {"supports": 2})
        self.assertEqual(abort["knowledge_status"], "local_reusable")
        self.assertTrue(any("no redundancy counterfactual" in e for e in abort["exclusion_conditions"]))

    def test_inconclusive_disposition_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _closure_root(Path(tmp), db_disposition="inconclusive")
            with self.assertRaises(ValueError):
                close_db_card(root)


if __name__ == "__main__":
    unittest.main()
