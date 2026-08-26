from __future__ import annotations

import json
import shutil
from http.client import BadStatusLine
from pathlib import Path
import subprocess

import pytest

import tools.kubernetes_lifecycle_executor as lifecycle_module
from tools.kubernetes_lifecycle_executor import KubernetesLifecycleExecutor
from tools.compile_scenario_node import compile_scenario
from tools.deployment_capability import build_deployment_node, build_scenario_node
from tools.run_deployment_scenario import run_scenario
from tools.tests.test_deployment_capability import deployment as deployment_document


def mutation() -> dict:
    return {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "PodChaos",
        "metadata": {"name": "ca-front-end-kill", "namespace": "sock-shop-lab"},
        "spec": {
            "action": "pod-kill",
            "mode": "one",
            "selector": {
                "namespaces": ["sock-shop-lab"],
                "labelSelectors": {"name": "front-end"},
            },
        },
    }


def container_mutation() -> dict:
    value = mutation()
    value["metadata"]["name"] = "ca-front-end-container-kill"
    value["spec"]["action"] = "container-kill"
    value["spec"]["containerNames"] = ["server"]
    return value


def hooks(*, applied: bool = True) -> dict:
    return {
        "gate": lambda manifest, path: {
            "decision": "ready_for_injection",
            "kind": manifest["kind"],
            "namespace": manifest["metadata"]["namespace"],
            "name": manifest["metadata"]["name"],
            "selector": manifest["spec"].get("selector") or {
                "namespaces": manifest["spec"].get("namespaces", []),
                "labelSelectors": manifest["spec"].get("labelSelectors", {}),
            },
            "checks": {"target_pods": [{"uid": "old-uid"}]},
        },
        "probe": lambda phase, manifest: {
            "status": "pass",
            "samples": [{"status_code": 200, "latency_ms": 12.0}],
        },
        "apply": lambda manifest: {
            "return_code": 0 if applied else 1,
            "stdout": "created" if applied else "",
            "stderr": "" if applied else "apply failed",
            "uid": "chaos-uid",
        },
        "wait_lifecycle": lambda kind, namespace, name, predicate: (
            True,
            {"injected_count": 1, "all_recovered": predicate == "recovered"},
            [],
        ),
        "wait_target_ready": lambda namespace, selector, expected, pre_uids: (
            True,
            {"ready_uids": ["new-uid"], "pre_kill_uids": sorted(pre_uids or set())},
            [],
        ),
        "delete": lambda kind, namespace, name: {
            "absent_confirmed": True,
            "resource_absent_after_delete": True,
            "delete_failed": False,
        },
    }


def test_live_executor_completes_attested_lifecycle(tmp_path: Path) -> None:
    executor = KubernetesLifecycleExecutor(
        root=tmp_path,
        namespace="sock-shop-lab",
        allowed_namespaces={"sock-shop-lab"},
        allow_live=True,
        hooks=hooks(),
    )

    result = executor.run(mutation(), action_id="A-FRONT-END-PODKILL-001")

    assert result["status"] == "executed"
    assert result["lifecycle"] == ["preflight", "baseline", "inject", "observe", "recover", "cleanup"]
    assert result["injection_confirmed"] is True
    assert result["recovery_confirmed"] is True
    assert result["cleanup_confirmed"] is True
    assert result["attestation"]["comparison_eligible"] is True
    assert (tmp_path / "runtime" / "A-FRONT-END-PODKILL-001.json").is_file()


def test_container_kill_uses_restart_recovery_hook(tmp_path: Path) -> None:
    configured = hooks()
    configured["gate"] = lambda manifest, path: {
        "decision": "ready_for_injection",
        "kind": manifest["kind"],
        "namespace": manifest["metadata"]["namespace"],
        "name": manifest["metadata"]["name"],
        "selector": manifest["spec"]["selector"],
        "checks": {"target_pods": [{"name": "front-end", "uid": "old-uid", "restarts": 0}]},
    }
    configured["wait_target_ready"] = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("container-kill must not require a replacement Pod UID")
    )
    configured["wait_container_ready"] = lambda *args, **kwargs: (
        True,
        {"recovery_mode": "container_restart", "restarted_pods": ["front-end"]},
        [],
    )
    executor = KubernetesLifecycleExecutor(
        root=tmp_path,
        namespace="sock-shop-lab",
        allowed_namespaces={"sock-shop-lab"},
        allow_live=True,
        hooks=configured,
    )

    result = executor.run(container_mutation(), action_id="A-FRONT-END-CONTAINER-001")

    assert result["status"] == "executed"
    assert result["recovery"]["state"]["recovery_mode"] == "container_restart"
    assert result["attestation"]["comparison_eligible"] is True


