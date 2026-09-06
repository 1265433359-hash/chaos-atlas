from pathlib import Path

from scripts.run_api_server_delay_disposable import _profile, build_plan
from tools.chaosatlas_runtime_preflight import KubernetesPreflight


def test_disposable_plan_is_owned_and_tears_down_cluster(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAOSATLAS_STATE_ROOT", str(tmp_path / "state"))
    plan = build_plan(
        repo=tmp_path,
        profile="chaosatlas-api-delay-test",
        namespace="chaosatlas-run-api-delay-test",
        output=tmp_path / "state" / "runs" / "api-server-delay",
        image="chaosatlas/resource-canary:test",
    )

    commands = [item["command"] for item in plan]
    assert commands[0][:4] == ["minikube", "start", "-p", "chaosatlas-api-delay-test"]
    assert any(command[:3] == ["kubectl", "--context", "chaosatlas-api-delay-test"] for command in commands)
    run_command = next(
        command for command in commands if str(tmp_path / "state" / "runs" / "api-server-delay" / "run") in command
    )
    assert "--candidate-id" not in run_command
    assert commands[-1][:4] == ["minikube", "delete", "-p", "chaosatlas-api-delay-test"]
    assert all(str(tmp_path / "state" / "runs") in str(item["output"]) for item in plan if item.get("output"))


def test_disposable_plan_rejects_unowned_names(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAOSATLAS_STATE_ROOT", str(tmp_path / "state"))
    try:
        build_plan(
            repo=tmp_path,
            profile="minikube",
            namespace="chaosatlas-run-api-delay-test",
            output=tmp_path / "state" / "runs" / "api-server-delay",
            image="chaosatlas/resource-canary:test",
        )
    except ValueError as exc:
        assert "chaosatlas-" in str(exc)
    else:
        raise AssertionError("unowned profile must be rejected")


def test_disposable_profile_declares_sensitive_data_policy():
    profile = _profile("chaosatlas-run-api-delay-test", "chaosatlas-api-delay-test")
    assert profile["sensitive_data_policy"]["redact_fields"]


def test_api_only_profile_does_not_require_chaos_mesh_crds():
    profile = _profile("chaosatlas-run-api-delay-test", "chaosatlas-api-delay-test")

    def runner(args, timeout=30):
        parts = args[2:] if args and args[0] == "--context" else args
        if parts and parts[0] == "get":
            kind = parts[1]
            if kind in {"namespace", "deployments", "services", "pods", "events"}:
                if kind == "namespace":
                    return 0, '{"metadata": {"name": "chaosatlas-run-api-delay-test"}}', ""
                if kind == "deployments":
                    return 0, '{"items": [{"status": {"availableReplicas": 1}}]}', ""
                if kind == "pods":
                    return 0, '{"items": [{"status": {"phase": "Running"}}]}', ""
                return 0, '{"items": []}', ""
            return 1, "", 'the server doesn\'t have a resource type "' + kind + '"'
        return 1, "", "unsupported"

    result = KubernetesPreflight(profile=profile, runner=runner, kube_context="chaosatlas-api-delay-test").run()
    assert result["status"] == "ready_for_injection"
    assert result["residual_resources"]["status"] == "not_required"


def test_kubernetes_api_fault_profile_does_not_require_chaos_mesh_crds():
    profile = _profile("chaosatlas-run-api-fault-test", "chaosatlas-api-fault-test")
    profile["fault_support"] = {
        "image_pull_failure": {"status": "supported", "reason": "owned disposable target"}
    }

    def runner(args, timeout=30):
        parts = args[2:] if args and args[0] == "--context" else args
        if parts and parts[0] == "get":
            kind = parts[1]
            if kind == "namespace":
                return 0, '{"metadata": {"name": "chaosatlas-run-api-fault-test"}}', ""
            if kind == "deployments":
                return 0, '{"items": [{"status": {"availableReplicas": 1}}]}', ""
            if kind == "pods":
                return 0, '{"items": [{"status": {"phase": "Running"}}]}', ""
            if kind in {"services", "events"}:
                return 0, '{"items": []}', ""
            return 1, "", 'the server doesn\'t have a resource type "' + kind + '"'
        return 1, "", "unsupported"

    result = KubernetesPreflight(profile=profile, runner=runner, kube_context="chaosatlas-api-fault-test").run()
    assert result["status"] == "ready_for_injection"
    assert result["residual_resources"]["status"] == "not_required"
