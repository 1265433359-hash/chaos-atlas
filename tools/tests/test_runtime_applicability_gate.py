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

    def test_current_online_boutique_namespace_is_allowed(self) -> None:
        def kubectl_for_allowed_namespace(args: list[str], timeout: int = 20):
            if len(args) >= 3 and args[0:2] == ["get", "crd"]:
                return 0, "crd", ""
            return 1, "", "not found"

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mutation.yaml"
            path.write_text(
                mutation(namespace="chaosatlas-online-boutique"),
                encoding="utf-8",
            )
            with patch.object(gate, "run_kubectl", side_effect=kubectl_for_allowed_namespace), patch.object(
                gate,
                "chaos_components",
                return_value=(
                    {"ready": True, "controller_pods": ["controller"], "daemon_pods": ["daemon"]},
                    [],
                ),
            ), patch.object(gate, "target_pods", return_value=([READY_POD], [])):
                result = gate.check_mutation(path)
        self.assertNotEqual("blocked", result["decision"])
        self.assertTrue(result["checks"]["scope_guard"]["metadata_namespace_ok"])

    def test_current_otel_namespace_is_allowed(self) -> None:
        def kubectl_for_allowed_namespace(args: list[str], timeout: int = 20):
            if len(args) >= 3 and args[0:2] == ["get", "crd"]:
                return 0, "crd", ""
            return 1, "", "not found"

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mutation.yaml"
            path.write_text(mutation(namespace="chaosatlas-otel"), encoding="utf-8")
            with patch.object(gate, "run_kubectl", side_effect=kubectl_for_allowed_namespace), patch.object(
                gate,
                "chaos_components",
                return_value=(
                    {"ready": True, "controller_pods": ["controller"], "daemon_pods": ["daemon"]},
                    [],
                ),
            ), patch.object(gate, "target_pods", return_value=([READY_POD], [])):
                result = gate.check_mutation(path)
        self.assertNotEqual("blocked", result["decision"])
        self.assertTrue(result["checks"]["scope_guard"]["metadata_namespace_ok"])

    def test_current_sock_shop_namespace_is_allowed(self) -> None:
        def kubectl_for_allowed_namespace(args: list[str], timeout: int = 20):
            if len(args) >= 3 and args[0:2] == ["get", "crd"]:
                return 0, "crd", ""
            return 1, "", "not found"

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mutation.yaml"
            path.write_text(mutation(namespace="chaosatlas-sock-shop"), encoding="utf-8")
            with patch.object(gate, "run_kubectl", side_effect=kubectl_for_allowed_namespace), patch.object(
                gate,
                "chaos_components",
                return_value=({"ready": True, "controller_pods": ["controller"], "daemon_pods": ["daemon"]}, []),
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

    def test_http_prerequisite_accepts_all_daemons_with_read_only_capability_probe(self) -> None:
        def kubectl(args, timeout=30):
            if args[0] == "logs":
                return 0, "ordinary daemon log", ""
            if args[0] == "exec":
                return 0, "HTTPCHAOS_CAPABILITY_OK", ""
            raise AssertionError(args)

        with patch.object(gate, "run_kubectl", side_effect=kubectl):
            result = gate.daemon_prerequisite("HTTPChaos", ["daemon-a", "daemon-b"])

        self.assertEqual("pass", result["status"])
        self.assertEqual("read_only_daemon_capability_probe", result["evidence_source"])

    def test_http_prerequisite_blocks_when_any_daemon_capability_probe_fails(self) -> None:
        def kubectl(args, timeout=30):
            if args[0] == "logs":
                return 0, "ordinary daemon log", ""
            if args[0] == "exec" and args[3] == "daemon-a":
                return 0, "HTTPCHAOS_CAPABILITY_OK", ""
            if args[0] == "exec" and args[3] == "daemon-b":
                return 1, "", "missing xt_TPROXY"
            raise AssertionError(args)

        with patch.object(gate, "run_kubectl", side_effect=kubectl):
            result = gate.daemon_prerequisite("HTTPChaos", ["daemon-a", "daemon-b"])

        self.assertEqual("blocked", result["status"])
        self.assertEqual("http_tproxy_positive_evidence_missing", result["blocker"])

    def test_http_target_port_mismatch_is_an_explicit_error_with_other_blocker(self) -> None:
        content = """apiVersion: chaos-mesh.org/v1alpha1
kind: HTTPChaos
metadata:
  name: bad-http-target
  namespace: chaosatlas-sock-shop
spec:
  mode: one
  selector:
    namespaces: [chaosatlas-sock-shop]
    labelSelectors:
      name: catalogue-db
  target: Request
  port: 80
  path: /catalogue
  delay: 500ms
  duration: 30s
"""

        def kubectl(args: list[str], timeout: int = 20):
            if args[:2] == ["get", "crd"]:
                return 0, "crd", ""
            if args and args[0] == "logs":
                return 0, "ordinary daemon log", ""
            return 1, "", 'Error from server (NotFound): httpchaos "bad-http-target" not found'

        pod = {
            **READY_POD,
            "metadata": {"namespace": "chaosatlas-sock-shop", "name": "catalogue-db-0"},
            "spec": {"containers": [{"ports": [{"containerPort": 3306}]}]},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mutation.yaml"
            path.write_text(content, encoding="utf-8")
            with patch.object(gate, "run_kubectl", side_effect=kubectl), patch.object(
                gate,
                "chaos_components",
                return_value=({"ready": True, "controller_pods": ["controller"], "daemon_pods": ["daemon"]}, []),
            ), patch.object(gate, "target_pods", return_value=([pod], [])):
                result = gate.check_mutation(path)

        self.assertEqual("blocked", result["decision"])
        self.assertFalse(result["checks"]["target_port_exists"])
        self.assertIn("target_port_missing:80", result["errors"])
        self.assertIn("http_tproxy_positive_evidence_missing", result["errors"])

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

    def test_schedule_uses_nested_podchaos_scope_for_runtime_gate(self) -> None:
        content = """apiVersion: chaos-mesh.org/v1alpha1
kind: Schedule
metadata:
  name: scheduled-fault
  namespace: chaosatlas-sock-shop
spec:
  type: PodChaos
  schedule: '@every 1s'
  podChaos:
    action: pod-kill
    mode: one
    selector:
      namespaces: [chaosatlas-sock-shop]
      labelSelectors:
        name: payment
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schedule.yaml"
            path.write_text(content, encoding="utf-8")

            def kubectl_for_schedule(args: list[str], timeout: int = 20):
                if args[:2] == ["get", "crd"]:
                    return 0, "crd", ""
                return 1, "", "not found"

            with patch.object(gate, "run_kubectl", side_effect=kubectl_for_schedule), patch.object(
                gate,
                "chaos_components",
                return_value=(
                    {"ready": True, "controller_pods": ["controller"], "daemon_pods": ["daemon"]},
                    [],
                ),
            ), patch.object(gate, "target_pods", return_value=([READY_POD], [])):
                result = gate.check_mutation(path)
        self.assertNotEqual("blocked", result["decision"])
        self.assertEqual("Schedule", result["kind"])
        self.assertEqual({"name": "payment"}, result["selector"]["labelSelectors"])

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
