import json

from chaosatlas.isolation.manager import IsolationManager
from chaosatlas.isolation.lease_store import LeaseStore
from chaosatlas.isolation.planner import IsolationPlanner
from chaosatlas.isolation.providers import KubernetesIsolationProvider, MinikubeIsolationProvider, ProviderRegistry


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
            self.objects[(kind.lower(), namespace, name)] = value
            return 0, "applied", ""
        if command[0] == "get" and command[1] == "namespace":
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

    def runner(args, timeout=60, input_text=None):
        calls.append(args)
        command = args[2:] if args[:2] == ["--context", "test"] else args
        if command[:2] == ["get", "namespace"]:
            return 0, json.dumps(namespace), ""
        if command[:3] == ["get", "pods", "-n"]:
            return 0, json.dumps(pods), ""
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
    provider = MinikubeIsolationProvider(root=tmp_path / "runtime", runner=runner, cache_seed_root=tmp_path / "empty-cache")
    manager = IsolationManager(store=LeaseStore(tmp_path / "store"), providers=ProviderRegistry([provider]))
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
