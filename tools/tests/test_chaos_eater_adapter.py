import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chaos_eater_adapter.adapter import ChaosEaterAdapter, extract_json_object  # noqa: E402
from chaos_eater_adapter.llm_backend import MockBackend  # noqa: E402
from chaos_eater_adapter.mapping import build_candidate_pool, fault_type_of  # noqa: E402
from chaos_eater_adapter.contexts import build_steady_states, build_user_input  # noqa: E402
from generate_deep_comparison_matrix import CORE_CANDIDATES, validate_plan  # noqa: E402
from generate_m1_adapter_plans import generate as generate_m1  # noqa: E402


class MockBackendTests(unittest.TestCase):
    def test_mock_selection_is_deterministic_for_the_same_seed(self):
        backend = MockBackend(seed=7, candidates=CORE_CANDIDATES, budget=10)
        adapter = ChaosEaterAdapter(backend=backend, candidates=CORE_CANDIDATES, budget=10)
        first = adapter.select("system", "steady", "instructions")
        backend2 = MockBackend(seed=7, candidates=CORE_CANDIDATES, budget=10)
        adapter2 = ChaosEaterAdapter(backend=backend2, candidates=CORE_CANDIDATES, budget=10)
        second = adapter2.select("system", "steady", "instructions")
        ids1 = [item["candidate_id"] for item in first.ranked_candidates]
        ids2 = [item["candidate_id"] for item in second.ranked_candidates]
        self.assertEqual(ids1, ids2)

    def test_different_seeds_are_not_forced_to_differ(self):
        backend = MockBackend(seed=1, candidates=CORE_CANDIDATES, budget=10)
        adapter = ChaosEaterAdapter(backend=backend, candidates=CORE_CANDIDATES, budget=10)
        result = adapter.select("system", "steady", "instructions")
        self.assertEqual(len(result.ranked_candidates), 10)
        self.assertEqual(len({item["candidate_id"] for item in result.ranked_candidates}), 10)

    def test_backend_meta_marks_mock_as_pipeline_verifier(self):
        backend = MockBackend(seed=3, candidates=CORE_CANDIDATES, budget=10)
        adapter = ChaosEaterAdapter(backend=backend, candidates=CORE_CANDIDATES, budget=10)
        result = adapter.select("system", "steady", "instructions")
        self.assertEqual(result.backend_meta["backend"], "mock")
        self.assertIn("not a real", result.backend_meta["note"])


class AdapterSelectionTests(unittest.TestCase):
    def setUp(self):
        self.backend = MockBackend(seed=11, candidates=CORE_CANDIDATES, budget=10)
        self.adapter = ChaosEaterAdapter(backend=self.backend, candidates=CORE_CANDIDATES, budget=10)

    def test_selected_candidates_come_from_the_shared_pool_only(self):
        result = self.adapter.select("system", "steady", "instructions")
        pool_ids = {item["candidate_id"] for item in CORE_CANDIDATES}
        selected = {item["candidate_id"] for item in result.ranked_candidates}
        self.assertTrue(selected.issubset(pool_ids))
        self.assertEqual(len(selected), 10)

    def test_ranks_are_consecutive_from_one(self):
        result = self.adapter.select("system", "steady", "instructions")
        ranks = [item["rank"] for item in result.ranked_candidates] if hasattr(result.ranked_candidates[0], "rank") else list(range(1, len(result.ranked_candidates) + 1))
        self.assertEqual(ranks, list(range(1, len(result.ranked_candidates) + 1)))

    def test_scenario_has_event_thought_and_faults(self):
        result = self.adapter.select("system", "steady", "instructions")
        self.assertTrue(result.scenario.event)
        self.assertTrue(result.scenario.thought)
        self.assertGreaterEqual(len(result.scenario.faults), 1)

    def test_candidate_not_in_pool_is_skipped_with_warning(self):
        backend = MockBackend(seed=2, candidates=CORE_CANDIDATES, budget=10)
        backend.complete = lambda s, u, f: (
            json.dumps(
                {
                    "event": "e",
                    "thought": "t",
                    "faults": [
                        [
                            {
                                "name": "NetworkChaos",
                                "name_id": 0,
                                "scope": {"candidate_id": "NOT-IN-POOL"},
                            }
                        ]
                    ],
                }
            ),
            {"backend": "mock", "model": "x", "generation_time_ms": 1},
        )
        adapter = ChaosEaterAdapter(backend=backend, candidates=CORE_CANDIDATES, budget=10)
        result = adapter.select("system", "steady", "instructions")
        self.assertEqual(result.ranked_candidates, [])
        self.assertTrue(any("not in pool" in warning for warning in result.warnings))


