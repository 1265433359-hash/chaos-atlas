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


def _ready_runner():
    def runner(args, timeout=30):
        command = args[2:] if args[:2] == ["--context", "test"] else args
        if command[:2] == ["get", "crd"]:
            return 0, "ok", ""
        namespace = command[3]
        if namespace != "chaos-mesh":
            return 1, "", "missing"
        return 0, json.dumps({"items": [_pod("chaos-controller-manager", True), _pod("chaos-daemon", True)]}), ""
    return runner


def test_runtime_probe_requires_valid_external_httpchaos_effect_evidence(tmp_path):
    payload = {
        "schema_version": "chaosatlas-httpchaos-runtime-evidence-v1",
        "kube_context": "test",
        "canaries": [{"attestation": {"valid": True}, "effect": {"confirmed": True}}],
    }
    (tmp_path / "httpchaos-runtime-evidence.json").write_text(json.dumps(payload), encoding="utf-8")
    result = probe_runtime_backends(runner=_ready_runner(), kube_context="test", evidence_root=tmp_path)
    assert result["httpchaos_runtime_verified"] is True
    assert result["httpchaos_runtime_evidence"]["valid_canary_count"] == 1


def test_runtime_probe_rejects_context_mismatch(tmp_path):
    payload = {
        "schema_version": "chaosatlas-httpchaos-runtime-evidence-v1",
        "kube_context": "other",
        "canaries": [{"attestation": {"valid": True}, "effect": {"confirmed": True}}],
    }
    (tmp_path / "httpchaos-runtime-evidence.json").write_text(json.dumps(payload), encoding="utf-8")
    result = probe_runtime_backends(runner=_ready_runner(), kube_context="test", evidence_root=tmp_path)
    assert result["httpchaos_runtime_verified"] is False
