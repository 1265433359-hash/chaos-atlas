from tools.isolated_environment import NamespaceLease
from tools.isolated_environment import DisposableNamespaceManager


def test_high_risk_fault_requires_disposable_environment():
    lease = NamespaceLease.for_fault("api_server_delay", project="online-boutique", seed=1)
    assert lease.disposable is True
    assert lease.namespace.startswith("chaosatlas-run-")


def test_cleanup_record_requires_owner_and_empty_confirmation():
    lease = NamespaceLease.for_fault("dns_failure", project="online-boutique", seed=2)
    result = lease.cleanup_record(resources=[], owner="chaosatlas")
    assert result["status"] == "verified"
    assert result["owner"] == "chaosatlas"


def test_disposable_namespace_manager_creates_and_destroys_owned_namespace():
    calls = []
    namespace = "chaosatlas-run-abc123"

    def runner(args, timeout=30, kube_context=None):
        calls.append(args)
        if args[:2] == ["create", "namespace"]:
            return 0, namespace, ""
        if args[:2] == ["label", "namespace"]:
            return 0, "labeled", ""
        if args[:2] == ["delete", "namespace"]:
            return 0, "deleted", ""
        if args[:2] == ["get", "namespace"]:
            return 1, "", "Error from server (NotFound): namespaces not found"
        raise AssertionError(args)

    manager = DisposableNamespaceManager(
        project="nginx-kubernetes-ingress",
        fault_family="disk_pressure",
        seed=11,
        runner=runner,
    )

    prepared = manager.prepare()
    destroyed = manager.destroy()

    assert prepared["status"] == "created"
    assert prepared["namespace"] == manager.lease.namespace
    assert destroyed["status"] == "verified"
    assert any(call[:2] == ["create", "namespace"] for call in calls)
    assert any(call[:2] == ["delete", "namespace"] for call in calls)


def test_disposable_namespace_manager_rejects_non_disposable_fault():
    manager = DisposableNamespaceManager(
        project="nginx-kubernetes-ingress",
        fault_family="network_delay",
        seed=11,
        runner=lambda args, timeout=30, kube_context=None: (0, "", ""),
    )

    result = manager.prepare()

    assert result["status"] == "environment_blocked"
    assert "disposable" in result["reason"]
