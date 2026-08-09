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


def pod(name: str, ready: bool, terminating: bool = False, uid: str | None = None) -> dict:
    meta = {"name": name, "namespace": "train-ticket-lab"}
    if uid:
        meta["uid"] = uid
    if terminating:
        meta["deletionTimestamp"] = "2026-08-09T00:00:00Z"
    status = {"conditions": []}
    if ready:
        status["conditions"] = [{"type": "Ready", "status": "True"}]
    return {"metadata": meta, "status": status}


class WaitForTargetReadyTests(unittest.TestCase):
    SELECTOR = {"labelSelectors": {"app": "demo"}}

    def _call(self, items, expected_count=None, timeout=2.0, interval=0.1,
              pre_kill_uids=None, stable_checks=2):
        with patch.object(rce, "kubectl_json", return_value=({"items": items}, None)):
            return rce.wait_for_target_ready(
                "train-ticket-lab", self.SELECTOR, timeout, interval,
                expected_pod_count=expected_count,
                pre_kill_uids=pre_kill_uids,
                stable_checks=stable_checks,
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


class IdentityReplacementTests(unittest.TestCase):
    """Round-3 P2-3 + Round-4 mode=one: recovery must verify identity
    replacement. mode=one kills exactly one replica, so multi-replica recovery
    only needs ONE new UID present (old replicas may keep their UIDs)."""

    SELECTOR = {"labelSelectors": {"app": "demo"}}

    def _call(self, items_or_sequence, pre_kill_uids, expected_count=1, timeout=0.5,
              interval=0.05, stable_checks=2):
        if isinstance(items_or_sequence, list) and items_or_sequence and isinstance(
            items_or_sequence[0], list
        ):
            # sequence of (items) snapshots -> side_effect over polls
            side_effect = [({"items": items}, None) for items in items_or_sequence]
            patcher = patch.object(rce, "kubectl_json", side_effect=side_effect)
        else:
            patcher = patch.object(rce, "kubectl_json", return_value=({"items": items_or_sequence}, None))
        with patcher:
            return rce.wait_for_target_ready(
                "train-ticket-lab", self.SELECTOR, timeout, interval,
                expected_pod_count=expected_count,
                pre_kill_uids=pre_kill_uids,
                stable_checks=stable_checks,
            )

    def test_old_uid_still_ready_not_recovered(self):
        # Single-replica: the pre-injection Pod (old UID) is still Ready -> the
        # kill did NOT replace it (no new UID) -> not recovered.
        old = pod("p0", ready=True, uid="uid-old")
        ok, status, _ = self._call([old], pre_kill_uids={"uid-old"})
        self.assertFalse(ok)
        self.assertEqual(status["ready_uids"], ["uid-old"])

    def test_replacement_uid_recovers_after_stability(self):
        # Single-replica: a new UID replaces the killed one; needs stable_checks
        # consecutive Ready polls. Use TWO DIFFERENT snapshot values so the
        # stability counter genuinely observes two polls (Round-4 requirement).
        new1 = pod("p0", ready=True, uid="uid-new")
        new2 = pod("p0", ready=True, uid="uid-new")
        ok, status, _ = self._call(
            [[new1], [new2]], pre_kill_uids={"uid-old"}, stable_checks=2,
        )
        self.assertTrue(ok)
        self.assertEqual(status["ready_uids"], ["uid-new"])

    def test_no_replacement_within_timeout(self):
        # No Ready pod appears -> not recovered (identity never replaced).
        down = pod("p0", ready=False, uid="uid-new")
        ok, _, _ = self._call([down], pre_kill_uids={"uid-old"}, timeout=0.2)
        self.assertFalse(ok)

    def test_multi_replica_one_replacement_recovers(self):
        # Round-4 mode=one: pre-kill {old-1, old-2}; one killed and replaced by
        # new-1 while old-2 keeps its UID. expected_count=2 -> recovered.
        new1 = pod("p0", ready=True, uid="uid-new-1")
        old2 = pod("p1", ready=True, uid="uid-old-2")
        ok, status, _ = self._call(
            [[new1, old2], [new1, old2]],
            pre_kill_uids={"uid-old-1", "uid-old-2"},
            expected_count=2, stable_checks=2,
        )
        self.assertTrue(ok)
        self.assertEqual(status["ready_uids"], ["uid-new-1", "uid-old-2"])

    def test_multi_replica_no_replacement_fails(self):
        # pre-kill {old-1, old-2} both still Ready and no new UID -> NOT
        # recovered (no replica was replaced).
        old1 = pod("p0", ready=True, uid="uid-old-1")
        old2 = pod("p1", ready=True, uid="uid-old-2")
        ok, _, _ = self._call(
            [old1, old2], pre_kill_uids={"uid-old-1", "uid-old-2"},
            expected_count=2, timeout=0.2,
        )
        self.assertFalse(ok)

    def test_multi_replica_extra_active_replica_fails(self):
        # old-1, old-2, new-1 all present and Ready -> active count (3) exceeds
        # expected (2): a replacement happened before the killed pod finished
        # terminating -> NOT a clean recovery.
        old1 = pod("p0", ready=True, uid="uid-old-1")
        old2 = pod("p1", ready=True, uid="uid-old-2")
        new1 = pod("p2", ready=True, uid="uid-new-1")
        ok, status, _ = self._call(
            [old1, old2, new1], pre_kill_uids={"uid-old-1", "uid-old-2"},
            expected_count=2, timeout=0.2,
        )
        self.assertFalse(ok)
        self.assertEqual(status["active_pod_count"], 3)

    def test_recovery_pre_kill_uids_recorded(self):
        src = Path(rce.__file__).read_text(encoding="utf-8")
        self.assertIn("recovery_pre_kill_uids", src)
        self.assertIn("pre_kill_uids=", src)


if __name__ == "__main__":
    unittest.main()
