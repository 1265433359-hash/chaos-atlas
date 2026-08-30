from tools.fault_capability_registry import capability_for


def test_kubernetes_api_fault_is_exposed_with_executor():
    capability = capability_for("config_reload")

    assert capability.status == "implemented"
    assert callable(capability.executor)


def test_unknown_fault_fails_closed():
    try:
        capability_for("not-a-real-fault")
    except KeyError as exc:
        assert "not-a-real-fault" in str(exc)
    else:
        raise AssertionError("unknown fault must fail closed")


def test_next_http_faults_are_registered_with_http_executor():
    for fault_id in ("http_response_corrupt", "dependency_error", "connection_reset"):
        capability = capability_for(fault_id)
        assert capability.status == "implemented"
        assert capability.backend == "HTTPChaos"
        assert callable(capability.executor)


def test_native_http_faults_are_registered_with_guarded_executor():
    for fault_id in ("http_rate_limit", "business_dependency_unreachable"):
        capability = capability_for(fault_id)
        assert capability.status == "implemented"
        assert capability.backend == "NativeExecutor"
        assert callable(capability.executor)


def test_remaining_faults_are_registered_with_guarded_executors():
    for fault_id in (
        "dns_failure", "dns_delay", "env_misconfiguration", "secret_rotation",
        "rollout_pause", "image_pull_failure", "pod_unschedulable", "api_server_delay",
    ):
        capability = capability_for(fault_id)
        assert capability.status == "implemented"
        assert callable(capability.executor)
