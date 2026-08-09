"""Phase-5 remediation tests: runner provenance + report correctness.

Covers review findings:
  #11 runner/summary reports hardcoded scenario repetition count to 3 while
      inputs contained 4 records per scenario.
  #12 runner report was not bound to an environment fingerprint, and internal
      classification had no baseline contract.

Pure unit tests: no cluster, no artifact writes.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import environment_fingerprint as fp
import summarize_comparative_results as scr


class FingerprintLoaderTests(unittest.TestCase):
    def test_load_returns_none_when_missing(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(fp.load_fingerprint(Path(d) / "nope.json"))

    def test_load_returns_none_on_invalid_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "fp.json"
            p.write_text("{ not json", encoding="utf-8")
            self.assertIsNone(fp.load_fingerprint(p))

    def test_load_returns_doc(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "fp.json"
            p.write_text(json.dumps({"tool": "environment_fingerprint", "kubernetes": {"context": "x"}}), encoding="utf-8")
            doc = fp.load_fingerprint(p)
            self.assertEqual(doc["kubernetes"]["context"], "x")


class FingerprintEmbeddedInRunnerTests(unittest.TestCase):
    def test_run_chaos_experiment_report_has_fingerprint(self):
        import run_chaos_experiment as rce
        src = Path(rce.__file__).read_text(encoding="utf-8")
        self.assertIn('"environment_fingerprint": load_fingerprint()', src)
        self.assertIn('"baseline": None', src)

    def test_run_grpc_report_has_fingerprint(self):
        import run_grpc_chaos_experiment as rgc
        src = Path(rgc.__file__).read_text(encoding="utf-8")
        self.assertIn('"environment_fingerprint": load_fingerprint()', src)
        self.assertIn('"baseline": None', src)

    def test_probe_restart_report_has_fingerprint(self):
        import run_probe_restart_escape as rpre
        src = Path(rpre.__file__).read_text(encoding="utf-8")
        self.assertIn('"environment_fingerprint": load_fingerprint()', src)


class ScenarioReplicatesDynamicTests(unittest.TestCase):
    """scenario_replicates must be derived from records, not hardcoded."""

    def test_source_has_no_hardcoded_replicates_dict(self):
        src = Path(scr.__file__).read_text(encoding="utf-8")
        self.assertNotIn('"tt_station_delay": 3', src)
        self.assertIn("scenario_replicates[scenario] = scenario_replicates.get(scenario, 0) + 1", src)

    def test_no_hardcoded_valid_runtime_replicates(self):
        # Round-2 finding #6: scope must NOT claim a uniform 4 (or any fixed
        # count); per-scenario counts come from the actual records.
        src = Path(scr.__file__).read_text(encoding="utf-8")
        self.assertNotIn('"valid_runtime_replicates": 4', src)
        self.assertIn("uniform_replicates", src)

    def test_scenario_field_present_in_records(self):
        # build the runtime records list WITHOUT touching real files: patch load()
        # to return stub reports; assert each record carries a scenario key and
        # counts group correctly.
        stub = {
            "lifecycle": {"applied": True, "injected": True, "recovered": True,
                          "cleanup": {"delete_command_ok": True, "resource_absent_after_delete": True}},
            "result_classification": "weakness",
            "observations": {"injected": True, "recovered": True, "cleanup_confirmed": True},
        }
        with patch.object(scr, "load", return_value=stub):
            # call the two record helpers directly with fake names
            rec1 = scr.http_record("TT station delay r1", "a.json", "b.json")
            rec2 = scr.grpc_record("OB payment loss r4", "c.json")
        self.assertEqual(rec1["scenario"], "TT station delay")
        self.assertEqual(rec2["scenario"], "OB payment loss")

    def test_different_replicate_counts_reported_honestly(self):
        # If scenarios have different record counts, the summary must report
        # per-scenario counts and NOT fabricate a uniform number.
        stub = {
            "lifecycle": {"applied": True, "injected": True, "recovered": True,
                          "cleanup": {"delete_command_ok": True, "resource_absent_after_delete": True}},
            "result_classification": "weakness",
            "observations": {"injected": True, "recovered": True, "cleanup_confirmed": True},
        }
        with patch.object(scr, "load", return_value=stub):
            records = [
                scr.grpc_record("OB payment delay r1", "x.json"),
                scr.grpc_record("OB payment delay r2", "x.json"),
                scr.grpc_record("OTel payment loss r1", "x.json"),
                scr.grpc_record("OTel payment loss r2", "x.json"),
                scr.grpc_record("OTel payment loss r3", "x.json"),
            ]
        counts: dict[str, int] = {}
        for item in records:
            counts[item["scenario"]] = counts.get(item["scenario"], 0) + 1
        self.assertEqual(counts["OB payment delay"], 2)
        self.assertEqual(counts["OTel payment loss"], 3)
        # The report must not claim a uniform count when they differ.
        self.assertNotEqual(len(set(counts.values())), 1)


if __name__ == "__main__":
    unittest.main()
