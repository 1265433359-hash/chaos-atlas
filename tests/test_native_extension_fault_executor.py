import json

from tools.native_extension_fault_executor import NativeExtensionFaultExecutor, build_native_extension_mutation


def _manifest(family, parameters):
    return {
        "apiVersion": "chaosatlas.dev/v1alpha1",
        "kind": "ChaosAtlasNativeExtension",
        "metadata": {"name": "extension-test", "namespace": "lab"},
        "spec": {"faultFamily": family, "targetSelector": {"app": "web"}, "parameters": parameters},
    }


def test_native_extension_mutation_validates_bounded_parameters():
    mutation = build_native_extension_mutation("extension.queue_backlog", {"queue_name": "test-queue", "depth": 100, "duration_s": 10})
    assert mutation["control"] == {"mode": "queue_backlog", "queue_name": "test-queue", "depth": 100, "duration_s": 10}
    try:
        build_native_extension_mutation("extension.connection_pool_exhaustion", {"pool_name": "test", "connections": 0, "duration_s": 10})
    except ValueError as exc:
        assert "connections" in str(exc)
    else:
        raise AssertionError("zero connections must fail closed")
    try:
        build_native_extension_mutation("extension.queue_backlog", {"queue_name": "test", "depth": 1, "duration_s": 0})
    except ValueError as exc:
        assert "duration_s" in str(exc)
    else:
        raise AssertionError("invalid duration must fail closed")
    pause = build_native_extension_mutation("extension.runtime_pause", {"target_process": "python", "pause_ms": 100, "duration_s": 10})
    assert pause["control"]["mode"] == "runtime_pause"


def test_native_extension_executor_attests_queue_lifecycle():
    pod = {"metadata": {"name": "web-abc"}, "status": {"phase": "Running"}}
    calls = []

    def runner(args, timeout=30):
        calls.append(args)
        if args[:4] == ["get", "pods", "-n", "lab"]:
            return 0, json.dumps({"items": [pod]}), ""
        if args[0] == "exec":
            return 0, "", ""
        raise AssertionError(args)

    phases = iter((
        {"status": "pass", "samples": [{"depth": 0}]},
        {"status": "degraded", "samples": [{"depth": 100}]},
        {"status": "pass", "samples": [{"depth": 0}]},
    ))
    executor = NativeExtensionFaultExecutor(
        namespace="lab",
        allowed_namespaces={"lab"},
        allow_live=True,
        isolated=True,
        runner=runner,
        probe=lambda _phase: next(phases),
        capability_probe=lambda pod_name, family: {"status": "ready", "pod": pod_name, "family": family},
    )
    result = executor(_manifest("extension.queue_backlog", {"queue_name": "test-queue", "depth": 100, "duration_s": 10}))
    assert result["status"] == "executed"
    assert result["observation"]["status"] == "degraded"
    assert result["recovery_confirmed"] is True
    assert result["cleanup_confirmed"] is True
    assert result["attestation"]["valid"] is True
    assert any(args[0] == "exec" for args in calls)


def test_native_extension_executor_requires_isolated_live_approval():
    result = NativeExtensionFaultExecutor(namespace="lab", allowed_namespaces={"lab"}, allow_live=False)(_manifest("extension.connection_pool_exhaustion", {"pool_name": "test-pool", "connections": 20, "duration_s": 10}))
    assert result["status"] == "environment_blocked"
    assert "isolated" in result["errors"][0]
