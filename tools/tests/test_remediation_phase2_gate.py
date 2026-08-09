"""Phase-2 remediation tests: runtime gate fail-closed + selector safety.

Covers review findings #2:
  - kubectl timeout / RBAC on mutation-name lookup must NOT be treated as
    "name available" (fail-open) -> fail closed with structured status.
  - empty labelSelectors must be rejected, and the gate must NOT issue a
    whole-namespace pod query in that case.

Pure unit tests: monkeypatch run_kubectl / target_pods / chaos_components.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import runtime_applicability_gate as gate

READY_POD = {
    "metadata": {"namespace": "train-ticket-lab", "name": "demo-0"},
    "status": {
        "conditions": [{"type": "Ready", "status": "True"}],
        "containerStatuses": [{"restartCount": 0}],
    },
    "spec": {"containers": [{"ports": [{"containerPort": 12345}]}]},
}


def mutation(labels_block: str = "      app: demo\n", namespace: str = "train-ticket-lab") -> str:
    return f"""apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
metadata:
  name: test-stress
  namespace: {namespace}
spec:
  mode: one
  selector:
    namespaces: [{namespace}]
    labelSelectors:
{labels_block}
  stressors:
    cpu:
      workers: 1
  duration: 1s
"""


def _run(content: str, kubectl_side_effect, target_pods=( [READY_POD], [] )):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "mutation.yaml"
        path.write_text(content, encoding="utf-8")
        with patch.object(gate, "run_kubectl", side_effect=kubectl_side_effect), patch.object(
            gate, "chaos_components", return_value=(
                {"ready": True, "controller_pods": ["c"], "daemon_pods": ["d"]}, []
            ),
        ), patch.object(gate, "target_pods", return_value=target_pods):
            return gate.check_mutation(path)


class GateFailClosedTests(unittest.TestCase):
    """mutation-name lookup must never treat timeout/RBAC as 'available'."""

    def _default_kubectl(self, resource_get_result=(1, "", 'Error from server (NotFound): ... "x" not found')):
        def _kb(args, timeout=20):
            if args[0:2] == ["get", "crd"]:
                return 0, "crd", ""
            if args[0] == "get" and len(args) >= 2 and args[1] in ("stresschaos", "podchaos", "networkchaos", "httpchaos"):
                return resource_get_result
            return 1, "", "not found"
        return _kb

    def test_timeout_on_name_lookup_fails_closed(self):
        result = _run(
            mutation(),
            self._default_kubectl(resource_get_result=(124, "", "kubectl timed out")),
        )
        self.assertEqual("blocked", result["decision"])
        self.assertFalse(result["checks"]["mutation_name_available"])
        self.assertEqual("unknown_timeout", result["checks"]["mutation_name_status"])
        self.assertTrue(any("failing closed" in e for e in result["errors"]))

    def test_rbac_on_name_lookup_fails_closed(self):
        result = _run(
            mutation(),
            self._default_kubectl(resource_get_result=(1, "", 'Error from server (Forbidden): is forbidden')),
        )
        self.assertEqual("blocked", result["decision"])
        self.assertFalse(result["checks"]["mutation_name_available"])
        self.assertEqual("unknown_error", result["checks"]["mutation_name_status"])

    def test_explicit_not_found_is_available(self):
        result = _run(
            mutation(),
            self._default_kubectl(resource_get_result=(1, "", 'Error from server (NotFound): ... "x" not found')),
        )
        self.assertTrue(result["checks"]["mutation_name_available"])
        self.assertEqual("available", result["checks"]["mutation_name_status"])

    def test_name_exists_is_blocked(self):
        result = _run(
            mutation(),
            self._default_kubectl(resource_get_result=(0, "exists", "")),
        )
        self.assertEqual("blocked", result["decision"])
        self.assertFalse(result["checks"]["mutation_name_available"])
        self.assertEqual("exists", result["checks"]["mutation_name_status"])


class EmptySelectorTests(unittest.TestCase):
    """Empty labelSelectors must be rejected and never trigger a namespace-wide query."""

    def test_empty_selector_is_blocked(self):
        # no labelSelectors at all
        content = """apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
metadata:
  name: test-stress
  namespace: train-ticket-lab
spec:
  mode: one
  selector:
    namespaces: [train-ticket-lab]
  stressors:
    cpu:
      workers: 1
  duration: 1s
"""
        result = _run(content, lambda args, timeout=20: (1, "", "not found"))
        self.assertEqual("blocked", result["decision"])
        self.assertFalse(result["checks"]["scope_guard"]["selector_labels_ok"])

    def test_empty_selector_never_queries_pods(self):
        content = """apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
metadata:
  name: test-stress
  namespace: train-ticket-lab
spec:
  mode: one
  selector:
    namespaces: [train-ticket-lab]
  stressors:
    cpu:
      workers: 1
  duration: 1s
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mutation.yaml"
            path.write_text(content, encoding="utf-8")
            with patch.object(gate, "run_kubectl", side_effect=lambda args, timeout=20: (1, "", "not found")), patch.object(
                gate, "chaos_components", return_value=(
                    {"ready": True, "controller_pods": ["c"], "daemon_pods": ["d"]}, []
                ),
            ), patch.object(gate, "target_pods", return_value=([READY_POD], [])) as tp:
                gate.check_mutation(path)
                tp.assert_not_called()

    def test_non_empty_selector_still_queries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mutation.yaml"
            path.write_text(mutation(), encoding="utf-8")
            with patch.object(gate, "run_kubectl", side_effect=lambda args, timeout=20: (
                (0, "crd", "") if args[0:2] == ["get", "crd"] else (1, "", "not found")
            )), patch.object(
                gate, "chaos_components", return_value=(
                    {"ready": True, "controller_pods": ["c"], "daemon_pods": ["d"]}, []
                ),
            ), patch.object(gate, "target_pods", return_value=([READY_POD], [])) as tp:
                gate.check_mutation(path)
                tp.assert_called_once()


if __name__ == "__main__":
    unittest.main()
