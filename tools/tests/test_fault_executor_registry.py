from __future__ import annotations

from tools.fault_executor_registry import get_fault_executor, list_fault_executors


def test_ready_families_have_live_executor_contracts():
    registry = list_fault_executors()
    for family in ("pod_kill", "container_kill", "stress_cpu", "stress_memory", "network_loss", "network_partition"):
        item = registry[family]
        assert item["status"] == "ready"
        assert item["executor"]
        assert item["required_evidence"]


def test_pending_families_fail_closed_before_live_execution():
    for family in ("network_delay", "backend_pod_kill", "config_reload", "replica_reduction"):
        item = get_fault_executor(family, live=True)
        assert item["status"] == "pending_method_freeze"
        assert item["can_execute"] is False
        assert item["executor"] is None


def test_unknown_family_is_method_invalid():
    item = get_fault_executor("unknown", live=True)
    assert item["status"] == "method_invalid"
    assert item["can_execute"] is False

