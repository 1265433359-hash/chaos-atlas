"""Tests for the OB prior-validation timeline reducers."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.ob_prior_validation import reduce_arm_a, reduce_arm_b, summarize_prior_validation


def _pods(*specs):
    items = []
    for uid, ip, ready in specs:
        items.append({
            "metadata": {"uid": uid},
            "status": {"podIP": ip, "conditions": [{"type": "Ready", "status": "True" if ready else "False"}]},
        })
    return {"items": items}


def _endpoints(ready_ips, not_ready_ips=()):
    return {"subsets": [
        {"addresses": [{"ip": ip} for ip in ready_ips], "notReadyAddresses": [{"ip": ip} for ip in not_ready_ips]}
    ]}


def _sample(status_code, pods, endpoints):
    ok = status_code == 200
    return {"business": {"status_code": status_code, "contract_ok": ok}, "pods": pods, "endpoints": endpoints}


class ArmATests(unittest.TestCase):
    def test_outage_proves_weakness(self):
        # pre-injection pod uid-1 killed; replacement uid-2 created but
        # business still failing -> outage co-proof (the observed OB race).
        samples = [
            _sample(500, _pods(("uid-2", "10.0.0.2", True)), _endpoints(["10.0.0.2"])),
            _sample(200, _pods(("uid-2", "10.0.0.2", True)), _endpoints(["10.0.0.2"])),
        ]
        out = reduce_arm_a(samples, {"uid-1"})
        self.assertEqual(out["classification"], "weakness_reproduced")
        self.assertEqual(out["outage_sample_count"], 1)
        self.assertEqual(out["observation_window_artifact_count"], 0)

    def test_business_failure_with_preinjection_pod_alive_is_not_outage(self):
        samples = [_sample(500, _pods(("uid-1", "10.0.0.1", True)), _endpoints(["10.0.0.1"]))]
        self.assertEqual(reduce_arm_a(samples, {"uid-1"})["classification"], "observation_inconclusive")

    def test_early_200_without_ready_endpoints_is_artifact(self):
        samples = [
            _sample(200, _pods(("uid-1", "10.0.0.1", False)), _endpoints([], ["10.0.0.1"])),
            _sample(200, _pods(("uid-2", "10.0.0.2", True)), _endpoints(["10.0.0.2"])),
        ]
        out = reduce_arm_a(samples, {"uid-1"})
        self.assertEqual(out["classification"], "observation_inconclusive")
        self.assertEqual(out["observation_window_artifact_count"], 1)

    def test_all_200_with_preinjection_pod_alive_is_inconclusive(self):
        samples = [_sample(200, _pods(("uid-1", "10.0.0.1", True)), _endpoints(["10.0.0.1"]))]
        self.assertEqual(reduce_arm_a(samples, {"uid-1"})["classification"], "observation_inconclusive")


class ArmBTests(unittest.TestCase):
    def test_surviving_uid_co_proof_defends(self):
        samples = [
            _sample(200, _pods(("killed", "10.0.0.1", False), ("alive", "10.0.0.2", True)), _endpoints(["10.0.0.2"])),
        ]
        out = reduce_arm_b(samples, killed_uid="killed")
        self.assertEqual(out["classification"], "defended")
        self.assertEqual(out["defended_sample_count"], 1)

    def test_killed_pod_ip_in_endpoints_is_not_co_proof(self):
        samples = [
            _sample(200, _pods(("killed", "10.0.0.1", True), ("alive", "10.0.0.2", False)), _endpoints(["10.0.0.1"])),
        ]
        out = reduce_arm_b(samples, killed_uid="killed")
        self.assertEqual(out["classification"], "observation_inconclusive")

    def test_business_failure_is_not_defense(self):
        samples = [
            _sample(500, _pods(("killed", "10.0.0.1", False), ("alive", "10.0.0.2", True)), _endpoints(["10.0.0.2"])),
        ]
        self.assertEqual(reduce_arm_b(samples, killed_uid="killed")["classification"], "observation_inconclusive")


class VerdictTests(unittest.TestCase):
    def test_both_arms_plus_clean_lifecycle_validates(self):
        a = {"classification": "weakness_reproduced"}
        b = {"classification": "defended"}
        out = summarize_prior_validation(arm_a=a, arm_b=b, cleanup_ok=True, restored_replicas=1, residual_chaos_count=0)
        self.assertEqual(out["verdict"], "prior_validated")

    def test_dirty_lifecycle_blocks_any_claim(self):
        out = summarize_prior_validation(
            arm_a={"classification": "weakness_reproduced"}, arm_b={"classification": "defended"},
            cleanup_ok=False, restored_replicas=1, residual_chaos_count=0)
        self.assertEqual(out["verdict"], "lifecycle_invalid")

    def test_single_arm_failure_keeps_prior_provisional(self):
        out = summarize_prior_validation(
            arm_a={"classification": "observation_inconclusive"}, arm_b={"classification": "defended"},
            cleanup_ok=True, restored_replicas=1, residual_chaos_count=0)
        self.assertEqual(out["verdict"], "not_validated")


if __name__ == "__main__":
    unittest.main()
