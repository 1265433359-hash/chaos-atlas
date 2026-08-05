from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import select_chaos_candidates as selector


def make_slice() -> dict:
    return {
        "kind": "NetworkChaos",
        "test_nodes": ["network_delay", "selector"],
        "source": "raw_yaml/NetworkChaos/does-not-exist.yaml",
        "selector": {"labels": {"app": "ts-station-service"}},
        "target_matches": ["deployment"],
        "service_matches": ["service"],
        "function_candidates": ["StationServiceImpl.queryForId"],
    }


def make_card(status: str, recommendation: str) -> dict:
    return {
        "id": "KB-TT-NETWORK-STATION-DELAY-001",
        "status": status,
        "evidence_state": "runtime_observed",
        "test_node": {
            "family": "NetworkChaos",
            "selector": {"label": {"app": "ts-station-service"}},
        },
        "_index_entry": {"injection_recommendation": recommendation},
    }


class CandidateDecisionTest(unittest.TestCase):
    def test_closed_boundary_is_not_ready_for_reinjection(self) -> None:
        _, decision, reasons, _ = selector.score_candidate(
            make_slice(),
            [
                make_card(
                    "validated_runtime_selector_pipeline_timeout_boundary_confirmed",
                    "stop_delay_after_timeout_boundary_require_slo_for_production_claim",
                )
            ],
            [],
        )

        self.assertEqual("closed_runtime_boundary_no_reinjection", decision)
        self.assertTrue(any("do not reinject" in reason for reason in reasons))

    def test_open_runtime_card_remains_ready(self) -> None:
        _, decision, _, _ = selector.score_candidate(
            make_slice(),
            [make_card("validated_runtime_selector_pipeline", "continue_bounded_replay")],
            [],
        )

        self.assertEqual("ready_candidate_with_runner", decision)

    def test_primary_test_node_is_deterministic(self) -> None:
        observed: list[str] = []
        original = selector.runtime_matches
        selector.runtime_matches = lambda records, service, node: observed.append(node) or []
        try:
            selector.score_candidate(make_slice(), [], [])
        finally:
            selector.runtime_matches = original
        self.assertEqual(["network_delay"], observed)

    def test_primary_test_node_skips_generic_selector(self) -> None:
        # Regression: 'selector' is a generic node; when a business-specific
        # node is present it must be the stable representative, otherwise
        # runtime-evidence matching lands on the wrong node.
        self.assertEqual("stress_cpu", selector.primary_test_node({"selector", "stress_cpu"}))
        self.assertEqual("network_delay", selector.primary_test_node({"network_delay", "selector"}))
        self.assertEqual("selector", selector.primary_test_node({"selector"}))
        self.assertEqual("", selector.primary_test_node(set()))

    def test_legacy_records_use_fuzzy_fallback_only_without_target_service(self) -> None:
        records = [
            {"id": "TT-NETWORK-BASIC-LEGACY", "test_node": "network_delay"},
            {"id": "TT-NETWORK-ORDER-EXPLICIT", "test_node": "network_delay", "target_service": "ts-order-service"},
        ]
        matches = selector.runtime_matches(records, "ts-basic-service", "network_delay")
        self.assertEqual(["TT-NETWORK-BASIC-LEGACY"], [record["id"] for record in matches])

    def test_output_runtime_matches_uses_slice_node_not_cli_node(self) -> None:
        # Regression: the per-candidate runtime_matches output must use the
        # slice's own test node, not the CLI --node filter. The internal
        # scoring call already did; the emitted field must match.
        records = [
            {
                "id": "TT-NETWORK-STATION-DELAY-001",
                "test_node": "network_delay",
                "target_service": "ts-station-service",
                "classification": "client_timeout_observed",
            }
        ]
        selected = selector.select_candidates(
            slices=[make_slice()],  # test_nodes = network_delay, selector
            node=None,
            kind=None,
            service=None,
            limit=10,
            cards=[],
            runtime_records=records,
        )
        self.assertEqual(1, len(selected))
        self.assertEqual(["TT-NETWORK-STATION-DELAY-001"], [m["id"] for m in selected[0]["runtime_matches"]])


if __name__ == "__main__":
    unittest.main()
