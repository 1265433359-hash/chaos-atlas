from pathlib import Path

import yaml

from tools.run_sock_shop_confidence_runtime import (
    build_runtime_invocation,
    compile_hypothesis_to_mutation,
    plan_confidence_runtime,
)


def _hypothesis(category: str, target: str, action: str) -> dict:
    return {
        "method": "native-full",
        "id": f"{target}-{action}",
        "category": category,
        "target_service": target,
        "action_or_target": action,
        "call_chain_position": "business-service",
        "motifs": [f"action_or_target={action}"],
    }


def test_compile_network_hypothesis_to_exact_namespace_local_mutation(tmp_path):
    compiled = compile_hypothesis_to_mutation(
        _hypothesis("Network degradation", "catalogue", "delay"),
        tmp_path,
    )

    document = yaml.safe_load(Path(compiled["path"]).read_text(encoding="utf-8"))
    assert compiled["kind"] == "NetworkChaos"
    assert len(compiled["sha256"]) == 64
    assert document["metadata"]["namespace"] == "chaosatlas-sock-shop"
    assert document["spec"]["selector"]["namespaces"] == ["chaosatlas-sock-shop"]
    assert document["spec"]["selector"]["labelSelectors"] == {"name": "catalogue"}
    assert document["spec"]["mode"] == "one"
    assert document["spec"]["action"] == "delay"


def test_compile_memory_stress_uses_chaos_mesh_admission_compatible_size(tmp_path):
    compiled = compile_hypothesis_to_mutation(
        _hypothesis("Resource pressure", "carts-db", "memory"),
        tmp_path,
    )

    document = yaml.safe_load(Path(compiled["path"]).read_text(encoding="utf-8"))
    assert document["kind"] == "StressChaos"
    assert document["spec"]["stressors"]["memory"]["size"] == "256MB"


def test_runtime_plan_keeps_gate_failures_and_emits_timing_contract(tmp_path):
    discovery = {
        "method": "native-full",
        "hypotheses": [
            _hypothesis("Network degradation", "catalogue", "delay"),
            _hypothesis("Pod disruption", "orders", "pod-kill"),
            _hypothesis("Protocol/HTTP fault", "front-end", "abort"),
        ],
    }

    plan = plan_confidence_runtime(
        {"native-full": discovery},
        output_dir=tmp_path,
    )

    method = plan["methods"]["native-full"]
    assert method["runtime_candidates"] == 2
    assert method["gate_failed"] == 1
    assert method["candidates"][2]["gate"]["reason"] == "runner_unsupported_category"
    assert plan["timing_fields"] == [
        "generation_seconds",
        "compile_seconds",
        "gate_seconds",
        "runtime_seconds",
        "washout_seconds",
        "total_wall_clock_seconds",
    ]
    assert plan["recovery_timeout_seconds"] == 180


def test_runtime_invocation_is_metadata_only_unless_execute_is_requested(tmp_path):
    compiled = compile_hypothesis_to_mutation(
        _hypothesis("Pod disruption", "orders", "pod-kill"),
        tmp_path,
    )

    invocation = build_runtime_invocation(
        compiled,
        tmp_path / "report.json",
        execute=False,
        replicate=1,
    )

    assert invocation["executed"] is False
    assert invocation["command"][0]
    assert "--report" in invocation["command"]
    assert "--recovery-timeout" in invocation["command"]


def test_execute_plan_stops_after_first_failed_runtime(tmp_path, monkeypatch):
    discovery = {
        "method": "native-full",
        "hypotheses": [
            _hypothesis("Pod disruption", "orders", "pod-kill"),
            _hypothesis("Pod disruption", "catalogue", "pod-kill"),
        ],
    }

    class Completed:
        returncode = 2

    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return Completed()

    monkeypatch.setattr("tools.run_sock_shop_confidence_runtime.subprocess.run", fake_run)
    plan = plan_confidence_runtime({"native-full": discovery}, output_dir=tmp_path, execute=True)

    assert plan["status"] == "stopped_on_failure"
    assert len(calls) == 1
    assert plan["methods"]["native-full"]["runtime_candidates"] == 2
    assert plan["methods"]["native-full"]["processed_runtime_candidates"] == 1


def test_execute_plan_reuses_prior_completed_reports_without_rerun(tmp_path, monkeypatch):
    prior = tmp_path / "prior" / "methods" / "native-full" / "runtime_reports"
    prior.mkdir(parents=True)
    (prior / "orders-pod-kill-rep-1.json").write_text('{"status":"completed"}', encoding="utf-8")
    discovery = {
        "method": "native-full",
        "hypotheses": [_hypothesis("Pod disruption", "orders", "pod-kill")],
    }
    calls = []

    class Completed:
        returncode = 0

    def fake_run(command, **_kwargs):
        calls.append(command)
        return Completed()

    monkeypatch.setattr("tools.run_sock_shop_confidence_runtime.subprocess.run", fake_run)
    out = tmp_path / "resume"
    plan = plan_confidence_runtime(
        {"native-full": discovery},
        output_dir=out,
        execute=True,
        prior_runtime_roots=[tmp_path / "prior"],
    )

    invocations = plan["methods"]["native-full"]["candidates"][0]["runtime_invocations"]
    assert invocations[0]["skipped_completed"] is True
    assert invocations[0]["source_report"].endswith("orders-pod-kill-rep-1.json")
    assert (out / "methods" / "native-full" / "runtime_reports" / "orders-pod-kill-rep-1.json").exists()
    assert len(calls) == 1