def test_executor_requires_explicit_live_gate_without_mutation(tmp_path: Path) -> None:
    executor = KubernetesLifecycleExecutor(
        root=tmp_path,
        namespace="sock-shop-lab",
        allowed_namespaces={"sock-shop-lab"},
        allow_live=False,
        hooks=hooks(),
    )

    result = executor.run(mutation(), action_id="A-BLOCKED-001")

    assert result["status"] == "environment_blocked"
    assert "live approval" in result["errors"][0]
    assert not (tmp_path / "runtime" / "A-BLOCKED-001.json").exists()


def test_executor_rejects_cross_namespace_manifest_before_hooks(tmp_path: Path) -> None:
    value = mutation()
    value["metadata"]["namespace"] = "default"
    executor = KubernetesLifecycleExecutor(
        root=tmp_path,
        namespace="sock-shop-lab",
        allowed_namespaces={"sock-shop-lab"},
        allow_live=True,
        hooks=hooks(),
    )

    result = executor.run(value, action_id="A-SCOPE-001")

    assert result["status"] == "environment_blocked"
    assert any("namespace" in item for item in result["errors"])


def test_executor_refuses_to_overwrite_append_only_result(tmp_path: Path) -> None:
    executor = KubernetesLifecycleExecutor(
        root=tmp_path,
        namespace="sock-shop-lab",
        allowed_namespaces={"sock-shop-lab"},
        allow_live=True,
        hooks=hooks(),
    )
    executor.run(mutation(), action_id="A-IMMUTABLE-001")

    with pytest.raises(FileExistsError):
        executor.run(mutation(), action_id="A-IMMUTABLE-001")


def test_executor_resolves_root_before_external_process_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    parent = tmp_path.parent
    monkeypatch.chdir(parent)
    relative_root = Path(tmp_path.name)
    executor = KubernetesLifecycleExecutor(
        root=relative_root,
        namespace="sock-shop-lab",
        allowed_namespaces={"sock-shop-lab"},
        allow_live=True,
        hooks=hooks(),
    )

    monkeypatch.chdir(parent.parent)
    path = executor._mutation_path("A-RELATIVE-ROOT-001", mutation())

    assert path.is_absolute()
    assert path == tmp_path / "runtime" / "mutations" / "A-RELATIVE-ROOT-001.yaml"
    assert path.is_file()


def test_executor_shortens_mutation_filename_when_windows_path_is_long(tmp_path: Path) -> None:
    long_root = Path(".pytest-tmp-long-mutation-root") / ("root-" + "x" * 125)
    try:
        long_root.mkdir(parents=True)
        executor = KubernetesLifecycleExecutor(
            root=long_root,
            namespace="sock-shop-lab",
            allowed_namespaces={"sock-shop-lab"},
            allow_live=True,
            hooks=hooks(),
        )

        path = executor._mutation_path("atlas-live-network-partition-live-verify-0-928fe5c5d40a", mutation())

        assert path.is_file()
        assert path.name.startswith("m-")
        assert len(str(path)) < 260
    finally:
        shutil.rmtree(long_root.parent, ignore_errors=True)


def test_business_unreachable_is_observed_but_not_comparison_eligible(tmp_path: Path) -> None:
    configured = hooks()
    configured["probe"] = lambda phase, manifest: (
        {"status": "pass", "samples": [{"status_code": 200}]}
        if phase == "baseline"
        else {
            "status": "business_unreachable",
            "reason": "no running service endpoint",
            "samples": [],
        }
    )
    executor = KubernetesLifecycleExecutor(
        root=tmp_path,
        namespace="sock-shop-lab",
        allowed_namespaces={"sock-shop-lab"},
        allow_live=True,
        hooks=configured,
    )

    result = executor.run(mutation(), action_id="A-UNREACHABLE-001")

    assert result["status"] == "executed"
    assert result["outcome_status"] == "business_unreachable"
    assert result["attestation"]["observation"] is True
    assert result["attestation"]["comparison_eligible"] is False
    assert result["attestation"]["valid"] is False


def test_degraded_observation_is_comparison_eligible_with_recovery(tmp_path: Path) -> None:
    configured = hooks()
    configured["probe"] = lambda phase, manifest: (
        {"status": "pass", "samples": [{"status_code": 200}]}
        if phase == "baseline"
        else {
            "status": "degraded",
            "samples": [
                {"status_code": None, "observation_status": "business_unreachable"},
                {"status_code": 200},
            ],
            "reason": "transient outage recovered",
        }
    )
    executor = KubernetesLifecycleExecutor(
        root=tmp_path,
        namespace="sock-shop-lab",
        allowed_namespaces={"sock-shop-lab"},
        allow_live=True,
        hooks=configured,
    )

    result = executor.run(mutation(), action_id="A-DEGRADED-001")

    assert result["outcome_status"] == "degraded"
    assert result["attestation"]["comparison_eligible"] is True
    assert result["attestation"]["valid"] is True