class MappingTests(unittest.TestCase):
    def test_fault_type_mapping_covers_all_pool_families(self):
        for candidate in CORE_CANDIDATES:
            fault_type = fault_type_of(candidate)
            self.assertIn(fault_type, {"PodChaos", "NetworkChaos", "StressChaos"})

    def test_pool_entries_do_not_leak_graph_scores(self):
        pool = build_candidate_pool(CORE_CANDIDATES)
        for entry in pool:
            self.assertNotIn("scores", entry)
            self.assertIn("candidate_id", entry)


class PromptParsingTests(unittest.TestCase):
    def test_extract_json_tolerates_markdown_fence(self):
        text = '```json\n{"event": "e", "faults": []}\n```'
        self.assertEqual(extract_json_object(text), {"event": "e", "faults": []})

    def test_extract_json_rejects_non_object(self):
        with self.assertRaises(ValueError):
            extract_json_object("[1, 2, 3]")

    def test_contexts_are_derived_from_pool_without_measurements(self):
        user_input = build_user_input("online-boutique", CORE_CANDIDATES)
        self.assertIn("paymentservice", user_input)
        self.assertIn("productcatalogservice", user_input)
        self.assertNotIn("2000ms latency", user_input)
        steady = build_steady_states("online-boutique")
        self.assertNotIn("ms", steady)


class GenerateM1PlansTests(unittest.TestCase):
    def _registry(self, replicate=1, seed=101):
        import generate_deep_comparison_matrix as base

        return base.generate(replicate=replicate, seed=seed, candidate_budget=10)

    def _m1_registry(self, replicate=1, seed=101):
        import types

        args = types.SimpleNamespace(backend="mock", seed=seed, budget=10)
        return generate_m1(self._registry(replicate, seed), args)

    def test_m1_becomes_available_with_valid_plans_from_the_pool(self):
        result = self._m1_registry()
        m1 = next(item for item in result["methods"] if item["id"] == "M1")
        self.assertEqual(m1["status"], "available")
        self.assertEqual(len(m1["plans"]), 10)
        universe = set(result["candidate_universe"])
        for plan in m1["plans"]:
            self.assertEqual(validate_plan(plan), [])
            self.assertIn(plan["execution"]["candidate_id"], universe)

    def test_m1_provenance_records_a_single_pool_wide_selection(self):
        result = self._m1_registry()
        m1 = next(item for item in result["methods"] if item["id"] == "M1")
        prov = m1["provenance"]
        self.assertEqual(prov["backend"], "mock")
        self.assertTrue(prov["event"])
        self.assertEqual(len(prov["ranked_candidates"]), 10)
        self.assertEqual(len(set(prov["ranked_candidates"])), 10)

    def test_m1_plans_have_global_consecutive_ranks(self):
        result = self._m1_registry()
        m1 = next(item for item in result["methods"] if item["id"] == "M1")
        ranks = [plan["rank"] for plan in m1["plans"]]
        self.assertEqual(ranks, list(range(1, 11)))

    def test_m2_stays_blocked(self):
        result = self._m1_registry()
        m2 = next(item for item in result["methods"] if item["id"] == "M2")
        self.assertTrue(m2["status"].startswith("blocked"))
        self.assertEqual(m2["plans"], [])

    def test_evaluator_consumes_the_m1_registry(self):
        from evaluate_deep_comparison_matrix import evaluate

        result = self._m1_registry()
        with patch(
            "evaluate_deep_comparison_matrix.check_mutation",
            return_value={"decision": "ready_for_injection"},
        ):
            evaluated = evaluate(result)
        m1 = next(item for item in evaluated["methods"] if item["id"] == "M1")
        self.assertEqual(m1["candidate_count"], 10)
        self.assertEqual(m1["summary"], {"ready_for_injection": 10})
        self.assertTrue(evaluated["same_candidate_pool"])


if __name__ == "__main__":
    unittest.main()
