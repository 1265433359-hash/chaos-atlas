from __future__ import annotations

from tools.p02_execution_gate import chaos_components, component_namespace


def pod(name: str, namespace: str) -> dict:
    return {"metadata": {"name": name, "namespace": namespace}}


def test_detects_nondefault_chaos_mesh_namespace() -> None:
    items = [
        pod("chaos-controller-manager-abc", "chaos-testing"),
        pod("chaos-daemon-xyz", "chaos-testing"),
        pod("chaos-dashboard-123", "chaos-testing"),
        pod("application", "default"),
    ]
    assert component_namespace(items) == "chaos-testing"
    assert [item["metadata"]["name"] for item in chaos_components(items)] == [
        "chaos-controller-manager-abc",
        "chaos-daemon-xyz",
    ]


def test_detection_fails_closed_without_both_required_components() -> None:
    assert component_namespace([pod("chaos-controller-manager-abc", "chaos-testing")]) is None


def test_detection_fails_closed_when_multiple_installations_match() -> None:
    items = [
        pod("chaos-controller-manager-a", "chaos-a"),
        pod("chaos-daemon-a", "chaos-a"),
        pod("chaos-controller-manager-b", "chaos-b"),
        pod("chaos-daemon-b", "chaos-b"),
    ]
    assert component_namespace(items) is None
