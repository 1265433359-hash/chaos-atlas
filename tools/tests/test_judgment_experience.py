import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from judgment_experience import (
    ADJUSTMENTS,
    DIMENSIONS,
    SEED_ENTRIES,
    load,
    query,
    seed,
    validate,
)
from query_knowledge_base import query_judgment  # noqa: E402


class JudgmentExperienceTests(unittest.TestCase):
    def test_seed_entries_all_validate(self):
        doc = seed()
        self.assertEqual(validate(doc), [])

    def test_every_entry_has_evidence_and_counter_example(self):
        for entry in SEED_ENTRIES:
            self.assertTrue(entry["evidence_cases"], f"{entry['id']} lacks evidence")
            self.assertTrue(entry["counter_example"], f"{entry['id']} lacks counter_example")

    def test_dimensions_and_adjustments_are_legal(self):
        for entry in SEED_ENTRIES:
            for dim in entry["dimensions"]:
                self.assertIn(dim, DIMENSIONS)
            self.assertIn(entry["severity_adjustment"], ADJUSTMENTS)

    def test_query_filters_by_dimension_and_adjustment(self):
        doc = seed()
        contract = query(doc, dimension="contract")
        self.assertTrue(all("contract" in e["dimensions"] for e in contract))
        upgrades = query(doc, adjustment="upgrade")
        self.assertTrue(all(e["severity_adjustment"] == "upgrade" for e in upgrades))

    def test_ids_are_unique(self):
        ids = [e["id"] for e in SEED_ENTRIES]
        self.assertEqual(len(ids), len(set(ids)))


class JudgmentQueryIntegrationTests(unittest.TestCase):
    def test_judgment_query_returns_entries(self):
        doc = load()
        self.assertGreaterEqual(len(doc.get("entries", [])), 5)


if __name__ == "__main__":
    unittest.main()


class SelectionExperienceTests(unittest.TestCase):
    def test_seed_entries_all_validate(self):
        from selection_experience import SEED_ENTRIES, load, seed, validate

        doc = seed()
        self.assertEqual(validate(doc), [])
        self.assertGreaterEqual(len(doc.get("entries", [])), 5)

    def test_every_entry_has_corpus_or_experiment_evidence(self):
        from selection_experience import SEED_ENTRIES

        for entry in SEED_ENTRIES:
            self.assertTrue(
                entry.get("corpus_evidence") or entry.get("experiment_evidence"),
                f"{entry['id']} lacks evidence",
            )
            self.assertTrue(entry["counter_example"], f"{entry['id']} lacks counter_example")

    def test_ids_unique(self):
        from selection_experience import SEED_ENTRIES

        ids = [e["id"] for e in SEED_ENTRIES]
        self.assertEqual(len(ids), len(set(ids)))
