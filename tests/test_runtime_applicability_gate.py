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


def test_httpchaos_daemon_probe_uses_discovered_namespace(monkeypatch):
    calls = []

    def fake_run_kubectl(args, timeout=30, kube_context=None):
        calls.append((args, kube_context))
        if args[0] == "logs":
            return 0, "", ""
        return 0, "HTTPCHAOS_CAPABILITY_OK", ""

    monkeypatch.setattr(gate, "run_kubectl", fake_run_kubectl)

    result = gate.daemon_prerequisite(
        "HTTPChaos",
        ["chaos-daemon-0"],
        namespace="chaos-mesh",
        kube_context="lab",
    )

    assert result["status"] == "pass"
    assert calls[0][0][2] == "chaos-mesh"
    assert calls[1][0][2] == "chaos-mesh"
