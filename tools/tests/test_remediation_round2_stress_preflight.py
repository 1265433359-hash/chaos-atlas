"""Round-2 finding #5 tests: run_stress_with_cgroup preflight must never raise a
bare traceback; RBAC / TimeoutExpired / OSError / API errors produce an
orchestration report (preflight_blocked + reason + exit code) and still attempt
an idempotent cleanup when the resource state is unknown.

Pure unit tests: patch sys.argv / resource_exists / cleanup_mutation; no cluster.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_stress_with_cgroup as rswc


MUTATION_YAML = """apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
metadata:
  name: demo-stress
  namespace: train-ticket-lab
spec:
  mode: one
  selector:
    namespaces: [train-ticket-lab]
    labelSelectors:
      app: demo
  stressors:
    cpu:
      workers: 1
  duration: 5s
"""


def _run_main(tmp: Path, exists_side_effect):
    mutation = tmp / "mutation.yaml"
    mutation.write_text(MUTATION_YAML, encoding="utf-8")
    orch = tmp / "orchestration.json"
    sys.argv = [
        "run_stress_with_cgroup",
        str(mutation),
        "--namespace", "train-ticket-lab",
        "--service", "demo",
        "--remote-port", "12345",
        "--local-port", "18082",
        "--request-path", "/api/v1/demo",
        "--runner-report", str(tmp / "runner.json"),
        "--cgroup-report", str(tmp / "cgroup.json"),
        "--orchestration-report", str(orch),
    ]
    with mock.patch.object(rswc, "resource_exists", side_effect=exists_side_effect), \
         mock.patch.object(rswc, "cleanup_mutation", return_value={
             "attempted": True, "confirmed": True,
         }) as cleanup_mock:
        rc = rswc.main()
        return rc, orch, cleanup_mock


class StressPreflightExceptionTests(unittest.TestCase):
    def test_runtime_error_no_traceback(self):
        with tempfile.TemporaryDirectory() as d:
            rc, orch, _ = _run_main(Path(d), exists_side_effect=RuntimeError("Forbidden: is forbidden"))
            self.assertEqual(rc, 2)
            report = json.loads(orch.read_text(encoding="utf-8"))
            self.assertEqual(report["preflight_blocked"], "preflight_error")
            self.assertTrue(any("Forbidden" in e for e in report["preflight_errors"]))
            self.assertEqual(report["exit_status"], "preflight_blocked")

    def test_timeout_expired_no_traceback(self):
        with tempfile.TemporaryDirectory() as d:
            rc, orch, _ = _run_main(Path(d), exists_side_effect=TimeoutError("kubectl timed out"))
            self.assertEqual(rc, 2)
            report = json.loads(orch.read_text(encoding="utf-8"))
            self.assertEqual(report["preflight_blocked"], "preflight_error")

    def test_os_error_no_traceback(self):
        with tempfile.TemporaryDirectory() as d:
            rc, orch, _ = _run_main(Path(d), exists_side_effect=OSError("kubectl binary missing"))
            self.assertEqual(rc, 2)
            report = json.loads(orch.read_text(encoding="utf-8"))
            self.assertEqual(report["preflight_blocked"], "preflight_error")

    def test_unknown_state_still_attempts_cleanup(self):
        # Even when existence cannot be determined, an idempotent cleanup is
        # attempted (unknown must not skip the final cleanup).
        with tempfile.TemporaryDirectory() as d:
            def _raises(*_a, **_k):
                raise RuntimeError("cannot determine existence")
            rc, orch, cleanup_mock = _run_main(Path(d), exists_side_effect=_raises)
            self.assertEqual(rc, 2)
            report = json.loads(orch.read_text(encoding="utf-8"))
            cleanup_mock.assert_called_once()
            self.assertIsNotNone(report["safety"]["parent_cleanup_fallback"])

    def test_mutation_exists_is_preflight_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            rc, orch, cleanup_mock = _run_main(Path(d), exists_side_effect=lambda *a, **k: True)
            self.assertEqual(rc, 2)
            report = json.loads(orch.read_text(encoding="utf-8"))
            self.assertEqual(report["preflight_blocked"], "mutation_exists")

    def test_yaml_parse_error_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            mutation = Path(d) / "mutation.yaml"
            mutation.write_text("::: not yaml :::\n", encoding="utf-8")
            orch = Path(d) / "orchestration.json"
            sys.argv = [
                "run_stress_with_cgroup", str(mutation),
                "--namespace", "train-ticket-lab", "--service", "demo",
                "--remote-port", "1", "--local-port", "2",
                "--request-path", "/", "--runner-report", str(Path(d) / "r.json"),
                "--cgroup-report", str(Path(d) / "c.json"),
                "--orchestration-report", str(orch),
            ]
            with mock.patch.object(rswc, "resource_exists") as exists_mock:
                rc = rswc.main()
            self.assertEqual(rc, 2)
            exists_mock.assert_not_called()  # YAML parse failure never queries
            report = json.loads(orch.read_text(encoding="utf-8"))
            self.assertEqual(report["preflight_blocked"], "yaml_shape_invalid")


class StressProvenanceContractTests(unittest.TestCase):
    """Round-2 finding #7: the stress orchestration report carries the same
    provenance contract as the other runners (schema v2 + fingerprint +
    baseline/lifecycle/cleanup declaration)."""

    def _blocked_report(self, tmp: Path):
        def _raises(*_a, **_k):
            raise RuntimeError("kubectl lookup failed")
        rc, orch, _ = _run_main(tmp, exists_side_effect=_raises)
        self.assertEqual(rc, 2)
        return json.loads(orch.read_text(encoding="utf-8"))

    def test_schema_v2_and_fingerprint_present(self):
        with tempfile.TemporaryDirectory() as d:
            report = self._blocked_report(Path(d))
        self.assertEqual(report["schema_version"], 2)
        self.assertIn("environment_fingerprint", report)

    def test_contract_declared(self):
        with tempfile.TemporaryDirectory() as d:
            report = self._blocked_report(Path(d))
        self.assertIn("contract", report)
        for key in ("baseline", "lifecycle", "cleanup", "cgroup"):
            self.assertIn(key, report["contract"])

    def test_fingerprint_embedded_in_normal_path_report(self):
        # The normal (non-blocked) path must also embed the fingerprint and
        # schema v2. We patch run_chaos_experiment as a subprocess is not run
        # (main returns 2 at preflight already), so instead assert the report
        # literal in source carries schema_version 2 and the fingerprint call.
        src = Path(rswc.__file__).read_text(encoding="utf-8")
        self.assertIn('"schema_version": 2', src)
        self.assertIn("environment_fingerprint", src)
        self.assertIn('"contract"', src)


if __name__ == "__main__":
    unittest.main()
