from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import classify_runtime_result
import run_chaos_experiment


class RuntimeClassificationConsistencyTest(unittest.TestCase):
    def test_runner_uses_shared_timeout_label(self) -> None:
        preflight = {"decision": "ready_for_injection"}
        lifecycle = {"injected_count": 1}
        requests = [{"status_code": None, "error": "timed out", "latency_ms": 5005}]
        self.assertEqual(
            "client_timeout_observed",
            run_chaos_experiment.classify(preflight, lifecycle, requests, True),
        )
        result = classify_runtime_result.classify(
            {"preflight": preflight, "lifecycle": {"injected": True, "injected_status": lifecycle, "recovered": True}, "requests": requests},
            None,
        )
        self.assertEqual("client_timeout_observed", result["classification"])


if __name__ == "__main__":
    unittest.main()
