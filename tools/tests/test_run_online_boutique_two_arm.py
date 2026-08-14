from __future__ import annotations

from tools.run_online_boutique_two_arm import (
    classify_observation,
    collect_sustained_successes,
    consecutive_successes,
    is_port_forward_failure,
    workload_passes,
)


def workload(*statuses: str) -> dict:
    return {"observations": [{"grpc_status": status} for status in statuses]}


def test_baseline_requires_every_requested_sample_to_succeed() -> None:
    assert workload_passes(workload("OK", "OK", "OK", "OK", "OK"), 5)
    assert not workload_passes(workload("OK", "OK", "UNAVAILABLE", "OK", "OK"), 5)
    assert not workload_passes(workload("OK"), 5)


def test_consecutive_successes_resets_after_failure() -> None:
    samples = [
        {"grpc_status": "OK"},
        {"grpc_status": "OK"},
        {"grpc_status": "UNAVAILABLE"},
        {"grpc_status": "OK"},
        {"grpc_status": "OK"},
        {"grpc_status": "OK"},
    ]
    assert consecutive_successes(samples) == 3


def test_observation_classification_does_not_invent_protection() -> None:
    assert classify_observation(workload("OK", "OK")) == "no_business_impact_observed"
    assert classify_observation(workload("OK", "UNAVAILABLE")) == "weakness_observed"
    assert classify_observation(workload()) == "observation_incomplete"


def test_recovery_preserves_failures_and_waits_for_consecutive_successes() -> None:
    statuses = iter(("OK", "INTERNAL", "OK", "OK", "OK"))
    clock = iter((0.0, 0.0, 1.0, 2.0, 3.0, 4.0))

    result = collect_sustained_successes(
        lambda: workload(next(statuses)),
        required=3,
        timeout=30.0,
        poll_interval=0.0,
        monotonic=lambda: next(clock),
        sleep=lambda _: None,
    )

    assert result["recovered"] is True
    assert [sample["grpc_status"] for sample in result["samples"]] == [
        "OK",
        "INTERNAL",
        "OK",
        "OK",
        "OK",
    ]
    assert result["consecutive_successes"] == 3


def test_recovery_stops_at_timeout_without_claiming_success() -> None:
    clock = iter((0.0, 0.0, 1.0, 2.0))

    result = collect_sustained_successes(
        lambda: workload("UNAVAILABLE"),
        required=2,
        timeout=2.0,
        poll_interval=0.0,
        monotonic=lambda: next(clock),
        sleep=lambda _: None,
    )

    assert result["recovered"] is False
    assert len(result["samples"]) == 2
    assert result["consecutive_successes"] == 0


def test_only_local_port_forward_failures_are_reconnect_candidates() -> None:
    assert is_port_forward_failure(
        workload("CART_ADD_FAILED"),
        "127.0.0.1:17070 connection refused",
    )
    assert is_port_forward_failure(
        workload("UNAVAILABLE"),
        "127.0.0.1:15050 connection refused",
    )
    assert not is_port_forward_failure(workload("CART_ADD_FAILED"), "cart backend rejected request")
