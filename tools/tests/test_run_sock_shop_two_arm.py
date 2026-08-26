from pathlib import Path

import pytest
import yaml

import tools.run_sock_shop_two_arm as runner
from tools.run_sock_shop_two_arm import (
    STEPS,
    NAMESPACE,
    classify_observation,
    contract_ok,
    resolve_api_key,
    oracle_passes,
    schedule_child_names,
    validate_mutation,
)


def test_oracle_requires_all_three_frozen_business_steps() -> None:
    samples = [
        {"step": "front-end", "status_code": 200, "contract_ok": True},
        {"step": "catalogue", "status_code": 200, "contract_ok": True},
        {"step": "login", "status_code": 200, "contract_ok": True},
        {"step": "orders", "status_code": 201, "contract_ok": True},
    ]
    assert oracle_passes(samples) is True
    samples[-1]["contract_ok"] = False
    assert oracle_passes(samples) is False


def test_mutation_validation_is_exactly_namespace_local_and_targets_sock_shop_apps() -> None:
    document = {
        "kind": "PodChaos",
        "metadata": {"namespace": NAMESPACE},
        "spec": {
            "action": "pod-kill",
            "mode": "one",
            "selector": {"namespaces": [NAMESPACE], "labelSelectors": {"name": "front-end"}},
        },
    }
    assert validate_mutation(document)["status"] == "passed"
    document["spec"]["selector"]["namespaces"] = ["sock-shop"]
    assert validate_mutation(document)["status"] == "blocked"


def test_mutation_validation_accepts_every_frozen_sock_shop_deployment() -> None:
    targets = {
        "carts", "carts-db", "catalogue", "catalogue-db", "front-end", "orders", "orders-db",
        "payment", "queue-master", "rabbitmq", "session-db", "shipping", "user", "user-db",
    }
    for target in targets:
        document = {
            "kind": "StressChaos",
            "metadata": {"namespace": NAMESPACE},
            "spec": {
                "mode": "one",
                "selector": {"namespaces": [NAMESPACE], "labelSelectors": {"name": target}},
                "stressors": {"cpu": {"workers": 1, "load": 50}},
            },
        }
        assert validate_mutation(document)["status"] == "passed", target


def test_mutation_validation_accepts_http_and_schedule_categories() -> None:
    http_document = {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "HTTPChaos",
        "metadata": {"name": "http-fault", "namespace": NAMESPACE},
        "spec": {
            "mode": "one",
            "target": "Response",
            "abort": True,
            "selector": {"namespaces": [NAMESPACE], "labelSelectors": {"name": "front-end"}},
        },
    }
    schedule_document = {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "Schedule",
        "metadata": {"name": "scheduled-fault", "namespace": NAMESPACE},
        "spec": {
            "type": "PodChaos",
            "schedule": "@every 1s",
            "podChaos": {
                "action": "pod-kill",
                "mode": "one",
                "selector": {"namespaces": [NAMESPACE], "labelSelectors": {"name": "payment"}},
            },
        },
    }

    assert validate_mutation(http_document)["status"] == "passed"
    assert validate_mutation(schedule_document)["status"] == "passed"


def test_schedule_children_are_selected_by_owner_uid() -> None:
    schedule = {"metadata": {"uid": "schedule-uid", "name": "scheduled-fault"}}
    children = [
        {
            "metadata": {
                "name": "scheduled-fault-abc",
                "ownerReferences": [{"kind": "Schedule", "uid": "schedule-uid"}],
            }
        },
        {
            "metadata": {
                "name": "unrelated-podchaos",
                "ownerReferences": [{"kind": "Schedule", "uid": "other-uid"}],
            }
        },
    ]
    assert schedule_child_names(schedule, children) == ["scheduled-fault-abc"]