def test_default_probe_preserves_port_forward_failure_sample(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class ExitedProcess:
        def poll(self):
            return 1

    monkeypatch.setattr(lifecycle_module, "start_port_forward", lambda *args: ExitedProcess())
    monkeypatch.setattr(
        lifecycle_module,
        "wait_for_port",
        lambda *args: (_ for _ in ()).throw(RuntimeError("port-forward exited with code 1: pod is Pending")),
    )
    monkeypatch.setattr(lifecycle_module, "stop_process", lambda process: None)
    executor = KubernetesLifecycleExecutor(
        root=tmp_path,
        namespace="sock-shop-lab",
        allowed_namespaces={"sock-shop-lab"},
        allow_live=True,
        oracle={"service": "front-end", "remote_port": 80},
    )

    result = executor._default_probe("observe", mutation())

    assert result["status"] == "business_unreachable"
    assert len(result["samples"]) == 1
    assert result["samples"][0]["observation_status"] == "business_unreachable"
    assert result["samples"][0]["error"] == "port-forward exited with code 1: pod is Pending"


def test_default_probe_marks_transient_observation_failure_as_degraded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class RunningProcess:
        def poll(self):
            return None

    processes = iter([RunningProcess(), RunningProcess()])
    wait_results = iter([
        RuntimeError("port-forward exited with code 1: pod is Pending"),
        None,
    ])
    monkeypatch.setattr(lifecycle_module, "start_port_forward", lambda *args: next(processes))

    def wait_for_port_once(*args):
        outcome = next(wait_results)
        if isinstance(outcome, Exception):
            raise outcome

    monkeypatch.setattr(lifecycle_module, "wait_for_port", wait_for_port_once)
    monkeypatch.setattr(lifecycle_module, "stop_process", lambda process: None)
    monkeypatch.setattr(
        lifecycle_module,
        "http_request",
        lambda *args: {"status_code": 200, "latency_ms": 12.0, "body": "ok", "error": None},
    )
    executor = KubernetesLifecycleExecutor(
        root=tmp_path,
        namespace="sock-shop-lab",
        allowed_namespaces={"sock-shop-lab"},
        allow_live=True,
        oracle={
            "service": "front-end",
            "remote_port": 80,
            "count": 2,
            "observation_window_s": 1,
            "probe_retry_interval_s": 0,
        },
    )

    result = executor._default_probe("observe", mutation())

    assert result["status"] == "degraded"
    assert len(result["samples"]) == 3
    assert result["samples"][0]["observation_status"] == "business_unreachable"
    assert [sample["status_code"] for sample in result["samples"][1:]] == [200, 200]


def test_default_probe_retries_transient_http_protocol_failure_during_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class RunningProcess:
        def poll(self):
            return None

    processes = iter([RunningProcess(), RunningProcess()])
    monkeypatch.setattr(lifecycle_module, "start_port_forward", lambda *args, **kwargs: next(processes))
    monkeypatch.setattr(lifecycle_module, "wait_for_port", lambda *args: None)
    monkeypatch.setattr(lifecycle_module, "stop_process", lambda process: None)
    responses = iter([
        BadStatusLine("binary protocol preface"),
        {"status_code": 200, "latency_ms": 12.0, "body": "ok", "error": None},
    ])

    def request(*args):
        value = next(responses)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(lifecycle_module, "http_request", request)
    executor = KubernetesLifecycleExecutor(
        root=tmp_path,
        namespace="sock-shop-lab",
        allowed_namespaces={"sock-shop-lab"},
        allow_live=True,
        oracle={
            "service": "front-end",
            "remote_port": 80,
            "count": 1,
            "baseline_retry_window_s": 1,
            "probe_retry_interval_s": 0,
        },
    )

    result = executor._default_probe("baseline", mutation())

    assert result["status"] == "degraded"
    assert result["samples"][0]["observation_status"] == "business_unreachable"
    assert result["samples"][1]["status_code"] == 200


def test_http_oracle_sends_headers_and_requires_expected_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class RunningProcess:
        def poll(self):
            return None

    captured: list[tuple[tuple[object, ...], dict[str, object]]] = []
    monkeypatch.setattr(lifecycle_module, "start_port_forward", lambda *args, **kwargs: RunningProcess())
    monkeypatch.setattr(lifecycle_module, "wait_for_port", lambda *args: None)
    monkeypatch.setattr(lifecycle_module, "stop_process", lambda process: None)

    def request(*args, **kwargs):
        captured.append((args, kwargs))
        return {"status_code": 200, "latency_ms": 12.0, "body": "unexpected backend", "error": None}

    monkeypatch.setattr(lifecycle_module, "http_request", request)
    executor = KubernetesLifecycleExecutor(
        root=tmp_path,
        namespace="chaosatlas-nginx-ingress",
        allowed_namespaces={"chaosatlas-nginx-ingress"},
        allow_live=True,
        oracle={
            "service": "nginx-ingress",
            "remote_port": 80,
            "count": 1,
            "baseline_retry_window_s": 0,
            "request_headers": {"Host": "nginx-fixture.local"},
            "expected_body": "chaosatlas-nginx-ingress-fixture",
        },
    )

    result = executor._default_probe("baseline", mutation())

    assert result["status"] == "business_unreachable"
    assert captured[0][1]["headers"] == {"Host": "nginx-fixture.local"}


def test_grpc_probe_runs_place_order_contract_with_supporting_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class RunningProcess:
        def poll(self):
            return None

    forwards: list[tuple[str, int, int]] = []

    def start_forward(namespace, service, local_port, remote_port, **kwargs):
        forwards.append((service, local_port, remote_port))
        return RunningProcess()

    monkeypatch.setattr(lifecycle_module, "start_port_forward", start_forward)
    monkeypatch.setattr(lifecycle_module, "wait_for_port", lambda *args: None)
    monkeypatch.setattr(lifecycle_module, "stop_process", lambda process: None)
    monkeypatch.setattr(
        lifecycle_module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="[0] ok oid=order-1 tracking=track-1 (3.1ms)\n[1] ok oid=order-2 tracking=track-2 (3.4ms)\n",
            stderr="",
        ),
    )
    executor = KubernetesLifecycleExecutor(
        root=tmp_path,
        namespace="chaosatlas-otel",
        allowed_namespaces={"chaosatlas-otel"},
        allow_live=True,
        oracle={
            "kind": "grpc",
            "service": "checkout",
            "remote_port": 5050,
            "supporting_services": [{"service": "cart", "remote_port": 7070}],
            "client": "artifacts/opentelemetry-demo/otel_client.py",
            "count": 2,
            "timeout_s": 12,
        },
    )

    result = executor._default_probe("baseline", mutation())

    assert result["status"] == "pass"
    assert result["oracle_kind"] == "grpc"
    assert result["successes"] == 2
    assert forwards == [("checkout", 18090, 5050), ("cart", 18091, 7070)]


