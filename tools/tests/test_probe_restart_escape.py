import sys
from pathlib import Path
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from run_probe_restart_escape import classify_escape  # noqa: E402


def workload(latency: float, status: str = "OK") -> dict:
    return {"observations": [{"grpc_status": status, "latency_ms": latency}]}


class ProbeRestartEscapeTests(unittest.TestCase):
    def test_confirmed_pattern_requires_reinjection(self):
        result = classify_escape(
            workload(30), workload(2030), workload(35), workload(2040), True
        )
        self.assertEqual(result, "probe_restart_escape_confirmed")

    def test_restart_without_latency_pattern_is_not_escape(self):
        result = classify_escape(
            workload(30), workload(2030), workload(2020), workload(2040), True
        )
        self.assertEqual(result, "restart_observed_without_escape_pattern")

    def test_restart_connection_failure_is_a_distinct_confirmed_outcome(self):
        result = classify_escape(
            workload(30),
            workload(2030),
            workload(15, "INTERNAL"),
            workload(2040),
            True,
        )
        self.assertEqual(result, "probe_restart_connection_failure_confirmed")


if __name__ == "__main__":
    unittest.main()
