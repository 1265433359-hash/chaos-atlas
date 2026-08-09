"""Run-ledger regression tests (review remediation #run-ledger).

The ledger must classify every execution-directory JSON file by its `tool`
field so predictions/classifications/summaries are never counted as
independent injections.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_ledger as rl


def _write(directory, name, doc):
    p = Path(directory) / name
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


class ClassifyTests(unittest.TestCase):
    def test_runner_complete_is_injection(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "a.json", {"tool": "run_chaos_experiment", "lifecycle": {"applied": True, "injected": True}})
            with patch.object(rl, "EXECUTION_DIR", Path(d)), patch.object(rl, "OUT", Path(d) / "ledger.json"):
                self.assertEqual(rl.main(), 0)
            ledger = json.loads((Path(d) / "ledger.json").read_text(encoding="utf-8"))
            self.assertEqual(ledger["category_counts"]["injection_complete"], 1)

    def test_classification_is_derived(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "c.json", {"tool": "classify_runtime_result", "classification": "weakness"})
            with patch.object(rl, "EXECUTION_DIR", Path(d)), patch.object(rl, "OUT", Path(d) / "ledger.json"):
                rl.main()
            ledger = json.loads((Path(d) / "ledger.json").read_text(encoding="utf-8"))
            self.assertEqual(ledger["category_counts"]["derived_classification"], 1)
            self.assertNotIn("injection_complete", ledger["category_counts"])

    def test_prediction_is_not_injection(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "r.json", {"tool": "decision_engine", "ranking": []})
            with patch.object(rl, "EXECUTION_DIR", Path(d)), patch.object(rl, "OUT", Path(d) / "ledger.json"):
                rl.main()
            ledger = json.loads((Path(d) / "ledger.json").read_text(encoding="utf-8"))
            self.assertEqual(ledger["category_counts"]["prediction_ranking"], 1)

    def test_grpc_runner_with_classification_is_injection(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "g.json", {"tool": "run_grpc_chaos_experiment", "result_classification": "weakness"})
            with patch.object(rl, "EXECUTION_DIR", Path(d)), patch.object(rl, "OUT", Path(d) / "ledger.json"):
                rl.main()
            ledger = json.loads((Path(d) / "ledger.json").read_text(encoding="utf-8"))
            self.assertEqual(ledger["category_counts"]["injection_complete"], 1)


if __name__ == "__main__":
    unittest.main()
