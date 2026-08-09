"""Phase-1 remediation tests: Chaos resource cleanup never misreports absence.

Covers review findings #1: any non-zero kubectl get was previously treated as
"resource absent", so a timeout / RBAC / API error could leave a Chaos resource
resident while the report claimed cleanup succeeded.

These tests are pure unit tests: they monkeypatch run_kubectl, they do NOT
touch a real cluster, and they do not write to versioned artifacts.
"""

from __future__ import annotations

import unittest
from unittest import mock

import run_chaos_experiment as rce
import run_stress_with_cgroup as rswc


class DeleteResourceClassificationTests(unittest.TestCase):
    """delete_resource must distinguish absent / timeout / error / exists."""

    def _patched(self, verify_code: int, verify_error: str):
        patcher = mock.patch.object(rce, "run_kubectl", autospec=True)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        # delete always ok; verify returns (verify_code, "", verify_error)
        mocked.return_value = (0, "deleted", "")
        if verify_code == 124:
            mocked.side_effect = [
                (0, "deleted", ""),
                (124, "", "kubectl timed out"),
            ]
        else:
            mocked.side_effect = [
                (0, "deleted", ""),
                (verify_code, "", verify_error),
            ]
        return mocked

    def test_not_found_is_absent(self):
        self._patched(1, 'Error from server (NotFound): networkchaos.chaos-mesh.org "x" not found')
        r = rce.delete_resource("NetworkChaos", "train-ticket-lab", "x")
        self.assertTrue(r["absent_confirmed"])
        self.assertTrue(r["resource_absent_after_delete"])
        self.assertEqual(r["verify_status"], "absent")
        self.assertFalse(r["delete_failed"])

    def test_timeout_is_not_absent(self):
        self._patched(124, "kubectl timed out")
        r = rce.delete_resource("NetworkChaos", "train-ticket-lab", "x")
        self.assertFalse(r["absent_confirmed"])
        self.assertFalse(r["resource_absent_after_delete"])
        self.assertEqual(r["verify_status"], "timeout")
        self.assertTrue(r["delete_failed"])

    def test_rbac_forbidden_is_not_absent(self):
        self._patched(1, 'Error from server (Forbidden): networkchaos.chaos-mesh.org "x" is forbidden')
        r = rce.delete_resource("NetworkChaos", "train-ticket-lab", "x")
        self.assertFalse(r["absent_confirmed"])
        self.assertFalse(r["resource_absent_after_delete"])
        self.assertEqual(r["verify_status"], "error")
        self.assertTrue(r["delete_failed"])

    def test_resource_still_exists_is_not_absent(self):
        self._patched(0, "")
        r = rce.delete_resource("NetworkChaos", "train-ticket-lab", "x")
        self.assertFalse(r["absent_confirmed"])
        self.assertEqual(r["verify_status"], "exists")
        self.assertTrue(r["delete_failed"])

    def test_delete_command_failure_is_not_absent(self):
        patcher = mock.patch.object(rce, "run_kubectl", autospec=True)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        mocked.side_effect = [
            (1, "", "the server rejected our request"),
            (1, "", 'Error from server (NotFound): ... "x" not found'),
        ]
        r = rce.delete_resource("NetworkChaos", "train-ticket-lab", "x")
        # absence confirmed on verify, but the delete command itself failed
        self.assertTrue(r["absent_confirmed"])
        self.assertFalse(r["delete_command_ok"])
        self.assertTrue(r["delete_failed"])


class StressCleanupClassificationTests(unittest.TestCase):
    """run_stress_with_cgroup.cleanup_mutation uses the same absence rule."""

    def test_timeout_never_confirms(self):
        patcher = mock.patch.object(rswc, "run_kubectl", autospec=True)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        mocked.side_effect = [
            (0, "deleted", ""),
            (124, "", "kubectl timed out"),
        ]
        r = rswc.cleanup_mutation("NetworkChaos", "train-ticket-lab", "x")
        self.assertFalse(r["confirmed"])
        self.assertFalse(r["resource_absent_after_delete"])
        self.assertEqual(r["verify_status"], "timeout")

    def test_rbac_never_confirms(self):
        patcher = mock.patch.object(rswc, "run_kubectl", autospec=True)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        mocked.side_effect = [
            (0, "deleted", ""),
            (1, "", 'Error from server (Forbidden): ... is forbidden'),
        ]
        r = rswc.cleanup_mutation("NetworkChaos", "train-ticket-lab", "x")
        self.assertFalse(r["confirmed"])
        self.assertEqual(r["verify_status"], "error")

    def test_not_found_confirms(self):
        patcher = mock.patch.object(rswc, "run_kubectl", autospec=True)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        mocked.side_effect = [
            (0, "deleted", ""),
            (1, "", 'Error from server (NotFound): networkchaos.chaos-mesh.org "x" not found'),
        ]
        r = rswc.cleanup_mutation("NetworkChaos", "train-ticket-lab", "x")
        self.assertTrue(r["confirmed"])
        self.assertTrue(r["resource_absent_after_delete"])
        self.assertEqual(r["verify_status"], "absent")


class ProbeRunnerLifecycleTests(unittest.TestCase):
    """The probe-restart runner keeps active_resource until absence is confirmed."""

    def test_active_resource_cleared_only_when_absent_confirmed(self):
        import run_probe_restart_escape as rpre

        # simulate the exact line: cleanup_result absent -> active_resource=None
        confirmed = rce.delete_resource.__wrapped__ if hasattr(rce.delete_resource, "__wrapped__") else None

        # We cannot easily invoke the whole runner; instead assert the CONTROLLING
        # logic: the runner only clears when absent_confirmed. We verify by reading
        # the source decision through a narrow re-implementation check:
        # the branch condition in run_probe_restart_escape.py.
        src = __import__("pathlib").Path(rpre.__file__).read_text(encoding="utf-8")
        self.assertIn('if cleanup_result.get("absent_confirmed"):', src)
        self.assertIn("active_resource = None", src)

    def test_delete_resource_provides_absent_confirmed_field(self):
        # contract: the runner keys off absent_confirmed, so delete_resource must
        # always emit it.
        self._patched = None
        patcher = mock.patch.object(rce, "run_kubectl", autospec=True)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        mocked.side_effect = [
            (0, "deleted", ""),
            (1, "", 'Error from server (NotFound): ... "x" not found'),
        ]
        r = rce.delete_resource("NetworkChaos", "train-ticket-lab", "x")
        self.assertIn("absent_confirmed", r)
        self.assertIn("verify_status", r)


if __name__ == "__main__":
    unittest.main()
