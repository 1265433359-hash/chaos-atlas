"""Tests for the cross-project RCA knowledge projection."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from project_sock_shop_rca_cross_project import project  # noqa: E402

DECISION = {
    "decision": "approved_local_reuse_with_cross_project_projection",
    "cross_project_mode": "provisional_prior_pending_target_project_validation",
    "reviewer": "project-owner",
    "date": "2026-08-21",
}

CARD = {
    "schema_version": "chaosatlas-rca-knowledge-draft-v1",
    "id": "KB-RCA-sock-shop-front-end-podchaos-pod-kill",
    "knowledge_status": "local_reusable",
}


def _r2_result() -> dict:
    return {
        "injection_status": {"status": {"conditions": [{"type": "AllInjected", "status": "True"}]}},
        "residual_podchaos": [],
    }


def _r4_result() -> dict:
    return {
        "summary": {"classification": "defended", "defended_sample_count": 3},
        "residual_podchaos": [],
        "restored_replicas": 1,
        "original_replicas": 1,
    }


def _timeline() -> list[str]:
    return [
        json.dumps({"business": {"status_code": 200}}),
        json.dumps({"business": {"status_code": None, "error": "URLError"}}),
    ]


def _round(root: Path, *, decision=None, card=None, r2=None, r4=None, timeline=None) -> Path:
    drafts = root / "knowledge_drafts"
    evidence = root / "evidence" / "disambiguation-r2"
    redundancy = root / "evidence" / "redundancy-r1"
    evidence.mkdir(parents=True)
    drafts.mkdir(parents=True)
    redundancy.mkdir(parents=True)
    (root / "human_review_decision.json").write_text(json.dumps(decision or DECISION), encoding="utf-8")
    (drafts / "KB-RCA-sock-shop-front-end-podchaos-pod-kill.json").write_text(json.dumps(card or CARD), encoding="utf-8")
    (evidence / "result.json").write_text(json.dumps(r2 or _r2_result()), encoding="utf-8")
    (evidence / "timeline.jsonl").write_text("\n".join(timeline or _timeline()), encoding="utf-8")
    (redundancy / "result.json").write_text(json.dumps(r4 or _r4_result()), encoding="utf-8")
    return root


class ProjectionTests(unittest.TestCase):
    def test_projection_produces_leak_free_provisional_prior(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = project(_round(Path(tmp)))
        self.assertEqual(report["classification"], "confirmed_weakness")
        self.assertEqual(report["projection_mode"], "provisional_prior_pending_target_project_validation")
        card = report["kb_projection"]["cards"][0]
        self.assertNotIn("evidence", card)
        self.assertNotIn("target", card)
        self.assertEqual(card["source_project_id"], "sock-shop")
        self.assertTrue(card["abstraction"]["applicability"].startswith("single-replica deployment"))

    def test_decision_not_authorizing_projection_fails_closed(self):
        bad = dict(DECISION, decision="approved_local_reuse")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                project(_round(Path(tmp), decision=bad))

    def test_missing_counterfactual_fails_closed(self):
        weak = _r4_result()
        weak["summary"] = {"classification": "observation_inconclusive", "defended_sample_count": 0}
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                project(_round(Path(tmp), r4=weak))

    def test_uninjected_timeline_fails_closed(self):
        no_outage = [json.dumps({"business": {"status_code": 200}})]
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                project(_round(Path(tmp), timeline=no_outage))

    def test_non_local_reusable_card_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                project(_round(Path(tmp), card=dict(CARD, knowledge_status="provisional")))


if __name__ == "__main__":
    unittest.main()
