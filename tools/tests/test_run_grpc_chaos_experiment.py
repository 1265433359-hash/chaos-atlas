import sys
from pathlib import Path
import unittest


TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

from run_grpc_chaos_experiment import baseline_is_valid  # noqa: E402


class GrpcExperimentRunnerTests(unittest.TestCase):
    def test_baseline_requires_at_least_one_successful_response(self):
        self.assertFalse(baseline_is_valid({"observations": []}))
        self.assertFalse(
            baseline_is_valid(
                {"observations": [{"grpc_status": "CART_ADD_FAILED"}]}
            )
        )
        self.assertTrue(
            baseline_is_valid(
                {
                    "observations": [
                        {"grpc_status": "UNAVAILABLE"},
                        {"grpc_status": "OK"},
                    ]
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