def test_apply_failure_is_persisted_as_append_only_result(tmp_path: Path) -> None:
    executor = KubernetesLifecycleExecutor(
        root=tmp_path,
        namespace="sock-shop-lab",
        allowed_namespaces={"sock-shop-lab"},
        allow_live=True,
        hooks=hooks(applied=False),
    )

    result = executor.run(mutation(), action_id="A-APPLY-FAILED-001")

    assert result["status"] == "apply_failed"
    path = tmp_path / "runtime" / "A-APPLY-FAILED-001.json"
    assert path.is_file()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["outcome_status"] == "apply_failed"


def test_executor_is_accepted_by_scenario_runner(tmp_path: Path) -> None:
    node = build_deployment_node(
        project_id="p",
        project_commit="a" * 40,
        namespace="sock-shop-lab",
        deployment=deployment_document(),
        service=None,
        source_refs=["manifest.yaml"],
        manifest_sha256="b" * 64,
    )
    scenario = build_scenario_node(
        scenario_id="sock-shop-executor-integration",
        deployment_nodes=[node],
        phases=[{
            "phase_id": "kill",
            "mode": "ordered",
            "faults": [{"kind": "pod_kill", "action": "pod-kill", "selector": {"name": "front-end"}, "parameters": {"mode": "one"}, "target_node_id": node["node_id"]}],
            "duration_s": 30,
            "target_node_ids": [node["node_id"]],
            "inject_confirmation": "status.injectedCount >= 1",
            "cleanup_owner": "phase",
        }],
        oracle={"ce_steady_state": {"metric": "deployment.availableReplicas", "minimum_available": 1}},
        recovery={"deadline_s": 120, "stable_samples": 3},
        cleanup={"required": True},
    )
    compiled = compile_scenario(scenario)
    executor = KubernetesLifecycleExecutor(
        root=tmp_path,
        namespace="sock-shop-lab",
        allowed_namespaces={"sock-shop-lab"},
        allow_live=True,
        hooks=hooks(),
    )
    result = run_scenario(
        scenario,
        compiled=compiled,
        dry_run=False,
        executor=executor,
    )

    assert result["status"] == "executed"
    assert result["phases"][0]["faults"][0]["injection_confirmed"] is True
    assert result["phases"][0]["faults"][0]["cleanup_confirmed"] is True
