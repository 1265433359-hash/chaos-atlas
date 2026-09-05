import json

from tools.kubernetes_lifecycle_executor import KubernetesLifecycleExecutor


def test_long_action_id_uses_bounded_result_path(tmp_path):
    executor = KubernetesLifecycleExecutor(
        root=tmp_path,
        namespace="lab",
        allowed_namespaces={"lab"},
    )

    path = executor._write_result("candidate-" + "x" * 300, {"status": "blocked"})

    assert path.is_file()
    assert path.name.startswith("result-")
    assert len(str(path)) < 240


def test_network_target_pods_are_included_in_cleanup_ownership(monkeypatch, tmp_path):
    def runner(args, timeout=30, kube_context=None):
        assert args[:4] == ["get", "pods", "-n", "lab"]
        return 0, json.dumps({"items": [{"metadata": {"name": "cache-0"}}]}), ""

    monkeypatch.setattr("tools.kubernetes_lifecycle_executor.run_kubectl", runner)
    executor = KubernetesLifecycleExecutor(
        root=tmp_path,
        namespace="lab",
        allowed_namespaces={"lab"},
        kube_context="test",
    )
    names = executor._target_pod_names_for_cleanup({
        "spec": {
            "target": {
                "selector": {
                    "namespaces": ["lab"],
                    "labelSelectors": {"app": "cache"},
                },
            },
        },
    })
    assert names == {"cache-0"}


def test_top_level_selector_is_included_in_cleanup_ownership(monkeypatch, tmp_path):
    def runner(args, timeout=30, kube_context=None):
        assert args == ["get", "pods", "-n", "lab", "-l", "app=extension", "-o", "json"]
        return 0, json.dumps({"items": [{"metadata": {"name": "extension-0"}}]}), ""

    monkeypatch.setattr("tools.kubernetes_lifecycle_executor.run_kubectl", runner)
    executor = KubernetesLifecycleExecutor(
        root=tmp_path,
        namespace="lab",
        allowed_namespaces={"lab"},
        kube_context="test",
    )
    names = executor._target_pod_names_for_cleanup({
        "spec": {
            "selector": {
                "namespaces": ["lab"],
                "labelSelectors": {"app": "extension"},
            },
        },
    })
    assert names == {"extension-0"}


def test_top_level_and_nested_selectors_are_merged(monkeypatch, tmp_path):
    def runner(args, timeout=30, kube_context=None):
        label = args[5]
        name = "extension-0" if label == "app=extension" else "cache-0"
        return 0, json.dumps({"items": [{"metadata": {"name": name}}]}), ""

    monkeypatch.setattr("tools.kubernetes_lifecycle_executor.run_kubectl", runner)
    executor = KubernetesLifecycleExecutor(
        root=tmp_path,
        namespace="lab",
        allowed_namespaces={"lab"},
        kube_context="test",
    )
    names = executor._target_pod_names_for_cleanup({
        "spec": {
            "selector": {
                "namespaces": ["lab"],
                "labelSelectors": {"app": "extension"},
            },
            "target": {
                "selector": {
                    "namespaces": ["lab"],
                    "labelSelectors": {"app": "cache"},
                },
            },
        },
    })
    assert names == {"extension-0", "cache-0"}


def test_selector_from_another_namespace_is_not_queried(monkeypatch, tmp_path):
    def runner(*_args, **_kwargs):
        raise AssertionError("cross-namespace selector must not be queried")

    monkeypatch.setattr("tools.kubernetes_lifecycle_executor.run_kubectl", runner)
    executor = KubernetesLifecycleExecutor(
        root=tmp_path,
        namespace="lab",
        allowed_namespaces={"lab"},
        kube_context="test",
    )
    names = executor._target_pod_names_for_cleanup({
        "spec": {
            "selector": {
                "namespaces": ["other"],
                "labelSelectors": {"app": "extension"},
            },
        },
    })
    assert names == set()
