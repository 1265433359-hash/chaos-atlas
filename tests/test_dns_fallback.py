import pytest

from tools.dns_network_fallback import build_dns_network_fallback


def test_dns_failure_fallback_targets_core_dns_only():
    manifest = build_dns_network_fallback(
        namespace="chaosatlas-run-test",
        selector={"app": "resource-canary"},
        dns_cluster_ip="10.96.0.10",
        fault_family="dns_failure",
        duration_s=30,
        name="dns-failure",
    )
    assert manifest["kind"] == "NetworkChaos"
    assert manifest["spec"]["action"] == "loss"
    assert manifest["spec"]["mode"] == "one"
    assert manifest["spec"]["externalTargets"] == ["10.96.0.10"]
    assert manifest["spec"]["loss"] == {"loss": "100", "correlation": "100"}
    assert manifest["spec"]["selector"]["namespaces"] == ["chaosatlas-run-test"]


def test_dns_delay_fallback_requires_bounded_latency():
    manifest = build_dns_network_fallback(
        namespace="chaosatlas-run-test",
        selector={"app": "resource-canary"},
        dns_cluster_ip="10.96.0.10",
        fault_family="dns_delay",
        duration_s=30,
        name="dns-delay",
        latency_ms=300,
    )
    assert manifest["spec"]["action"] == "delay"
    assert manifest["spec"]["delay"] == {"latency": "300ms"}

    with pytest.raises(ValueError, match="latency_ms"):
        build_dns_network_fallback(
            namespace="chaosatlas-run-test",
            selector={"app": "resource-canary"},
            dns_cluster_ip="10.96.0.10",
            fault_family="dns_delay",
            duration_s=30,
            name="dns-delay",
            latency_ms=0,
        )