def test_schedule_is_deleted_before_target_and_business_recovery(tmp_path: Path, monkeypatch) -> None:
    mutation = tmp_path / "scheduled-pod-kill.yaml"
    mutation.write_text(
        yaml.safe_dump(
            {
                "apiVersion": "chaos-mesh.org/v1alpha1",
                "kind": "Schedule",
                "metadata": {"name": "scheduled-kill", "namespace": NAMESPACE},
                "spec": {
                    "type": "PodChaos",
                    "schedule": "@every 30s",
                    "podChaos": {
                        "action": "pod-kill",
                        "mode": "one",
                        "selector": {
                            "namespaces": [NAMESPACE],
                            "labelSelectors": {"name": "catalogue-db"},
                        },
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    calls: list[str] = []
    monkeypatch.setattr(
        runner,
        "check_mutation",
        lambda _path: {
            "decision": "ready_for_injection",
            "kind": "Schedule",
            "name": "scheduled-kill",
            "checks": {"target_pods": [{"uid": "catalogue-db-before"}]},
        },
    )
    monkeypatch.setattr(runner, "start_port_forward", lambda *_args: object())
    monkeypatch.setattr(runner, "wait_for_port", lambda *_args: None)
    monkeypatch.setattr(runner, "stop_process", lambda _process: {"stopped_by_runner": True})
    monkeypatch.setattr(runner, "run_kubectl", lambda *_args, **_kwargs: (0, "applied", ""))

    def scheduled_lifecycle(_namespace, _name, predicate, *_args):
        calls.append(f"schedule-{predicate}")
        if predicate == "recovered":
            raise AssertionError("Schedule must be stopped before recovery is evaluated")
        return True, {"selected_child": "scheduled-kill-child"}, []

    def delete_schedule(*_args):
        calls.append("cleanup")
        return {"absent_confirmed": True}

    def wait_target(*_args, **_kwargs):
        calls.append("target-recovery")
        return True, {"ready": True}, []

    journeys = iter(
        [
            {"pass": True, "samples": []},
            {"pass": False, "samples": []},
            {"pass": True, "samples": []},
            {"pass": True, "samples": []},
        ]
    )

    def journey():
        value = next(journeys)
        calls.append("journey")
        return value

    monkeypatch.setattr(runner, "wait_for_scheduled_lifecycle", scheduled_lifecycle)
    monkeypatch.setattr(runner, "delete_schedule_with_children", delete_schedule)
    monkeypatch.setattr(runner, "wait_for_target_ready", wait_target)
    monkeypatch.setattr(runner, "global_residuals", lambda: ([], []))
    monkeypatch.setattr(runner, "capture_diagnostics", lambda *_args: {"status": "captured", "files": []})
    monkeypatch.setattr(runner, "run_journey", journey)

    report = runner.run_one(
        mutation,
        tmp_path / "report.json",
        "ChaosAtlas-full",
        1001,
        "scheduled-catalogue-db-pod-kill",
        1,
        baseline_count=1,
        washout_seconds=0,
        washout_successes=1,
        washout_timeout=1,
    )

    assert report["status"] == "completed"
    assert report["recovery"]["resource_recovered"] is True
    assert calls == [
        "journey",
        "schedule-injected",
        "journey",
        "cleanup",
        "target-recovery",
        "journey",
        "journey",
        "target-recovery",
    ]


def test_sock_shop_diagnostics_always_emit_zipkin_json_placeholder(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(runner, "run_kubectl", lambda *_args, **_kwargs: (0, "{}", ""))
    result = runner.capture_diagnostics(tmp_path / "rep-1.json", "name=payment")
    paths = {Path(item["path"]).name for item in result["files"]}
    assert "events.json" in paths
    assert "zipkin.json" in paths


def test_sock_shop_diagnostics_shorten_windows_long_paths(tmp_path: Path) -> None:
    report = tmp_path / ("route-aware-runtime-" + "x" * 120) / ("schedule-" + "y" * 70 + "-rep-2.json")
    directory = runner.diagnostics_directory(report)

    assert directory.name.startswith("d-")
    assert len(str(directory / "front-end.log")) < 260


def test_sock_shop_diagnostics_uses_absolute_length_for_relative_reports(monkeypatch) -> None:
    monkeypatch.setattr(runner, "WINDOWS_PATH_SAFE_LIMIT", 1)
    directory = runner.diagnostics_directory(Path("relative/runtime-reports/rep-1.json"))

    assert directory.name.startswith("d-")


def test_response_contracts_and_observation_classification() -> None:
    assert contract_ok("front-end", "<html>shop</html>") is True
    assert contract_ok("catalogue", "[]") is True
    assert contract_ok("login", "Cookie is set") is True
    assert contract_ok("orders", '{"orders": []}') is True
    passing = [{"pass": True}, {"pass": True}]
    failing = [{"pass": True}, {"pass": False}]
    assert classify_observation(passing) == "no_business_impact_observed"
    assert classify_observation(failing) == "weakness_observed"


def test_resolve_api_key_prefers_explicit_file(tmp_path: Path, monkeypatch) -> None:
    key_file = tmp_path / "deepseek_api_key.txt"
    key_file.write_text("  file-key\n", encoding="utf-8")
    monkeypatch.setenv("CHAOS_EATER_API_KEY", "environment-key")

    key, source = resolve_api_key(None, key_file)

    assert key == "file-key"
    assert source == str(key_file)


def test_resolve_api_key_uses_environment_before_default_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CHAOS_EATER_API_KEY", "environment-key")

    key, source = resolve_api_key(None, None, default_file=tmp_path / "missing-key.txt")

    assert key == "environment-key"
    assert source == "CHAOS_EATER_API_KEY"


def test_resolve_api_key_returns_no_secret_when_sources_are_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("CHAOS_EATER_API_KEY", raising=False)

    key, source = resolve_api_key(None, None, default_file=tmp_path / "missing-key.txt")

    assert key is None
    assert source is None


def test_configure_console_output_uses_utf8_when_supported(monkeypatch) -> None:
    class FakeStream:
        def __init__(self) -> None:
            self.options: dict[str, str] | None = None

        def reconfigure(self, **kwargs: str) -> None:
            self.options = kwargs

    stdout = FakeStream()
    stderr = FakeStream()
    monkeypatch.setattr(runner.sys, "stdout", stdout)
    monkeypatch.setattr(runner.sys, "stderr", stderr)

    runner.configure_console_output()

    assert stdout.options == {"encoding": "utf-8", "errors": "replace"}
    assert stderr.options == {"encoding": "utf-8", "errors": "replace"}


def test_failed_washout_preserves_journey_evidence(tmp_path: Path, monkeypatch) -> None:
    mutation = tmp_path / "stress.yaml"
    mutation.write_text(
        yaml.safe_dump(
            {
                "apiVersion": "chaos-mesh.org/v1alpha1",
                "kind": "StressChaos",
                "metadata": {"name": "test-stress", "namespace": NAMESPACE},
                "spec": {
                    "mode": "one",
                    "selector": {"namespaces": [NAMESPACE], "labelSelectors": {"name": "payment"}},
                    "stressors": {"cpu": {"workers": 1, "load": 50}},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runner,
        "check_mutation",
        lambda _path: {
            "decision": "ready_for_injection",
            "kind": "StressChaos",
            "name": "test-stress",
            "checks": {"target_pods": [{"uid": "before"}]},
        },
    )
    monkeypatch.setattr(runner, "start_port_forward", lambda *_args: object())
    monkeypatch.setattr(runner, "wait_for_port", lambda *_args: None)
    monkeypatch.setattr(runner, "stop_process", lambda _process: {"stopped_by_runner": True})
    monkeypatch.setattr(runner, "run_kubectl", lambda *_args, **_kwargs: (0, "applied", ""))
    monkeypatch.setattr(runner, "wait_for_lifecycle", lambda *_args: (True, {}, []))
    target_ready_calls = []

    def target_ready(*args, **kwargs):
        target_ready_calls.append((args, kwargs))
        return True, {"ready_pods": ["front-end-1"]}, []

    monkeypatch.setattr(runner, "wait_for_target_ready", target_ready)
    monkeypatch.setattr(runner, "delete_resource", lambda *_args: {"absent_confirmed": True})
    monkeypatch.setattr(runner, "global_residuals", lambda: ([], []))
    monkeypatch.setattr(runner, "capture_diagnostics", lambda *_args: {"status": "captured", "files": []})
    calls = {"journey": 0, "clock": 0}

    def journey() -> dict[str, bool]:
        calls["journey"] += 1
        return {"pass": calls["journey"] <= 15}

    def clock() -> float:
        calls["clock"] += 1
        return calls["clock"] * 31.0

    monkeypatch.setattr(runner, "run_journey", journey)
    monkeypatch.setattr(runner.time, "monotonic", clock)
    monkeypatch.setattr(runner.time, "sleep", lambda _seconds: None)

    report = runner.run_one(
        mutation,
        tmp_path / "report.json",
        "runtime-gate",
        0,
        "washout-evidence",
        1,
        washout_seconds=60,
        washout_successes=2,
        washout_timeout=180,
    )

    assert report["status"] == "failed"
    assert report["washout"]["stable"] is False
    assert len(report["washout"]["journeys"]) > 0
    assert report["washout"]["consecutive_successes"] == 0
    assert report["diagnostics"]["status"] == "captured"


def test_port_forward_does_not_pipe_unbounded_kubectl_output(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeSubprocess:
        PIPE = object()

        class Process:
            pass

        def Popen(self, args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return self.Process()

    monkeypatch.setattr(runner.subprocess, "Popen", FakeSubprocess().Popen)
    runner.start_port_forward(NAMESPACE, "front-end", 18081, 80)

    kwargs = captured["kwargs"]
    assert kwargs["stdout"] is not runner.subprocess.PIPE
    assert kwargs["stderr"] is not runner.subprocess.PIPE
    assert kwargs["stdout"].name.endswith(".log")
    assert kwargs["stderr"] == kwargs["stdout"]


def test_recovered_chaos_restarts_frontend_port_forward_after_cleanup(tmp_path: Path, monkeypatch) -> None:
    mutation = tmp_path / "pod-kill.yaml"
    mutation.write_text(
        yaml.safe_dump(
            {
                "apiVersion": "chaos-mesh.org/v1alpha1",
                "kind": "NetworkChaos",
                "metadata": {"name": "test-kill", "namespace": NAMESPACE},
                "spec": {
                    "action": "delay",
                    "mode": "one",
                    "selector": {"namespaces": [NAMESPACE], "labelSelectors": {"name": "front-end"}},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runner,
        "check_mutation",
        lambda _path: {
            "decision": "ready_for_injection",
            "kind": "PodChaos",
            "name": "test-kill",
            "selector": {"labelSelectors": {"name": "front-end"}},
            "checks": {"target_pods": [{"uid": "before"}]},
        },
    )
    processes: list[object] = []
    monkeypatch.setattr(runner, "start_port_forward", lambda *_args: processes.append(object()) or processes[-1])
    monkeypatch.setattr(runner, "wait_for_port", lambda *_args: None)
    monkeypatch.setattr(runner, "stop_process", lambda _process: {"stopped_by_runner": True})
    monkeypatch.setattr(runner, "run_kubectl", lambda *_args, **_kwargs: (0, "applied", ""))
    monkeypatch.setattr(runner, "wait_for_lifecycle", lambda *_args: (True, {}, []))
    monkeypatch.setattr(runner, "wait_for_target_ready", lambda *_args, **_kwargs: (True, {}, []))
    monkeypatch.setattr(runner, "delete_resource", lambda *_args: {"absent_confirmed": True})
    monkeypatch.setattr(runner, "global_residuals", lambda: ([], []))
    monkeypatch.setattr(runner, "run_journey", lambda: {"pass": True, "samples": []})

    report = runner.run_one(
        mutation,
        tmp_path / "report.json",
        "ChaosAtlas-full",
        1001,
        "front-end-pod-kill",
        1,
        baseline_count=1,
        washout_seconds=0,
        washout_successes=1,
        washout_timeout=1,
    )

    assert report["status"] == "completed"
    assert len(processes) == 2


@pytest.mark.parametrize(("target_ready", "expected_status"), [(True, "completed"), (False, "failed")])
def test_recovery_rebinds_frontend_port_forward_when_restarted_process_exits(
    tmp_path: Path,
    monkeypatch,
    target_ready: bool,
    expected_status: str,
) -> None:
    mutation = tmp_path / "network-delay.yaml"
    mutation.write_text(
        yaml.safe_dump(
            {
                "apiVersion": "chaos-mesh.org/v1alpha1",
                "kind": "NetworkChaos",
                "metadata": {"name": "test-delay", "namespace": NAMESPACE},
                "spec": {
                    "action": "delay",
                    "mode": "one",
                    "selector": {"namespaces": [NAMESPACE], "labelSelectors": {"name": "front-end"}},
                    "duration": "30s",
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runner,
        "check_mutation",
        lambda _path: {
            "decision": "ready_for_injection",
            "kind": "NetworkChaos",
            "name": "test-delay",
            "selector": {"labelSelectors": {"name": "front-end"}},
            "checks": {"target_pods": [{"uid": "front-end"}]},
        },
    )

    class FakeProcess:
        def __init__(self, alive: bool = True) -> None:
            self.alive = alive

        def poll(self) -> int | None:
            return None if self.alive else 1

    processes = [FakeProcess(), FakeProcess(alive=False), FakeProcess()]

    def start_fake_port_forward(*_args):
        return processes.pop(0)

    monkeypatch.setattr(runner, "start_port_forward", start_fake_port_forward)
    monkeypatch.setattr(runner, "wait_for_port", lambda *_args: None)
    monkeypatch.setattr(runner, "stop_process", lambda _process: {"stopped_by_runner": True})
    monkeypatch.setattr(runner, "run_kubectl", lambda *_args, **_kwargs: (0, "applied", ""))
    monkeypatch.setattr(runner, "wait_for_lifecycle", lambda *_args: (True, {}, []))
    target_ready_calls = []

    def wait_target_ready(*args, **kwargs):
        target_ready_calls.append((args, kwargs))
        return target_ready, {"ready_pods": ["front-end-1"] if target_ready else []}, ([] if target_ready else ["target not ready"])

    monkeypatch.setattr(runner, "wait_for_target_ready", wait_target_ready)
    monkeypatch.setattr(runner, "delete_resource", lambda *_args: {"absent_confirmed": True})
    monkeypatch.setattr(runner, "global_residuals", lambda: ([], []))
    monkeypatch.setattr(runner, "run_journey", lambda: {"pass": True, "samples": []})

    report = runner.run_one(
        mutation,
        tmp_path / "report.json",
        "ChaosAtlas-full",
        1003,
        "front-end-network-delay",
        1,
        baseline_count=1,
        washout_seconds=0,
        washout_successes=1,
        washout_timeout=1,
    )

    assert report["status"] == expected_status
    assert report["recovery"]["recovered"] is True
    assert report["recovery"]["port_forward_rebinds"] == 2
    assert len(target_ready_calls) == 1
    assert report["washout"]["target_ready"] is target_ready
    if not target_ready:
        assert "target not ready" in report["errors"]


def test_recovery_rebinds_frontend_port_forward_after_local_connection_refused(tmp_path: Path, monkeypatch) -> None:
    mutation = tmp_path / "network-delay.yaml"
    mutation.write_text(
        yaml.safe_dump(
            {
                "apiVersion": "chaos-mesh.org/v1alpha1",
                "kind": "NetworkChaos",
                "metadata": {"name": "test-delay", "namespace": NAMESPACE},
                "spec": {
                    "action": "delay",
                    "mode": "one",
                    "selector": {"namespaces": [NAMESPACE], "labelSelectors": {"name": "front-end"}},
                    "duration": "30s",
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runner,
        "check_mutation",
        lambda _path: {
            "decision": "ready_for_injection",
            "kind": "NetworkChaos",
            "name": "test-delay",
            "selector": {"labelSelectors": {"name": "front-end"}},
            "checks": {"target_pods": [{"uid": "front-end"}]},
        },
    )

    class FakeProcess:
        def poll(self) -> int | None:
            return None

    processes = [FakeProcess(), FakeProcess(), FakeProcess()]
    monkeypatch.setattr(runner, "start_port_forward", lambda *_args: processes.pop(0))
    monkeypatch.setattr(runner, "wait_for_port", lambda *_args: None)
    monkeypatch.setattr(runner, "stop_process", lambda _process: {"stopped_by_runner": True})
    monkeypatch.setattr(runner, "run_kubectl", lambda *_args, **_kwargs: (0, "applied", ""))
    monkeypatch.setattr(runner, "wait_for_lifecycle", lambda *_args: (True, {}, []))
    monkeypatch.setattr(runner, "wait_for_target_ready", lambda *_args, **_kwargs: (True, {}, []))
    monkeypatch.setattr(runner, "delete_resource", lambda *_args: {"absent_confirmed": True})
    monkeypatch.setattr(runner, "global_residuals", lambda: ([], []))
    journeys = iter(
        [
            {"pass": True, "samples": []},
            {"pass": True, "samples": []},
            {
                "pass": False,
                "samples": [
                    {
                        "step": step,
                        "status_code": None,
                        "pass": False,
                        "error": "<urlopen error [WinError 10061] connection refused>",
                    }
                    for step, _path in STEPS
                ],
                },
                {"pass": True, "samples": []},
                {"pass": True, "samples": []},
            ]
        )
    monkeypatch.setattr(runner, "run_journey", lambda: next(journeys))

    report = runner.run_one(
        mutation,
        tmp_path / "report.json",
        "ChaosAtlas-full",
        1003,
        "front-end-network-delay",
        1,
        baseline_count=1,
        washout_seconds=0,
        washout_successes=1,
        washout_timeout=1,
    )

    assert report["status"] == "completed"
    assert report["recovery"]["port_forward_rebinds"] == 2
