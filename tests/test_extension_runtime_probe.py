import json

from tools.extension_runtime_probe import probe_extension_environment


def _runner(resources):
    def runner(args, timeout=30):
        if args[:3] == ["--context", "test", "get"]:
            command = args[3:]
        else:
            command = args
        if command[:2] == ["crd", "iochaos.chaos-mesh.org"] or command[:2] == ["crd", "timechaos.chaos-mesh.org"] or command[:2] == ["crd", "jvmchaos.chaos-mesh.org"]:
            return 0, "ok\n", ""
        if command[:4] == ["pods", "-n", "chaos-testing", "-o"]:
            return 0, json.dumps({"items": [{"status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}]}}]}), ""
        if command[:4] == ["deployments", "-n", "dify-k8s-lab", "-o"]:
            return 0, json.dumps({"items": resources}), ""
        return 1, "", "not found"
    return runner


def _profile():
    return {"project_id": "dify-kubernetes", "namespace_policy": {"allowed_namespaces": ["dify-k8s-lab"]}}


def test_probe_blocks_io_and_time_without_disposable_test_target_and_marks_jvm_inapplicable():
    deployment = {"metadata": {"name": "api"}, "spec": {"template": {"spec": {"containers": [{"image": "langgenius/dify-api:1.17.0"}]}}}}
    result = probe_extension_environment(_profile(), runner=_runner([deployment]), kube_context="test")
    statuses = {item["extension_id"]: item["status"] for item in result["extensions"]}
    assert statuses["extension.io_delay"] == "blocked"
    assert statuses["extension.io_error"] == "blocked"
    assert statuses["extension.time_offset"] == "blocked"
    assert statuses["extension.jvm_gc_pause"] == "inapplicable"
    assert statuses["extension.queue_backlog"] == "blocked"
    assert statuses["extension.connection_pool_exhaustion"] == "blocked"
    assert statuses["extension.runtime_pause"] == "blocked"
    assert result["read_only"] is True
    assert result["injection_performed"] is False


def test_probe_recognizes_declared_disposable_target_and_java_image():
    profile = {**_profile(), "extension_runtime": {"io_test_paths": ["/tmp/chaosatlas-test"], "disposable_target": True}}
    deployment = {"metadata": {"name": "java"}, "spec": {"template": {"spec": {"containers": [{"image": "eclipse-temurin:21"}]}}}}
    result = probe_extension_environment(profile, runner=_runner([deployment]), kube_context="test")
    statuses = {item["extension_id"]: item["status"] for item in result["extensions"]}
    assert statuses == {"extension.io_delay": "supported", "extension.io_error": "supported", "extension.time_offset": "supported", "extension.jvm_gc_pause": "supported", "extension.queue_backlog": "blocked", "extension.connection_pool_exhaustion": "blocked", "extension.runtime_pause": "blocked"}


def test_probe_projects_extension_agents_from_a_labeled_disposable_workload():
    profile = {
        **_profile(),
        "extension_runtime": {
            "disposable_targets": [{
                "id": "test-target",
                "selector": {"chaosatlas.dev/disposable": "true"},
                "capabilities": {"iochaos": True, "timechaos": True, "queue_agent": True, "connection_pool_agent": True, "pause_agent": True},
                "io_test_paths": ["/data"],
            }],
        },
    }
    deployment = {"metadata": {"name": "extension-target", "labels": {"chaosatlas.dev/disposable": "true"}}, "spec": {"template": {"spec": {"containers": [{"image": "chaosatlas/extension-python:20260903"}]}}}}
    result = probe_extension_environment(profile, runner=_runner([deployment]), kube_context="test")
    statuses = {item["extension_id"]: item["status"] for item in result["extensions"]}
    assert statuses["extension.io_delay"] == "supported"
    assert statuses["extension.time_offset"] == "supported"
    assert statuses["extension.queue_backlog"] == "supported"
    assert statuses["extension.connection_pool_exhaustion"] == "supported"
    assert statuses["extension.runtime_pause"] == "supported"


def test_probe_falls_back_to_chaos_mesh_namespace():
    deployment = {"metadata": {"name": "api"}, "spec": {"template": {"spec": {"containers": [{"image": "app:1"}]}}}}

    def runner(args, timeout=30):
        command = args[3:] if args[:3] == ["--context", "test", "get"] else args
        if command[0] == "crd":
            return 0, "ok", ""
        if command[:4] == ["pods", "-n", "chaos-testing", "-o"]:
            return 1, "", "not found"
        if command[:4] == ["pods", "-n", "chaos-mesh", "-o"]:
            return 0, json.dumps({"items": [{"status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}]}}]}), ""
        if command[:4] == ["deployments", "-n", "dify-k8s-lab", "-o"]:
            return 0, json.dumps({"items": [deployment]}), ""
        return 1, "", "not found"

    result = probe_extension_environment(_profile(), runner=runner, kube_context="test")
    assert result["cluster"]["chaos_mesh_namespace"] == "chaos-mesh"
    assert result["cluster"]["chaos_mesh_ready"] is True
