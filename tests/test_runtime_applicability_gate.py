from __future__ import annotations

from tools import runtime_applicability_gate as gate


def _ready_pod(name: str) -> dict:
    return {
        "metadata": {"name": name, "labels": {}},
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }


def test_chaos_components_accepts_standard_chaos_mesh_namespace(monkeypatch):
    calls = []

    def fake_kubectl_json(args, kube_context=None):
        calls.append((args, kube_context))
        if args[-1] == "chaos-testing":
            return {}, "namespace not found"
        return {
            "items": [
                _ready_pod("chaos-controller-manager-0"),
                _ready_pod("chaos-daemon-0"),
            ]
        }, None

    monkeypatch.setattr(gate, "kubectl_json", fake_kubectl_json)

    components, errors = gate.chaos_components(kube_context="lab")

    assert errors == []
    assert components["ready"] is True
    assert components["namespace"] == "chaos-mesh"
    assert calls == [
        (["get", "pods", "-n", "chaos-testing"], "lab"),
        (["get", "pods", "-n", "chaos-mesh"], "lab"),
    ]
