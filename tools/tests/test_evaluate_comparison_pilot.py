import sys
from pathlib import Path
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluate_comparison_pilot import evaluate_registry  # noqa: E402
from generate_comparison_pilot import generate  # noqa: E402


class ComparisonPilotEvaluationTests(unittest.TestCase):
    def test_preclassified_candidates_do_not_call_runtime_gate(self):
        registry = generate(replicate=1, seed=42, limit=6)
        with patch(
            "evaluate_comparison_pilot.check_mutation",
            return_value={"decision": "ready_for_injection"},
        ) as gate:
            result = evaluate_registry(registry)
        evaluated = [
            plan
            for method in result["methods"]
            for plan in method["plans"]
            if plan["candidate_id"] == "TT-K2-ORDER-UNREACHABLE"
        ]
        self.assertTrue(evaluated)
        self.assertTrue(all(plan["decision"] == "invalid_unreachable" for plan in evaluated))
        self.assertLess(gate.call_count, 36)


if __name__ == "__main__":
    unittest.main()
