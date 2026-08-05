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


def mutation(namespace: str = "train-ticket-lab", mode: str = "one") -> str:
    return f"""apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
metadata:
  name: test-stress
  namespace: {namespace}
spec:
  mode: {mode}
  selector:
    namespaces: [{namespace}]
    labelSelectors:
      app: demo
  stressors:
    cpu:
      workers: 1
  duration: 1s
"""


class RuntimeGateTest(unittest.TestCase):
    def check(self, content: str) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mutation.yaml"
            path.write_text(content, encoding="utf-8")
            with patch.object(gate, "run_kubectl", return_value=(1, "", "not found")), patch.object(
                gate, "chaos_components", return_value=(
                    {"ready": True, "controller_pods": ["controller"], "daemon_pods": ["daemon"]}, []
                ),
            ), patch.object(gate, "target_pods", return_value=([READY_POD], [])):
                return gate.check_mutation(path)

    def test_namespace_is_a_hard_boundary(self) -> None:
        result = self.check(mutation(namespace="default"))
        self.assertEqual("blocked", result["decision"])
        self.assertFalse(result["checks"]["scope_guard"]["metadata_namespace_ok"])

    def test_mode_all_is_rejected(self) -> None:
        result = self.check(mutation(mode="all"))
        self.assertEqual("blocked", result["decision"])
        self.assertFalse(result["checks"]["scope_guard"]["mode_ok"])

    def test_http_prerequisite_fails_closed_without_positive_signal(self) -> None:
        with patch.object(gate, "run_kubectl", return_value=(0, "ordinary daemon log", "")):
            result = gate.daemon_prerequisite("HTTPChaos", ["daemon"])
        self.assertEqual("blocked", result["status"])
        self.assertEqual("http_tproxy_positive_evidence_missing", result["blocker"])

    def test_http_prerequisite_accepts_positive_signal(self) -> None:
        with patch.object(gate, "run_kubectl", return_value=(0, "tproxy ready; ebtables loaded", "")):
            result = gate.daemon_prerequisite("HTTPChaos", ["daemon"])
        self.assertEqual("pass", result["status"])


if __name__ == "__main__":
    unittest.main()
