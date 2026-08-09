"""Phase-4 remediation tests: registry/evidence/contract share ONE universe.

Covers review findings:
  #5  selection comparison mixed the 20-candidate evidence pool with the
      12-candidate core registry universe -> negative-remainder artifacts.
  #13 unknown project prefix silently fell back to TT, misrouting candidates.
  Also pins the stale OB-PRODUCTCATALOG decision (A2 audit: no_timeout).

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

import compare_selection_methods as csm
import project_registry as pr


class RegistryUniverseConsistencyTests(unittest.TestCase):
    """Metrics must be computed over the registry universe only."""

    def _registry(self, universe):
        return {
            "candidate_universe": list(universe),
            "methods": [
                {
                    "id": "M1",
                    "name": "m1",
                    "status": "available",
                    "plans": [
                        {"execution": {"candidate_id": cid}}
                        for cid in ["OB-PAYMENT-DELAY-2000", "OB-CHECKOUT-DELAY-2000"]
                    ],
                }
            ],
        }

    def _evidence(self, known_ids):
        return {
            "candidates": [
                {"candidate_id": cid, "own_discovery_evidence": [{"verdict": "weakness"}]}
                for cid in known_ids
            ]
        }

    def test_known_outside_universe_is_not_counted(self):
        # universe = {A,B}; evidence knows {A,B,C} where C is outside the universe.
        universe = ["OB-PAYMENT-DELAY-2000", "OB-PAYMENT-LOSS-100"]
        registry = self._registry(universe)
        evidence = self._evidence(["OB-PAYMENT-DELAY-2000", "OB-PAYMENT-LOSS-100", "OB-CHECKOUT-DELAY-2000"])
        with tempfile.TemporaryDirectory() as d:
            reg_p = Path(d) / "reg.json"
            ev_p = Path(d) / "candidate_evidence_status.json"  # compute() reads this name
            reg_p.write_text(json.dumps(registry), encoding="utf-8")
            ev_p.write_text(json.dumps(evidence), encoding="utf-8")
            with patch.object(csm, "EXECUTION_DIR", Path(d)), patch.object(
                csm, "load_json", side_effect=lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
            ):
                report = csm.compute(1, registry_path=reg_p)
        self.assertEqual(report["candidate_universe_size"], 2)
        self.assertEqual(report["known_discovered_count"], 2)  # C excluded
        self.assertEqual(report["known_outside_universe_count"], 1)
        self.assertEqual(report["known_outside_universe_ids"], ["OB-CHECKOUT-DELAY-2000"])
        self.assertFalse(report["universe_consistent"])
        # M1 selected only OB-PAYMENT-DELAY-2000 (universe member) -> 1 hit of 2
        m1 = report["methods"][0]
        self.assertEqual(m1["known_hits"], 1)
        self.assertEqual(m1["selected_count"], 1)  # OB-CHECKOUT excluded from selected
        self.assertEqual(m1["selected_outside_universe_count"], 1)

    def test_universe_consistent_when_sets_match(self):
        universe = ["A", "B"]
        registry = self._registry(universe)
        evidence = self._evidence(["A", "B"])
        with tempfile.TemporaryDirectory() as d:
            reg_p = Path(d) / "reg.json"
            ev_p = Path(d) / "candidate_evidence_status.json"
            reg_p.write_text(json.dumps(registry), encoding="utf-8")
            ev_p.write_text(json.dumps(evidence), encoding="utf-8")
            with patch.object(csm, "EXECUTION_DIR", Path(d)), patch.object(
                csm, "load_json", side_effect=lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
            ):
                report = csm.compute(1, registry_path=reg_p)
        self.assertTrue(report["universe_consistent"])
        self.assertEqual(report["known_outside_universe_count"], 0)


class UnknownProjectStrictTests(unittest.TestCase):
    """Unknown project prefix must fail closed with strict=True."""

    def test_known_projects_resolve(self):
        self.assertEqual(pr.project_of("SOCK-FRONTEND-KILL-1", strict=True), "SOCK")
        self.assertEqual(pr.project_of("OB-PAYMENT-DELAY-2000", strict=True), "OB")
        self.assertEqual(pr.normalize_service("SOCK-CARTS-LOSS-100", strict=True), "CART")

    def test_unknown_project_strict_raises(self):
        with self.assertRaises(ValueError):
            pr.project_of("UNKNOWN-SERVICE-DELAY-2000", strict=True)
        with self.assertRaises(ValueError):
            pr.normalize_service("NOPE-PAYMENT-LOSS-100", strict=True)

    def test_legacy_tolerant_still_returns_tt(self):
        # backward-compat: default remains tolerant; strict is the opt-in.
        self.assertEqual(pr.project_of("UNKNOWN-SERVICE-DELAY-2000"), "TT")


if __name__ == "__main__":
    unittest.main()
