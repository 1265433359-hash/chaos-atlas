from __future__ import annotations

from tools.availability_oracle import (
    availability_ratio,
    business_probe_stability,
    classify_recovery,
    max_zero_streak,
    recovery_deadline,
    replacement_identity,
)


def test_ce_metrics_handle_deployment_samples_and_api_failures_as_zero():
    samples = [{"availableReplicas": 1}, {"availableReplicas": 0}, {"availableReplicas": 0}, {"api_error": "timeout"}]
    assert availability_ratio(samples, 1) == 0.25
    assert max_zero_streak(samples) == 3


def test_recovery_requires_new_identity_ready_business_and_cleanup():
    before = [{"uid": "old"}]
    after = [{"uid": "new", "ready": True, "business_probe": True, "elapsed_s": 12}]
    assert replacement_identity(before, after)
    assert recovery_deadline(after, 30) == 12
    assert business_probe_stability(after, 1)
    assert classify_recovery(before, after, stable_probe_samples=after, cleanup_confirmed=True, deadline_s=30) == "recovered"


def test_running_or_probe_restart_is_not_recovery():
    before = [{"uid": "old"}]
    after = [{"uid": "new", "phase": "Running", "ready": False, "business_probe": False, "elapsed_s": 5}]
    assert not classify_recovery(before, after, stable_probe_samples=after, cleanup_confirmed=True, deadline_s=30) == "recovered"
    assert classify_recovery(before, after, stable_probe_samples=after, cleanup_confirmed=False, deadline_s=30) == "cleanup_incomplete"
