import sys
from pathlib import Path
import unittest


TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

from run_grpc_chaos_experiment import baseline_is_valid, parse_client_output  # noqa: E402


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

    def test_parser_keeps_multiline_cart_failure_as_business_observation(self):
        output = "[0] cart_add_failed (<_InactiveRpcError\nstatus = StatusCode.UNAVAILABLE\ndetails = \\\"Connection refused\\\"\n"
        observations = parse_client_output(output)
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["grpc_status"], "CART_ADD_FAILED")

    def test_parser_keeps_multiline_rpc_error_and_latency(self):
        output = (
            "[0] rpc_error code=UNAVAILABLE details=failed to connect\n"
            "debug_error_string = \\\"127.0.0.1:15050 connection refused\\\"\n"
            " (2042.1ms)\n"
        )
        observations = parse_client_output(output)
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["grpc_status"], "UNAVAILABLE")
        self.assertEqual(observations[0]["latency_ms"], 2042.1)



if __name__ == "__main__":
    unittest.main()
