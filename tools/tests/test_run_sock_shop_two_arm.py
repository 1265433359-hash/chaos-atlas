from pathlib import Path

import yaml

import tools.run_sock_shop_two_arm as runner
from tools.run_sock_shop_two_arm import STEPS, NAMESPACE, classify_observation, contract_ok, oracle_passes, validate_mutation


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


def test_response_contracts_and_observation_classification() -> None:
    assert contract_ok("front-end", "<html>shop</html>") is True
    assert contract_ok("catalogue", "[]") is True
    assert contract_ok("login", "Cookie is set") is True
    assert contract_ok("orders", '{"orders": []}') is True
    passing = [{"pass": True}, {"pass": True}]
    failing = [{"pass": True}, {"pass": False}]
    assert classify_observation(passing) == "no_business_impact_observed"
    assert classify_observation(failing) == "weakness_observed"


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
    monkeypatch.setattr(runner, "delete_resource", lambda *_args: {"absent_confirmed": True})
    monkeypatch.setattr(runner, "global_residuals", lambda: ([], []))
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


def test_recovery_rebinds_frontend_port_forward_when_restarted_process_exits(tmp_path: Path, monkeypatch) -> None:
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

    assert report["status"] == "completed"
    assert report["recovery"]["recovered"] is True
    assert report["recovery"]["port_forward_rebinds"] == 2


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
