import pytest

from chaosatlas.isolation.blueprint import compile_blueprint, derive_l2_blueprint


LABELS = {"chaosatlas.dev/managed": "true", "chaosatlas.dev/lease-id": "lease-1"}


def test_blueprint_rejects_secret_values_host_paths_and_privileged_containers():
    with pytest.raises(ValueError, match="Secret values"):
        compile_blueprint({"resources": [{"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "x"}, "stringData": {"password": "no"}}]}, namespace="ca-l2-x", owner_labels=LABELS)
    with pytest.raises(ValueError, match="hostPath"):
        compile_blueprint({"resources": [{"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "x"}, "spec": {"template": {"spec": {"volumes": [{"hostPath": {"path": "/"}}]}}}}]}, namespace="ca-l2-x", owner_labels=LABELS)
    with pytest.raises(ValueError, match="privileged"):
        compile_blueprint({"resources": [{"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "x"}, "spec": {"template": {"spec": {"containers": [{"securityContext": {"privileged": True}}]}}}}]}, namespace="ca-l2-x", owner_labels=LABELS)


def test_blueprint_rewrites_namespace_labels_and_drops_server_metadata():
    source = {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "safe", "namespace": "source", "uid": "old"}, "data": {"mode": "synthetic"}}
    result = compile_blueprint({"resources": [source]}, namespace="ca-l2-x", owner_labels=LABELS)
    assert result[0]["metadata"]["namespace"] == "ca-l2-x"
    assert result[0]["metadata"]["labels"] == LABELS
    assert "uid" not in result[0]["metadata"]
    assert source["metadata"]["namespace"] == "source"


def test_workload_blueprint_propagates_ownership_and_rejects_source_references():
    deployment = {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "safe"}, "spec": {"selector": {"matchLabels": {"app": "safe"}}, "template": {"metadata": {"labels": {"app": "safe"}}, "spec": {"containers": [{"name": "safe", "image": "pause:3.9"}]}}}}
    result = compile_blueprint({"resources": [deployment]}, namespace="ca-l2-x", owner_labels=LABELS)[0]
    assert result["spec"]["template"]["metadata"]["labels"]["chaosatlas.dev/lease-id"] == "lease-1"
    assert result["spec"]["template"]["spec"]["automountServiceAccountToken"] is False

    deployment["spec"]["template"]["spec"]["containers"][0]["envFrom"] = [{"secretRef": {"name": "source-secret"}}]
    with pytest.raises(ValueError, match="envFrom"):
        compile_blueprint({"resources": [deployment]}, namespace="ca-l2-x", owner_labels=LABELS)


@pytest.mark.parametrize("unsafe", [
    {"volumes": [{"name": "data", "persistentVolumeClaim": {"claimName": "source"}}]},
    {"serviceAccountName": "source-service-account"},
    {"containers": [{"name": "x", "image": "x", "ports": [{"containerPort": 80, "hostPort": 8080}]}]},
])
def test_blueprint_rejects_persistent_or_host_coupled_pod_settings(unsafe):
    resource = {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "unsafe"}, "spec": {"selector": {"matchLabels": {"app": "x"}}, "template": {"metadata": {"labels": {"app": "x"}}, "spec": unsafe}}}
    with pytest.raises(ValueError, match="forbidden|must reference"):
        compile_blueprint({"resources": [resource]}, namespace="ca-l2-x", owner_labels=LABELS)


def test_blueprint_allows_only_lease_local_config_secret_and_empty_claim_references():
    resources = [
        {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "settings"}, "data": {"MODE": "synthetic"}},
        {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "credentials"}, "runtimeGenerate": {"keys": ["password"], "templates": {"database-url": "postgres://user:${password}@db/test"}}},
        {"apiVersion": "v1", "kind": "PersistentVolumeClaim", "metadata": {"name": "scratch"}, "spec": {"accessModes": ["ReadWriteOnce"], "resources": {"requests": {"storage": "64Mi"}}}},
        {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "app"}, "spec": {"selector": {"matchLabels": {"app": "x"}}, "template": {"metadata": {"labels": {"app": "x"}}, "spec": {"containers": [{"name": "app", "image": "app:1", "env": [{"name": "PASSWORD", "valueFrom": {"secretKeyRef": {"name": "credentials", "key": "password"}}}], "envFrom": [{"configMapRef": {"name": "settings"}}], "volumeMounts": [{"name": "scratch", "mountPath": "/data"}]}], "volumes": [{"name": "scratch", "persistentVolumeClaim": {"claimName": "scratch"}}]}}}},
    ]
    compiled = compile_blueprint({"resources": resources}, namespace="ca-l2-x", owner_labels=LABELS)
    assert [item["kind"] for item in compiled[:3]] == ["ConfigMap", "Secret", "PersistentVolumeClaim"]
    assert "stringData" not in compiled[1]


def test_blueprint_runtime_template_must_derive_from_a_declared_random_key():
    secret = {
        "apiVersion": "v1", "kind": "Secret", "metadata": {"name": "credentials"},
        "runtimeGenerate": {"keys": ["random"], "templates": {"password": "hardcoded"}},
    }
    with pytest.raises(ValueError, match="reference declared generated keys"):
        compile_blueprint({"resources": [secret]}, namespace="ca-l2-x", owner_labels=LABELS)
    secret["runtimeGenerate"]["templates"]["password"] = "Aa1!${unknown}"
    with pytest.raises(ValueError, match="reference declared generated keys"):
        compile_blueprint({"resources": [secret]}, namespace="ca-l2-x", owner_labels=LABELS)


def test_blueprint_rejects_guard_weakening_and_foreign_references():
    with pytest.raises(ValueError, match="unsupported blueprint kind"):
        compile_blueprint({"resources": [{"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {"name": "allow-all"}, "spec": {"podSelector": {}, "ingress": [{}]}}]}, namespace="ca-l2-x", owner_labels=LABELS)
    deployment = {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "app"}, "spec": {"selector": {"matchLabels": {"app": "x"}}, "template": {"metadata": {"labels": {"app": "x"}}, "spec": {"containers": [{"name": "app", "image": "app:1", "env": [{"name": "X", "valueFrom": {"configMapKeyRef": {"name": "foreign", "key": "x"}}}]}]}}}}
    with pytest.raises(ValueError, match="created by this lease"):
        compile_blueprint({"resources": [deployment]}, namespace="ca-l2-x", owner_labels=LABELS)


def test_l2_derivation_keeps_only_safe_container_facts_and_adds_test_volume():
    target = {"extensions": {"container_blueprints": [{"name": "web", "image": "app:1", "ports": [{"containerPort": 8080}], "resources": {"limits": {"memory": "256Mi"}}, "secret": "ignored"}]}}
    blueprint = derive_l2_blueprint(target, "fixture")
    container = blueprint["resources"][0]["spec"]["template"]["spec"]["containers"][0]
    assert container["image"] == "app:1"
    assert "secret" not in container
    assert container["volumeMounts"][0]["mountPath"] == "/chaosatlas-test"
