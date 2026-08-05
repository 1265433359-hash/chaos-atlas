from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_stress_with_cgroup


class OrchestrationSelectorTest(unittest.TestCase):
    def test_cgroup_selector_comes_from_mutation(self) -> None:
        namespace, selector, kind = run_stress_with_cgroup.mutation_target(
            {
                "kind": "StressChaos",
                "metadata": {"namespace": "train-ticket-lab", "name": "x"},
                "spec": {
                    "selector": {
                        "namespaces": ["train-ticket-lab"],
                        "labelSelectors": {"component": "station", "app": "ts-station-service"},
                    }
                },
            }
        )
        self.assertEqual("train-ticket-lab", namespace)
        self.assertEqual("app=ts-station-service,component=station", selector)
        self.assertEqual("StressChaos", kind)

    def test_cgroup_selector_rejects_cross_namespace_target(self) -> None:
        with self.assertRaises(ValueError):
            run_stress_with_cgroup.mutation_target(
                {
                    "kind": "StressChaos",
                    "metadata": {"namespace": "train-ticket-lab", "name": "x"},
                    "spec": {"selector": {"namespaces": ["default"], "labelSelectors": {"app": "demo"}}},
                }
            )

    def test_resource_exists_treats_only_not_found_as_absent(self) -> None:
        # Regression: only an explicit NotFound must be treated as "absent".
        # A transient/RBAC failure must raise so the parent fallback cleanup
        # cannot be skipped on a failed lookup.
        with patch.object(run_stress_with_cgroup, "run_kubectl", return_value=(1, "", "not found")):
            self.assertFalse(run_stress_with_cgroup.resource_exists("StressChaos", "train-ticket-lab", "x"))
        with patch.object(run_stress_with_cgroup, "run_kubectl", return_value=(0, "", "")):
            self.assertTrue(run_stress_with_cgroup.resource_exists("StressChaos", "train-ticket-lab", "x"))
        with patch.object(run_stress_with_cgroup, "run_kubectl", return_value=(1, "", "Error from server (Forbidden)")):
            with self.assertRaises(RuntimeError):
                run_stress_with_cgroup.resource_exists("StressChaos", "train-ticket-lab", "x")


if __name__ == "__main__":
    unittest.main()
