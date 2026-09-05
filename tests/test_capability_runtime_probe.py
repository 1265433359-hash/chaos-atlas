import json

from chaosatlas.capabilities.runtime_probe import probe_runtime_backends


def _pod(name, ready):
    return {
        "metadata": {"name": name},
        "status": {"conditions": [{"type": "Ready", "status": "True" if ready else "False"}]},
    }


def test_runtime_probe_prefers_ready_mesh_namespace_over_stale_partial_install():
    def runner(args, timeout=30):
        command = args[2:] if args[:2] == ["--context", "test"] else args
        if command[:2] == ["get", "crd"]:
            return 0, "ok", ""
        namespace = command[3]
        if namespace == "chaos-testing":
            return 0, json.dumps({"items": [_pod("chaos-controller-manager-old", False)]}), ""
        return 0, json.dumps({"items": [_pod("chaos-controller-manager-new", True), _pod("chaos-daemon-new", True)]}), ""

    result = probe_runtime_backends(runner=runner, kube_context="test")
    assert result["chaos_mesh"]["namespace"] == "chaos-mesh"
    assert result["chaos_mesh"]["ready"] is True
    assert result["read_only"] is True
    assert result["injection_performed"] is False
