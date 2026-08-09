"""Round-2 finding #4 tests: PodChaos multi-replica recovery must not be
confirmed while any target replica is still down.

Requires:
  - recovery counts non-terminating Pods only (deletionTimestamp excluded)
  - with expected_pod_count set: ALL target replicas must be Ready
  - single-replica / unknown-count legacy callers keep the old "any Ready" rule

Pure unit tests: monkeypatch run_chaos_experiment.kubectl_json.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_chaos_experiment as rce


def pod(name: str, ready: bool, terminating: bool = False) -> dict:
    meta = {"name": name, "namespace": "train-ticket-lab"}
    if terminating:
        meta["deletionTimestamp"] = "2026-08-09T00:00:00Z"
    status = {"conditions": []}
    if ready:
        status["conditions"] = [{"type": "Ready", "status": "True"}]
    return {"metadata": meta, "status": status}


class WaitForTargetReadyTests(unittest.TestCase):
    SELECTOR = {"labelSelectors": {"app": "demo"}}

    def _call(self, items, expected_count=None, timeout=2.0, interval=0.1):
        with patch.object(rce, "kubectl_json", return_value=({"items": items}, None)):
            return rce.wait_for_target_ready(
                "train-ticket-lab", self.SELECTOR, timeout, interval,
                expected_pod_count=expected_count,
            )

    def test_single_ready_replica_recovers(self):
        # single-replica PodChaos: one Ready Pod -> recovered (legacy behaviour).
        ok, status, _ = self._call([pod("p0", ready=True)], expected_count=1)
        self.assertTrue(ok)
        self.assertEqual(status["expected_pod_count"], 1)

    def test_multi_replica_one_down_returns_false(self):
        # Round-2 #4: expected 2 replicas, only 1 Ready -> NOT recovered.
        ok, status, _ = self._call(
            [pod("p0", ready=True), pod("p1", ready=False)],
            expected_count=2, timeout=0.5,
        )
        self.assertFalse(ok)
        self.assertEqual(status["ready_pods"], ["p0"])

    def test_multi_replica_all_ready_recovers(self):
        ok, status, _ = self._call(
            [pod("p0", ready=True), pod("p1", ready=True)],
            expected_count=2, timeout=0.5,
        )
        self.assertTrue(ok)

    def test_terminating_pod_never_counts_toward_recovery(self):
        # A terminating replica must be excluded even if it reports Ready.
        ok, status, _ = self._call(
            [pod("p0", ready=True), pod("p1", ready=True, terminating=True)],
            expected_count=2, timeout=0.5,
        )
        self.assertFalse(ok)  # only 1 active pod < 2 expected
        self.assertEqual(status["active_pod_count"], 1)

    def test_legacy_none_count_any_ready_still_ok(self):
        # Unknown target count keeps the historical single-Ready semantics.
        ok, _, _ = self._call([pod("p0", ready=False), pod("p1", ready=True)], expected_count=None)
        self.assertTrue(ok)

    def test_recovery_target_count_recorded_in_lifecycle(self):
        # The runner must record the pre-injection target count for audit.
        src = Path(rce.__file__).read_text(encoding="utf-8")
        self.assertIn("recovery_target_pod_count", src)
        self.assertIn("expected_pod_count=", src)


if __name__ == "__main__":
    unittest.main()
