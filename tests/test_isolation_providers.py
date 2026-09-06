import json
import re

import pytest

from chaosatlas.isolation.manager import IsolationManager
from chaosatlas.isolation.lease_store import LeaseStore
from chaosatlas.isolation.planner import IsolationPlanner
from chaosatlas.isolation.providers import KubernetesIsolationProvider, MinikubeIsolationProvider, ProviderRegistry, _job_terminal_failure


def test_kubernetes_guard_allows_only_same_namespace_pods_and_dns_ports():
    resources = KubernetesIsolationProvider._guard_resources(
        "ca-l2-test", {"chaosatlas.dev/managed": "true"}, {},
    )
    policy = next(item for item in resources if item["kind"] == "NetworkPolicy")
    lease_peer = {"podSelector": {"matchLabels": {"chaosatlas-managed": "true"}}}
    assert policy["spec"]["ingress"] == [{"from": [lease_peer]}]
    assert policy["spec"]["egress"][0] == {"to": [lease_peer]}
    assert policy["spec"]["egress"][1] == {
        "ports": [
            {"protocol": "UDP", "port": 53},
            {"protocol": "TCP", "port": 53},
        ],
    }


def test_kubernetes_job_terminal_failure_is_detected_without_waiting_for_timeout():
    assert _job_terminal_failure(
        {"backoffLimit": 2},
        {"failed": 3, "conditions": [{"type": "Failed", "status": "True"}]},
    ) is True
    assert _job_terminal_failure({"backoffLimit": 2}, {"failed": 1}) is False


