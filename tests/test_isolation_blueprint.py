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
    with pytest.raises(ValueError, match="forbidden"):
        compile_blueprint({"resources": [resource]}, namespace="ca-l2-x", owner_labels=LABELS)


def test_l2_derivation_keeps_only_safe_container_facts_and_adds_test_volume():
    target = {"extensions": {"container_blueprints": [{"name": "web", "image": "app:1", "ports": [{"containerPort": 8080}], "resources": {"limits": {"memory": "256Mi"}}, "secret": "ignored"}]}}
    blueprint = derive_l2_blueprint(target, "fixture")
    container = blueprint["resources"][0]["spec"]["template"]["spec"]["containers"][0]
    assert container["image"] == "app:1"
    assert "secret" not in container
    assert container["volumeMounts"][0]["mountPath"] == "/chaosatlas-test"
