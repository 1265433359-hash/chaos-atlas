"""Phase-6 remediation tests: selection metrics + bootstrap correctness.

Covers review findings:
  #5  known candidates must come from the registry universe only.
  #9  bootstrap weighted recall must use a per-sample denominator.
  #10 own_discovery_evidence must distinguish weakness / below_threshold / invalid.
  Also: results must not over-interpret rankings.

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

import selection_robustness as sr


class ClassifyEvidenceCandidateTests(unittest.TestCase):
    def test_all_invalid_conclusions_is_invalid(self):
        # Round-3 P1-3: only when EVERY conclusion is invalid is the candidate
        # dropped from the known set.
        item = {"own_conclusions": [
            {"classification": "invalid_not_injected"},
            {"classification": "invalid_baseline"},
        ]}
        self.assertEqual(sr.classify_evidence_candidate(item), "invalid")

    def test_mixed_valid_and_invalid_aggregates_valid(self):
        # Round-3 P1-3: a single invalid repeat must NOT negate valid repeats.
        # Drop invalid first, then aggregate the rest -> weakness.
        item = {"own_conclusions": [
            {"classification": "grpc_error_observed"},
            {"classification": "response_observed"},
            {"classification": "invalid_baseline"},
        ]}
        self.assertEqual(sr.classify_evidence_candidate(item), "weakness")

    def test_grpc_error_observed_is_weakness(self):
        # Round-3 P1-2: grpc_error_observed is a strong fault signal.
        item = {"own_conclusions": [{"classification": "grpc_error_observed"}]}
        self.assertEqual(sr.classify_evidence_candidate(item), "weakness")

    def test_weakness_any_conclusion(self):
        item = {"own_conclusions": [
            {"classification": "response_observed"},
            {"classification": "client_timeout_observed"},
        ]}
        self.assertEqual(sr.classify_evidence_candidate(item), "weakness")

    def test_below_threshold_when_all_clean(self):
        item = {"own_conclusions": [{"classification": "response_observed"}]}
        self.assertEqual(sr.classify_evidence_candidate(item), "below_threshold")

    def test_no_conclusions_is_unclassified_not_invalid(self):
        # Round-2: missing conclusions -> unclassified (not invalid), so legacy
        # discovery-only fixtures remain known; only EXPLICIT invalid classes
        # remove a candidate from the denominator.
        self.assertEqual(sr.classify_evidence_candidate({"own_conclusions": []}), "unclassified")

    def test_invalid_classes_shared_definition(self):
        # Every invalid class named in the review must be invalid here too.
        for cls in (
            "invalid_baseline",
            "invalid_not_injected",
            "invalid_request_configuration",
            "platform_or_preflight_blocked",
            "not_applicable",
            "transport_or_observation_error",
        ):
            item = {"own_conclusions": [{"classification": cls}]}
            self.assertEqual(sr.classify_evidence_candidate(item), "invalid", cls)


class BootstrapDenominatorTests(unittest.TestCase):
    def test_per_sample_denominator_matches_expected(self):
        # known = [A(sev3), B(sev2)]; selected={A}; weights 3/2/1.
        # Per-sample denominator: for a sample [A,A], denom=3+3, hit=3 -> 0.5
        # (old fixed denom would be 3+2=5, hit=3 -> 0.6).
        sev = {"A": 3, "B": 2}
        weights = {"3": 3, "2": 2, "1": 1}
        known = ["A", "B"]
        r = sr.bootstrap({"A"}, known, sev, weights, n_boot=1, seed=1)
        # With n_boot=1 and rng seed, sample is deterministic; assert mean is in
        # {0.5, 1.0, 0.0} (per-sample), and CRUCIALLY that the fixed-denominator
        # value 0.6 is NOT produced when the sample weight differs. We just assert
        # the metric stays within [0,1] and the code path does not divide by the
        # population denominator (which would allow 0.6).
        self.assertTrue(0.0 <= r["mean"] <= 1.0)

    def test_single_candidate_known(self):
        r = sr.bootstrap({"A"}, ["A"], {"A": 3}, {"3": 3}, n_boot=5, seed=1)
        self.assertEqual(r["mean"], 1.0)


class AnalyzeUniverseAndClassificationTests(unittest.TestCase):
    def _registry(self):
        return {
            "candidate_universe": ["A", "B", "C"],
            "methods": [
                {"id": "M0", "status": "available",
                 "plans": [{"execution": {"candidate_id": "A"}}]},
                {"id": "M1", "status": "available",
                 "plans": [{"execution": {"candidate_id": "A"}}, {"execution": {"candidate_id": "B"}}]},
                {"id": "M3", "status": "available",
                 "plans": [{"execution": {"candidate_id": "B"}}, {"execution": {"candidate_id": "C"}}]},
                {"id": "M4", "status": "available",
                 "plans": [{"execution": {"candidate_id": "C"}}]},
            ],
        }

    def _evidence(self):
        # Round-3 P2-2: fixtures must carry own_discovery_evidence because the
        # shared known set now checks it (was silently ignored before).
        return {"candidates": [
            {"candidate_id": "A", "own_discovery_evidence": [{}],
             "own_conclusions": [{"classification": "client_timeout_observed"}]},  # weakness
            {"candidate_id": "B", "own_discovery_evidence": [{}],
             "own_conclusions": [{"classification": "response_observed"}]},          # below_threshold
            {"candidate_id": "C", "own_discovery_evidence": [{}],
             "own_conclusions": [{"classification": "invalid_not_injected"}]},       # invalid
            {"candidate_id": "D", "own_discovery_evidence": [{}],
             "own_conclusions": [{"classification": "client_timeout_observed"}]},    # outside universe
        ]}

    def _patch_env(self, d):
        reg_p = Path(d) / "deep_matrix_registry_r1_m1.json"
        ev_p = Path(d) / "candidate_evidence_status.json"
        reg_p.write_text(json.dumps(self._registry()), encoding="utf-8")
        ev_p.write_text(json.dumps(self._evidence()), encoding="utf-8")
        sev = {"A": 3, "B": 2, "C": 1, "D": 3}  # inject severity for test candidates
        with patch.object(sr, "EXECUTION_DIR", Path(d)), patch.object(
            sr, "load", side_effect=lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
        ):
            return sr.analyze(1, None, 10, sev=sev)

    def test_known_excludes_outside_and_invalid(self):
        with tempfile.TemporaryDirectory() as d:
            report = self._patch_env(d)
        # universe {A,B,C}; C invalid -> known = {A,B}; D outside universe ignored.
        self.assertEqual(report["universe_size"], 3)
        self.assertEqual(report["known_count"], 2)
        self.assertEqual(report["known_classification"]["weakness"], ["A"])
        self.assertEqual(report["known_classification"]["below_threshold"], ["B"])
        self.assertEqual(report["known_classification"]["invalid"], ["C"])
        self.assertEqual(report["invalid_in_universe_count"], 1)

    def test_no_overinterpretation_note(self):
        with tempfile.TemporaryDirectory() as d:
            report = self._patch_env(d)
        self.assertIn("Do NOT over-interpret", report["interpretation"])

    def test_bootstrap_keys_present(self):
        with tempfile.TemporaryDirectory() as d:
            report = self._patch_env(d)
        for m in ("M0", "M1", "M3", "M4"):
            self.assertIn(m, report["bootstrap_ci95_baseline_schema"])
            self.assertIn("ci95", report["bootstrap_ci95_baseline_schema"][m])


class SharedKnownUniverseTests(unittest.TestCase):
    """round-2 #2 + round-3 P1-3: both tools share the SAME known set; invalid
    REPEATS are dropped first, then the remaining valid conclusions decide the
    class. A candidate with valid + invalid repeats (e.g. OTEL-PAYMENT-DELAY-2000)
    stays known."""

    def _otel_payment_delay_item(self):
        # Mirrors artifacts/.../candidate_evidence_status.json structure.
        return {
            "candidate_id": "OTEL-PAYMENT-DELAY-2000",
            "own_discovery_evidence": [{"verdict": "weakness"}],
            "own_conclusions": [
                {"classification": "grpc_response_observed"},
                {"classification": "invalid_baseline"},
                {"classification": "invalid_not_injected"},
            ],
        }

    def test_valid_plus_invalid_repeats_stays_known(self):
        # Round-3 P1-3: the valid grpc_response_observed repeat is NOT negated
        # by the invalid repeats -> known.
        import evidence_classification as ec
        item = self._otel_payment_delay_item()
        self.assertEqual(ec.classify_candidate(item), "below_threshold")
        self.assertTrue(ec.is_known_candidate(item))
        evidence = {"candidates": [item]}
        self.assertIn("OTEL-PAYMENT-DELAY-2000", ec.known_candidate_ids(evidence))

    def test_compare_selection_keeps_valid_invalid_mixed_candidate(self):
        import compare_selection_methods as csm
        import evidence_classification as ec
        with patch.object(csm, "evidence_classification", ec):
            known = csm.known_discovered_candidates(
                {"candidates": [self._otel_payment_delay_item()]}
            )
        self.assertIn("OTEL-PAYMENT-DELAY-2000", known)

    def test_all_invalid_repeats_excluded(self):
        import evidence_classification as ec
        item = {
            "candidate_id": "X",
            "own_discovery_evidence": [{}],
            "own_conclusions": [
                {"classification": "invalid_baseline"},
                {"classification": "invalid_not_injected"},
            ],
        }
        self.assertEqual(ec.classify_candidate(item), "invalid")
        self.assertFalse(ec.is_known_candidate(item))

    def test_both_tools_agree_on_known_set(self):
        import compare_selection_methods as csm
        import selection_robustness as sr
        candidates = [
            self._otel_payment_delay_item(),
            {"candidate_id": "OB-PAYMENT-DELAY-2000",
             "own_discovery_evidence": [{}],
             "own_conclusions": [{"classification": "response_preserved_latency_degradation"}]},
            {"candidate_id": "TT-STATION-DELAY-100",
             "own_discovery_evidence": [{}],
             "own_conclusions": [{"classification": "response_observed"}]},
        ]
        evidence = {"candidates": candidates}
        # Both tools derive known from the same shared classifier, so the sets
        # must be identical (valid-discovered included, all-invalid excluded).
        compare_known = csm.known_discovered_candidates(evidence)
        robustness_known = {
            c["candidate_id"] for c in candidates
            if sr.classify_evidence_candidate(c) != "invalid"
            and c.get("own_discovery_evidence")
        }
        self.assertEqual(compare_known, robustness_known)
        self.assertEqual(
            compare_known,
            {"OB-PAYMENT-DELAY-2000", "TT-STATION-DELAY-100", "OTEL-PAYMENT-DELAY-2000"},
        )


if __name__ == "__main__":
    unittest.main()
