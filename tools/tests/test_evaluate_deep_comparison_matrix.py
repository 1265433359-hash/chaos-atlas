import sys
from pathlib import Path
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluate_deep_comparison_matrix import evaluate  # noqa: E402
from generate_deep_comparison_matrix import generate  # noqa: E402


class DeepComparisonEvaluationTests(unittest.TestCase):
    def test_evaluation_requires_a_common_pool_and_records_gate_decisions(self):
        registry = generate(replicate=1, seed=42, candidate_budget=12)
        with patch(
            "evaluate_deep_comparison_matrix.check_mutation",
            return_value={"decision": "ready_for_injection"},
        ) as gate:
            result = evaluate(registry)
        self.assertTrue(result["same_candidate_pool"])
        self.assertGreater(gate.call_count, 0)
        ours = next(item for item in result["methods"] if item["id"] == "M4")
        self.assertEqual(ours["candidate_count"], 12)
        self.assertEqual(ours["summary"], {"ready_for_injection": 12})


if __name__ == "__main__":
    unittest.main()
