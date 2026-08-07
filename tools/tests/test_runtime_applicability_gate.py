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

    def test_isolated_project_lab_namespace_is_allowed(self) -> None:
        def kubectl_for_allowed_lab(args: list[str], timeout: int = 20):
            if len(args) >= 3 and args[0:2] == ["get", "crd"]:
                return 0, "crd", ""
            return 1, "", "not found"

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mutation.yaml"
            path.write_text(mutation(namespace="online-boutique-lab"), encoding="utf-8")
            with patch.object(gate, "run_kubectl", side_effect=kubectl_for_allowed_lab), patch.object(
                gate, "chaos_components", return_value=(
                    {"ready": True, "controller_pods": ["controller"], "daemon_pods": ["daemon"]}, []
                ),
            ), patch.object(gate, "target_pods", return_value=([READY_POD], [])):
                result = gate.check_mutation(path)
        self.assertNotEqual("blocked", result["decision"])
        self.assertTrue(result["checks"]["scope_guard"]["metadata_namespace_ok"])

    def test_mode_all_is_rejected(self) -> None:
        result = self.check(mutation(mode="all"))
        self.assertEqual("blocked", result["decision"])
        self.assertFalse(result["checks"]["scope_guard"]["mode_ok"])

    def test_terminating_pod_is_not_ready_for_injection(self) -> None:
        pod = {
            **READY_POD,
            "metadata": {
                **READY_POD["metadata"],
                "deletionTimestamp": "2026-08-07T03:15:31Z",
            },
        }
        self.assertFalse(gate.ready_condition(pod))

    def test_http_prerequisite_fails_closed_without_positive_signal(self) -> None:
        with patch.object(gate, "run_kubectl", return_value=(0, "ordinary daemon log", "")):
            result = gate.daemon_prerequisite("HTTPChaos", ["daemon"])
        self.assertEqual("blocked", result["status"])
        self.assertEqual("http_tproxy_positive_evidence_missing", result["blocker"])

    def test_http_prerequisite_accepts_positive_signal(self) -> None:
        with patch.object(gate, "run_kubectl", return_value=(0, "tproxy ready; ebtables loaded", "")):
            result = gate.daemon_prerequisite("HTTPChaos", ["daemon"])
        self.assertEqual("pass", result["status"])

    def test_http_prerequisite_negation_fragments_never_pass(self) -> None:
        # Regression: the positive-evidence regex must not match negated
        # phrases; a daemon reporting that tproxy is NOT available must never
        # be treated as positive evidence for HTTPChaos injection.
        negated_fragments = [
            "tproxy not supported on this kernel",
            "ebtables unavailable",
            "ERROR: tproxy support is not enabled",
            "ebtables missing; cannot apply HTTPChaos rules",
            "tproxy failed to load",
        ]
        for fragment in negated_fragments:
            with self.subTest(fragment=fragment), patch.object(
                gate, "run_kubectl", return_value=(0, fragment, "")
            ):
                result = gate.daemon_prerequisite("HTTPChaos", ["daemon"])
                self.assertEqual("blocked", result["status"], fragment)
                self.assertEqual("http_tproxy_positive_evidence_missing", result["blocker"], fragment)

    def test_check_mutation_malformed_yaml_is_blocked_not_crash(self) -> None:
        # Regression: yaml.safe_load failures must produce a blocked decision
        # instead of an unhandled traceback escaping check_mutation.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.yaml"
            path.write_text("kind: StressChaos\n  bad_indent: [unclosed\n", encoding="utf-8")
            result = gate.check_mutation(path)
        self.assertEqual("blocked", result["decision"])
        self.assertTrue(any("not parseable" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
