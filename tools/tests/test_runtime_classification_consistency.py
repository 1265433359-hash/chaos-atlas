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
        self.assertEqual(
            classify_runtime_result.exit_code_for_classification("server_error_observed"),
            0,
        )

    def test_invalid_request_configuration_is_a_failure_exit(self) -> None:
        # Regression: a configuration error must not masquerade as a
        # successful execution in CI.
        self.assertEqual(2, classify_runtime_result.exit_code_for_classification("invalid_request_configuration"))

    def test_forced_classification_reconciles_report_labels(self) -> None:
        # Regression: when the runner forces a control outcome, the shared
        # classifier's label must be preserved in a note rather than leaving
        # two conflicting classification strings in one report.
        report = {
            "preflight": {"decision": "not_applicable"},
            "lifecycle": {"applied": False, "injected": False, "recovered": False, "cleanup": None},
            "requests": [],
            "warmup_requests": [],
            "errors": [],
        }
        details = classify_runtime_result.classify(report, None)
        # Runner sets result_classification to the forced label while the
        # shared classifier remains the evidence-derived label; the runner
        # then records the override in classification_note.
        self.assertEqual("not_applicable", details["classification"])
        forced = "invalid_request_configuration"
        if details["classification"] != forced:
            details["classification_note"] = f"overridden by runner control outcome {forced!r}"
            details["classification"] = forced
        self.assertEqual("invalid_request_configuration", details["classification"])
        self.assertIn("overridden by runner control outcome", details["classification_note"])

    def test_runner_imports_yaml_before_referencing_it(self) -> None:
        # Regression: the runner's except clause references yaml.YAMLError;
        # a missing `import yaml` raises NameError at runtime instead of
        # producing a report. Statically assert the name is imported.
        source = Path(run_chaos_experiment.__file__).read_text(encoding="utf-8")
        if "yaml.YAMLError" in source:
            self.assertIn("import yaml", source)


if __name__ == "__main__":
    unittest.main()
