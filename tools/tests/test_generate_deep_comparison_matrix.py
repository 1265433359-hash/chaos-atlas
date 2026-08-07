import sys
from pathlib import Path
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from generate_deep_comparison_matrix import CORE_CANDIDATES, generate, validate_plan  # noqa: E402


class DeepComparisonMatrixTests(unittest.TestCase):
    def test_available_methods_share_the_same_twelve_candidate_pool(self):
        result = generate(replicate=1, seed=42, candidate_budget=10)
        available = [item for item in result["methods"] if item["status"] == "available"]
        self.assertEqual(len(CORE_CANDIDATES), 12)
        pools = [
            {plan["execution"]["candidate_id"] for plan in method["plans"]}
            for method in available
        ]
        self.assertTrue(all(pool.issubset(set(result["candidate_universe"])) for pool in pools))
        self.assertTrue(all(len(pool) == 10 for pool in pools))

    def test_external_methods_are_blocked_without_fake_plans(self):
        result = generate(replicate=1, seed=42, candidate_budget=10)
        blocked = [item for item in result["methods"] if item["status"].startswith("blocked")]
        self.assertEqual({item["id"] for item in blocked}, {"M1", "M2"})
        self.assertTrue(all(not item["plans"] for item in blocked))

    def test_generated_plans_are_one_target_and_valid(self):
        result = generate(replicate=1, seed=42, candidate_budget=10)
        for method in result["methods"]:
            for plan in method["plans"]:
                self.assertEqual(validate_plan(plan), [])
                self.assertEqual(plan["fault"]["mode"], "one")


if __name__ == "__main__":
    unittest.main()
