"""Tests for the RCA-round -> decision-engine rca_snapshot projection."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build_sock_shop_rca_snapshot import build_snapshot  # noqa: E402


def _card(status: str = "local_reusable", card_id: str = "KB-RCA-sock-shop-front-end-podchaos-pod-kill") -> dict:
    return {
        "schema_version": "chaosatlas-rca-knowledge-draft-v1",
        "id": card_id,
        "knowledge_status": status,
        "weakness_id": "WS-sock-shop-front-end-podchaos-pod-kill",
        "project": "sock-shop",
        "test_node": {"family": "PodChaos", "operation": "pod-kill", "target_role": "front-end deployment"},
        "test_node_centered_graph": {"scope": {"edge": "front-end deployment", "services": ["front-end deployment"]}},
        "mechanism_claim": "singleton workload loses all capacity under pod kill",
        "applicability_conditions": ["single-replica deployment without pod disruption budget"],
        "stop_rule": "stop after two valid reproductions or one clean falsification",
        "next_evidence": ["next_bounded_evidence"],
    }


def _write_round(root: Path, cards: list[dict], intents: dict | None = None) -> Path:
    drafts = root / "knowledge_drafts"
    drafts.mkdir(parents=True)
    for card in cards:
        (drafts / f"{card['id']}.json").write_text(json.dumps(card), encoding="utf-8")
    if intents is None:
        intents = {"intents": []}
    (drafts / "regression_intents.json").write_text(json.dumps(intents), encoding="utf-8")
    return root


class BuildSnapshotTests(unittest.TestCase):
    def test_projects_card_with_engine_fields_and_closed_boundary(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = _write_round(
                Path(tmp),
                [_card()],
                intents={
                    "intents": [
                        {
                            "kind": "guard",
                            "source_card_id": "KB-RCA-sock-shop-front-end-podchaos-pod-kill",
                            "stop_rule": "guard: closed_runtime_boundary_no_reinjection; stop after two valid reproductions",
                        }
                    ]
                },
            )
            snapshot = build_snapshot(root)
        self.assertEqual(snapshot["schema_version"], 1)
        self.assertEqual(len(snapshot["cards"]), 1)
        card = snapshot["cards"][0]
        self.assertEqual(card["id"], "KB-RCA-sock-shop-front-end-podchaos-pod-kill")
        self.assertEqual(card["knowledge_status"], "local_reusable")
        self.assertFalse(card["contested"])
        self.assertTrue(card["closed_boundary"])
        self.assertEqual(card["edge"], "front-end deployment")
        self.assertEqual(card["test_node"]["operation"], "pod-kill")
        self.assertIn("next_bounded_evidence", card["next_evidence"])
        # provenance, not full evidence dumps
        self.assertIn("source", card)
        self.assertNotIn("evidence_refs", card)

    def test_no_guard_intent_means_open_boundary(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = _write_round(Path(tmp), [_card()], intents={"intents": []})
            snapshot = build_snapshot(root)
        self.assertFalse(snapshot["cards"][0]["closed_boundary"])

    def test_invalid_schema_fails_closed(self):
        import tempfile

        bad = _card()
        bad["schema_version"] = "something-else"
        with tempfile.TemporaryDirectory() as tmp:
            root = _write_round(Path(tmp), [bad])
            with self.assertRaises(ValueError):
                build_snapshot(root)

    def test_unknown_knowledge_status_fails_closed(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = _write_round(Path(tmp), [_card(status="globally_true")])
            with self.assertRaises(ValueError):
                build_snapshot(root)

    def test_missing_regression_intents_fails_closed(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = _write_round(Path(tmp), [_card()])
            (root / "knowledge_drafts" / "regression_intents.json").unlink()
            with self.assertRaises(ValueError):
                build_snapshot(root)


if __name__ == "__main__":
    unittest.main()