class FakeKubernetes:
    def __init__(self):
        self.objects = {}
        self.calls = []

    def __call__(self, args, timeout=60, input_text=None):
        self.calls.append(list(args))
        command = args[2:] if args[:2] == ["--context", "test"] else args
        if command[:3] == ["apply", "-f", "-"]:
            value = json.loads(input_text)
            metadata = value.get("metadata") or {}
            namespace = metadata.get("namespace")
            name = metadata.get("name")
            kind = value.get("kind")
            value.setdefault("metadata", {})["uid"] = f"uid-{kind}-{name}"
            if kind in {"Deployment", "StatefulSet"}:
                value["metadata"]["generation"] = 1
                value["status"] = {"observedGeneration": 1, "readyReplicas": 1, "availableReplicas": 1, "currentReplicas": 1, "updatedReplicas": 1}
            self.objects[(kind.lower(), namespace, name)] = value
            return 0, "applied", ""
        if command[0] == "get" and command[1] == "namespace":
            if command[2] == "kube-system":
                return 0, json.dumps({"metadata": {"name": "kube-system", "uid": "cluster-uid"}}), ""
            value = self.objects.get(("namespace", None, command[2]))
            return (0, json.dumps(value), "") if value else (1, "", "NotFound")
        if command[:3] == ["get", "pods", "-n"]:
            namespace = command[3]
            has_workload = any(key[1] == namespace and key[0] in {"deployment", "statefulset"} for key in self.objects)
            items = [{"metadata": {"uid": "pod-sandbox"}, "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}]}}] if has_workload else []
            return 0, json.dumps({"items": items}), ""
        if command[0] == "get":
            namespace = command[command.index("-n") + 1]
            value = self.objects.get((command[1], namespace, command[2]))
            return (0, json.dumps(value), "") if value else (1, "", "NotFound")
        if command[:2] == ["delete", "namespace"]:
            namespace = command[2]
            self.objects = {key: value for key, value in self.objects.items() if key[1] != namespace and not (key[0] == "namespace" and key[2] == namespace)}
            return 0, "deleted", ""
        raise AssertionError(command)


def test_adopted_l1_release_never_deletes_namespace(tmp_path):
    calls = []
    namespace = {"metadata": {"name": "fixture-lab", "uid": "source-uid"}}
    pods = {"items": [{"metadata": {"uid": "pod-uid"}, "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}]}}]}
    workload = {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "app", "generation": 1}, "spec": {"replicas": 1}, "status": {"observedGeneration": 1, "readyReplicas": 1, "availableReplicas": 1, "updatedReplicas": 1}}

    def runner(args, timeout=60, input_text=None):
        calls.append(args)
        command = args[2:] if args[:2] == ["--context", "test"] else args
        if command[:2] == ["get", "namespace"]:
            return 0, json.dumps(namespace), ""
        if command[:3] == ["get", "pods", "-n"]:
            return 0, json.dumps(pods), ""
        if command[:3] == ["get", "deployments,statefulsets", "-n"]:
            return 0, json.dumps({"items": [workload]}), ""
        if command[:2] == ["get", "deployment"]:
            return 0, json.dumps(workload), ""
        raise AssertionError(command)

    profile = {"project_id": "fixture", "project_commit": "r", "namespace_policy": {"allowed_namespaces": ["fixture-lab"]}, "runtime_contract": {"kube_context": "test"}, "isolation": {"l1": {"mode": "adopted-test-replica", "dedicated_test_replica": True}, "synthetic_data_only": True}}
    capability = {"fault_id": "pod_kill", "target_id": "n1", "required_isolation": "L1", "capability_status": "canary_required"}
    plan = IsolationPlanner().plan(profile=profile, capability=capability)
    provider = KubernetesIsolationProvider(name="kubernetes-l1", level="L1", runner=runner)
    manager = IsolationManager(store=LeaseStore(tmp_path), providers=ProviderRegistry([provider]))
    lease = manager.prepare(plan)
    released = manager.release(lease["lease_id"])
    assert released["state"] == "released"
    assert not any("delete" in call for call in calls)


def test_minikube_provider_uses_only_exact_generated_profile(tmp_path):
    calls = []
    existing = set()

    def runner(args, timeout=900, env=None):
        calls.append(args)
        if args[:3] == ["profile", "list", "--output"]:
            return 0, json.dumps({"valid": [{"Name": item} for item in existing]}), ""
        profile = args[args.index("--profile") + 1]
        if args[0] == "start":
            existing.add(profile)
            return 0, "started", ""
        if args[0] == "status":
            return (0, '{"Host":"Running","Kubelet":"Running","APIServer":"Running"}', "") if profile in existing else (7, "", "not found")
        if args[0] == "delete":
            existing.discard(profile)
            return 0, "deleted", ""
        raise AssertionError(args)

    profile = {"project_id": "fixture", "project_commit": "r", "isolation": {"l3": {"mode": "ephemeral-cluster", "resource_budget": {"cpu": 2, "memory": "2048mb", "disk": "5g"}}, "synthetic_data_only": True}}
    capability = {"fault_id": "api_server_delay", "target_id": None, "required_isolation": "L3", "capability_status": "blocked"}
    plan = IsolationPlanner().plan(profile=profile, capability=capability)
    def docker_runner(args, timeout=60, input_text=None, env=None):
        profile_name = args[args.index("--filter") + 1].split("=", 1)[1]
        return 0, ("container-id\n" if profile_name in existing else ""), ""

    provider = MinikubeIsolationProvider(root=tmp_path / "runtime", runner=runner, docker_runner=docker_runner, cache_seed_root=tmp_path / "empty-cache")
    manager = IsolationManager(store=LeaseStore(tmp_path / "store", coordination_root=tmp_path / "coordination"), providers=ProviderRegistry([provider]))
    lease = manager.prepare(plan)
    assert lease["state"] == "ready"
    assert lease["target_name"].startswith("ca-l3-fixture-")
    assert manager.release(lease["lease_id"])["state"] == "released"
    assert all("minikube" not in call and "chaosatlas-apps" not in call for call in calls)


def test_l2_creates_owned_sandbox_and_proves_zero_residue(tmp_path):
    runner = FakeKubernetes()
    profile = {
        "project_id": "fixture",
        "project_commit": "r",
        "runtime_contract": {"kube_context": "test"},
        "isolation": {"synthetic_data_only": True, "l2": {"mode": "ephemeral-target", "blueprint": {"resources": [{
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "sandbox"},
            "spec": {"replicas": 1, "selector": {"matchLabels": {"app": "sandbox"}}, "template": {"metadata": {"labels": {"app": "sandbox"}}, "spec": {"containers": [{"name": "sandbox", "image": "pause:3.9"}]}}},
        }]}}},
    }
    capability = {"fault_id": "disk_pressure", "target_id": "n1", "required_isolation": "L2", "capability_status": "blocked"}
    plan = IsolationPlanner().plan(profile=profile, capability=capability, target={"node_id": "n1"})
    provider = KubernetesIsolationProvider(name="kubernetes-l2", level="L2", runner=runner)
    manager = IsolationManager(store=LeaseStore(tmp_path), providers=ProviderRegistry([provider]))
    lease = manager.prepare(plan)
    assert lease["state"] == "ready"
    namespace = lease["target_name"]
    namespace_object = runner.objects[("namespace", None, namespace)]
    assert namespace_object["metadata"]["labels"]["chaosatlas.dev/lease-id"] == lease["lease_id"]
    assert manager.release(lease["lease_id"])["state"] == "released"
    assert not runner.objects
    delete_calls = [call for call in runner.calls if "delete" in call]
    assert len(delete_calls) == 1 and namespace in delete_calls[0]


def test_runtime_generated_secrets_are_portable_hex_and_templates_use_them(tmp_path):
    runner = FakeKubernetes()
    profile = {
        "project_id": "fixture",
        "project_commit": "r",
        "runtime_contract": {"kube_context": "test"},
        "isolation": {"synthetic_data_only": True, "l2": {"mode": "ephemeral-target", "blueprint": {"resources": [
            {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "runtime"}, "runtimeGenerate": {"keys": ["password"], "templates": {"uri": "scheme://user:${password}@service/db"}}},
            {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "sandbox"}, "spec": {"replicas": 1, "selector": {"matchLabels": {"app": "sandbox"}}, "template": {"metadata": {"labels": {"app": "sandbox"}}, "spec": {"containers": [{"name": "sandbox", "image": "pause:3.9"}]}}}},
        ]}}},
    }
    capability = {"fault_id": "secret_rotation", "target_id": "n1", "required_isolation": "L2", "capability_status": "canary_required"}
    plan = IsolationPlanner().plan(profile=profile, capability=capability)
    manager = IsolationManager(store=LeaseStore(tmp_path), providers=ProviderRegistry([KubernetesIsolationProvider(name="kubernetes-l2", level="L2", runner=runner)]))

    lease = manager.prepare(plan)
    secret = runner.objects[("secret", lease["target_name"], "runtime")]["stringData"]

    assert re.fullmatch(r"[0-9a-f]{64}", secret["password"])
    assert secret["uri"] == f"scheme://user:{secret['password']}@service/db"
    assert manager.release(lease["lease_id"])["state"] == "released"


def test_l2_refuses_cleanup_when_namespace_uid_changes(tmp_path):
    runner = FakeKubernetes()
    profile = {"project_id": "fixture", "project_commit": "r", "runtime_contract": {"kube_context": "test"}, "isolation": {"synthetic_data_only": True, "l2": {"mode": "ephemeral-target", "blueprint": {"resources": [{"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "sandbox"}, "spec": {"selector": {"matchLabels": {"app": "sandbox"}}, "template": {"metadata": {"labels": {"app": "sandbox"}}, "spec": {"containers": [{"name": "sandbox", "image": "pause:3.9"}]}}}}]}}}}
    plan = IsolationPlanner().plan(profile=profile, capability={"fault_id": "disk_pressure", "target_id": "n1", "required_isolation": "L2", "capability_status": "blocked"}, target={"node_id": "n1"})
    manager = IsolationManager(store=LeaseStore(tmp_path), providers=ProviderRegistry([KubernetesIsolationProvider(name="kubernetes-l2", level="L2", runner=runner)]))
    lease = manager.prepare(plan)
    runner.objects[("namespace", None, lease["target_name"])]["metadata"]["uid"] = "foreign-uid"
    assert manager.release(lease["lease_id"])["state"] == "cleanup_failed"
    assert not any("delete" in call for call in runner.calls)


def test_ephemeral_l1_uses_same_owned_lifecycle_and_leaves_zero_residue(tmp_path):
    runner = FakeKubernetes()
    workload = {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "app-clone"}, "spec": {"selector": {"matchLabels": {"app": "clone"}}, "template": {"metadata": {"labels": {"app": "clone"}}, "spec": {"containers": [{"name": "clone", "image": "registry.k8s.io/pause:3.9"}]}}}}
    profile = {"project_id": "fixture", "project_commit": "r", "runtime_contract": {"kube_context": "test"}, "isolation": {"synthetic_data_only": True, "l1": {"mode": "ephemeral-app-clone", "blueprint": {"resources": [workload]}}}}
    plan = IsolationPlanner().plan(profile=profile, capability={"fault_id": "pod_kill", "target_id": "n1", "required_isolation": "L1", "capability_status": "canary_required"})
    manager = IsolationManager(store=LeaseStore(tmp_path), providers=ProviderRegistry([KubernetesIsolationProvider(name="kubernetes-l1", level="L1", runner=runner)]))
    lease = manager.prepare(plan)
    assert lease["state"] == "ready"
    assert lease["target_name"].startswith("ca-l1-fixture-")
    assert manager.release(lease["lease_id"])["state"] == "released"
    assert not runner.objects


def _ready_lease(*, cluster_uid="cluster-uid"):
    return {
        "target_name": "ca-l2-fixture-abc",
        "runtime_locator": {"provider": "kubernetes-l2", "kube_context": "test", "cluster_uid": cluster_uid},
        "resources": [{"kind": "Deployment", "namespace": "ca-l2-fixture-abc", "name": "app", "actual_uid": "uid-app"}],
    }


def test_ready_rejects_one_ready_and_one_pending_pod():
    def runner(args, timeout=60, input_text=None):
        command = args[2:] if args[:2] == ["--context", "test"] else args
        if command[:2] == ["get", "namespace"]:
            uid = "cluster-uid" if command[2] == "kube-system" else "namespace-uid"
            return 0, json.dumps({"metadata": {"uid": uid}}), ""
        if command[:3] == ["get", "pods", "-n"]:
            return 0, json.dumps({"items": [
                {"metadata": {}, "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}]}},
                {"metadata": {}, "status": {"phase": "Pending", "conditions": []}},
            ]}), ""
        if command[:2] == ["get", "deployment"]:
            return 0, json.dumps({"metadata": {"generation": 1}, "spec": {"replicas": 1}, "status": {"observedGeneration": 1, "readyReplicas": 1, "availableReplicas": 1, "updatedReplicas": 1}}), ""
        raise AssertionError(command)

    provider = KubernetesIsolationProvider(name="kubernetes-l2", level="L2", runner=runner)
    result = provider.verify_ready({"kube_context": "test", "ready_timeout_s": 1}, _ready_lease())
    assert result["status"] == "blocked"
    assert result["checks"]["pod_count"] == 2
    assert result["checks"]["all_pods_ready"] is False


def test_ready_rejects_incomplete_rollout_even_when_pod_is_ready():
    def runner(args, timeout=60, input_text=None):
        command = args[2:] if args[:2] == ["--context", "test"] else args
        if command[:2] == ["get", "namespace"]:
            uid = "cluster-uid" if command[2] == "kube-system" else "namespace-uid"
            return 0, json.dumps({"metadata": {"uid": uid}}), ""
        if command[:3] == ["get", "pods", "-n"]:
            return 0, json.dumps({"items": [{"metadata": {}, "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}]}}]}), ""
        if command[:2] == ["get", "deployment"]:
            return 0, json.dumps({"metadata": {"generation": 2}, "spec": {"replicas": 2}, "status": {"observedGeneration": 1, "readyReplicas": 1, "availableReplicas": 1, "updatedReplicas": 1}}), ""
        raise AssertionError(command)

    result = KubernetesIsolationProvider(name="kubernetes-l2", level="L2", runner=runner).verify_ready({"kube_context": "test", "ready_timeout_s": 1}, _ready_lease())
    assert result["status"] == "blocked"
    assert result["checks"]["all_workloads_ready"] is False


def test_ready_rejects_deleted_registered_guard_even_when_workloads_are_ready():
    lease = _ready_lease()
    lease["owner_labels"] = {
        "chaosatlas.dev/managed": "true",
        "chaosatlas.dev/lease-id": "lease-test",
    }
    lease["resources"].append({
        "kind": "NetworkPolicy", "namespace": lease["target_name"],
        "name": "chaosatlas-boundary", "actual_uid": "uid-policy",
    })

    def runner(args, timeout=60, input_text=None):
        command = args[2:] if args[:2] == ["--context", "test"] else args
        if command[:3] == ["get", "namespace", "kube-system"]:
            return 0, json.dumps({"metadata": {"uid": "cluster-uid"}}), ""
        if command[:2] == ["get", "namespace"]:
            return 0, json.dumps({"metadata": {
                "uid": "namespace-uid", "labels": lease["owner_labels"],
            }}), ""
        if command[:3] == ["get", "pods", "-n"]:
            return 0, json.dumps({"items": [{
                "metadata": {}, "status": {"phase": "Running", "conditions": [
                    {"type": "Ready", "status": "True"},
                ]},
            }]}), ""
        if command[:2] == ["get", "deployment"]:
            return 0, json.dumps({
                "metadata": {"uid": "uid-app", "generation": 1, "labels": lease["owner_labels"]},
                "spec": {"replicas": 1},
                "status": {"observedGeneration": 1, "readyReplicas": 1,
                           "availableReplicas": 1, "updatedReplicas": 1},
            }), ""
        if command[:2] == ["get", "networkpolicy"]:
            return 1, "", "Error from server (NotFound)"
        raise AssertionError(command)

    result = KubernetesIsolationProvider(
        name="kubernetes-l2", level="L2", runner=runner,
    ).verify_ready({"kube_context": "test", "ready_timeout_s": 1}, lease)
    assert result["status"] == "blocked"
    assert result["checks"]["all_pods_ready"] is True
    assert result["checks"]["all_workloads_ready"] is True
    assert result["checks"]["all_registered_resources_ready"] is False
    assert result["errors"] == [
        "NetworkPolicy/chaosatlas-boundary missing or changed after registration",
    ]


def test_cleanup_can_recover_namespace_created_before_uid_was_recorded():
    lease = _ready_lease()
    lease.update({"lease_id": "lease-abc", "owner_labels": {"chaosatlas.dev/managed": "true", "chaosatlas.dev/lease-id": "lease-abc"}})
    lease["resources"] = [{"kind": "Namespace", "namespace": None, "name": lease["target_name"], "actual_uid": None}]
    deleted = []

    def runner(args, timeout=60, input_text=None):
        command = args[2:] if args[:2] == ["--context", "test"] else args
        if command[:3] == ["get", "namespace", "kube-system"]:
            return 0, json.dumps({"metadata": {"uid": "cluster-uid"}}), ""
        if command[:2] == ["get", "namespace"]:
            return 0, json.dumps({"metadata": {"uid": "created-uid", "labels": lease["owner_labels"]}}), ""
        if command[:2] == ["delete", "namespace"]:
            deleted.append(command[2])
            return 0, "deleted", ""
        raise AssertionError(command)

    result = KubernetesIsolationProvider(name="kubernetes-l2", level="L2", runner=runner).cleanup({"kube_context": "test"}, lease)
    assert result["status"] == "released"
    assert deleted == [lease["target_name"]]


def test_cleanup_blocks_when_pinned_cluster_identity_changes():
    lease = _ready_lease(cluster_uid="original")
    lease.update({"lease_id": "lease-abc", "owner_labels": {"chaosatlas.dev/managed": "true", "chaosatlas.dev/lease-id": "lease-abc"}})
    lease["resources"] = [{"kind": "Namespace", "namespace": None, "name": lease["target_name"], "actual_uid": "uid"}]

    def runner(args, timeout=60, input_text=None):
        return 0, json.dumps({"metadata": {"uid": "different"}}), ""

    result = KubernetesIsolationProvider(name="kubernetes-l2", level="L2", runner=runner).cleanup({"kube_context": "test"}, lease)
    assert result == {"status": "blocked", "reason": "cluster_identity_mismatch"}


def test_kubernetes_absence_confirmation_waits_for_slow_namespace_deletion(monkeypatch):
    lease = _ready_lease(cluster_uid="cluster-uid")
    calls = 0

    def runner(args, timeout=60, input_text=None):
        nonlocal calls
        command = args[2:] if args[:2] == ["--context", "test"] else args
        if command[:3] == ["get", "namespace", "kube-system"]:
            return 0, json.dumps({"metadata": {"uid": "cluster-uid"}}), ""
        if command[:2] == ["get", "namespace"]:
            calls += 1
            if calls < 4:
                return 0, json.dumps({"metadata": {"uid": "namespace-uid"}}), ""
            return 1, "", "Error from server (NotFound): namespaces not found"
        raise AssertionError(command)

    monkeypatch.setattr("chaosatlas.isolation.providers.time.sleep", lambda _seconds: None)
    result = KubernetesIsolationProvider(name="kubernetes-l2", level="L2", runner=runner).verify_absent(
        {"kube_context": "test", "cleanup_timeout_s": 90},
        lease,
    )

    assert result["confirmed"] is True
    assert calls == 4


def test_minikube_unknown_profile_inventory_fails_closed(tmp_path):
    def runner(args, timeout=900, env=None):
        return 124, "", "minikube command unavailable"

    provider = MinikubeIsolationProvider(root=tmp_path / "wrong", runner=runner, docker_runner=lambda *args, **kwargs: (0, "", ""), cache_seed_root=tmp_path / "empty")
    lease = {
        "lease_id": "lease-abc",
        "target_name": "ca-l3-fixture-abc",
        "runtime_locator": {"provider": "minikube-l3", "runtime_root": str(tmp_path / "pinned"), "driver": "docker"},
        "external_profiles": [{"provider": "minikube", "name": "ca-l3-fixture-abc"}],
        "resources": [],
    }
    cleanup = provider.cleanup({}, lease)
    absence = provider.verify_absent({}, lease)
    assert cleanup["status"] == "blocked"
    assert "presence_unknown" in cleanup["reason"]
    assert absence["confirmed"] is False
    assert "unknown" in absence["errors"][0]
    assert str(provider._paths(lease)[0]).startswith(str((tmp_path / "pinned").resolve()))


def test_minikube_rejects_unapproved_cni_before_start(tmp_path):
    calls = []

    def runner(args, timeout=900, env=None):
        calls.append(args)
        return 0, "", ""

    provider = MinikubeIsolationProvider(root=tmp_path / "runtime", runner=runner, docker_runner=lambda *args, **kwargs: (0, "", ""), cache_seed_root=tmp_path / "empty")
    lease = {"lease_id": "lease-abc", "target_name": "ca-l3-fixture-abc", "runtime_locator": {"provider": "minikube-l3", "runtime_root": str(tmp_path / "runtime"), "driver": "docker"}, "external_profiles": [], "resources": []}
    with pytest.raises(RuntimeError, match="unsupported.*CNI"):
        provider.prepare({"blueprint": {"driver": "docker", "container_runtime": "containerd", "cni": "unsafe-plugin"}, "resource_budget": {}}, lease, lambda action, payload: None)
    assert not any(call and call[0] == "start" for call in calls)


def test_minikube_passes_allowlisted_credential_free_runtime_proxy(tmp_path):
    calls = []

    def runner(args, timeout=900, env=None):
        calls.append(args)
        return 0, "", ""

    provider = MinikubeIsolationProvider(root=tmp_path / "runtime", runner=runner, docker_runner=lambda *args, **kwargs: (0, "", ""), cache_seed_root=tmp_path / "empty")
    lease = {"lease_id": "lease-abc", "target_name": "ca-l3-fixture-abc", "runtime_locator": {"provider": "minikube-l3", "runtime_root": str(tmp_path / "runtime"), "driver": "docker"}, "external_profiles": [], "resources": []}
    provider.prepare({"blueprint": {
        "driver": "docker",
        "container_runtime": "docker",
        "runtime_proxy": {
            "HTTP_PROXY": "http://host.docker.internal:7897",
            "HTTPS_PROXY": "http://host.docker.internal:7897",
            "NO_PROXY": "127.0.0.1,localhost,.svc,.cluster.local",
        },
    }, "resource_budget": {}}, lease, lambda action, payload: None)

    start = next(call for call in calls if call[0] == "start")
    values = [start[index + 1] for index, value in enumerate(start[:-1]) if value == "--docker-env"]
    assert values == [
        "HTTPS_PROXY=http://host.docker.internal:7897",
        "HTTP_PROXY=http://host.docker.internal:7897",
        "NO_PROXY=127.0.0.1,localhost,.svc,.cluster.local",
    ]


def test_minikube_rejects_proxy_credentials_before_start(tmp_path):
    calls = []

    def runner(args, timeout=900, env=None):
        calls.append(args)
        return 0, "", ""

    provider = MinikubeIsolationProvider(root=tmp_path / "runtime", runner=runner, docker_runner=lambda *args, **kwargs: (0, "", ""), cache_seed_root=tmp_path / "empty")
    lease = {"lease_id": "lease-abc", "target_name": "ca-l3-fixture-abc", "runtime_locator": {"provider": "minikube-l3", "runtime_root": str(tmp_path / "runtime"), "driver": "docker"}, "external_profiles": [], "resources": []}
    with pytest.raises(RuntimeError, match="credentials"):
        provider.prepare({"blueprint": {"driver": "docker", "container_runtime": "docker", "runtime_proxy": {"HTTPS_PROXY": "http://user:password@host.docker.internal:7897"}}, "resource_budget": {}}, lease, lambda action, payload: None)
    assert not any(call and call[0] == "start" for call in calls)
