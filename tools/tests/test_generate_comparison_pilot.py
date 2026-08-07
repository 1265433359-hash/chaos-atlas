import sys
from pathlib import Path
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from generate_comparison_pilot import generate, validate_plan  # noqa: E402


class ComparisonPilotPlanTests(unittest.TestCase):
    def test_available_methods_emit_valid_bounded_plans(self):
        result = generate(replicate=1, seed=42, limit=6)
        available = [method for method in result["methods"] if method["status"] == "available"]
        self.assertEqual({method["id"] for method in available}, {"M0", "M3", "M4"})
        for method in available:
            self.assertEqual(len(method["plans"]), 12)
            for plan in method["plans"]:
                self.assertEqual(validate_plan(plan), [])

    def test_external_methods_are_explicitly_blocked_without_fake_plans(self):
        result = generate(replicate=1, seed=42, limit=6)
        blocked = [method for method in result["methods"] if method["status"].startswith("blocked")]
        self.assertEqual({method["id"] for method in blocked}, {"M1", "M2"})
        self.assertTrue(all(not method["plans"] for method in blocked))

    def test_ours_deprioritizes_known_unreachable_path(self):
        result = generate(replicate=1, seed=42, limit=6)
        ours = next(method for method in result["methods"] if method["id"] == "M4")
        train_ticket = [plan for plan in ours["plans"] if plan["project_id"] == "train-ticket"]
        self.assertEqual(train_ticket[-1]["execution"]["candidate_id"], "TT-K2-ORDER-UNREACHABLE")


if __name__ == "__main__":
    unittest.main()
