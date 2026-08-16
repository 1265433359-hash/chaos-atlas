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


def test_compile_protocol_http_fault_to_namespace_local_httpchaos(tmp_path):
    compiled = compile_hypothesis_to_mutation(
        _hypothesis("Protocol/HTTP fault", "front-end", "abort"),
        tmp_path,
    )

    document = yaml.safe_load(Path(compiled["path"]).read_text(encoding="utf-8"))
    assert compiled["kind"] == "HTTPChaos"
    assert document["metadata"]["namespace"] == "chaosatlas-sock-shop"
    assert document["spec"]["selector"]["namespaces"] == ["chaosatlas-sock-shop"]
    assert document["spec"]["selector"]["labelSelectors"] == {"name": "front-end"}
    assert document["spec"]["target"] == "Response"
    assert document["spec"]["abort"] is True
    assert document["spec"]["port"] == 8079
    assert document["spec"]["path"] == "*"


def test_compile_http_fault_uses_target_call_path_for_business_service(tmp_path):
    compiled = compile_hypothesis_to_mutation(
        _hypothesis("Protocol/HTTP fault", "carts", "abort"),
        tmp_path,
    )

    document = yaml.safe_load(Path(compiled["path"]).read_text(encoding="utf-8"))
    assert document["spec"]["port"] == 80
    assert document["spec"]["path"] == "/carts*"
    assert compiled["http_route"] == {
        "port": 80,
        "path": "/carts*",
        "source": "sock-shop-call-chain:front-end->carts",
    }


def test_compile_http_fault_rejects_non_http_dependency_targets(tmp_path):
    compiled = compile_hypothesis_to_mutation(
        _hypothesis("Protocol/HTTP fault", "catalogue-db", "abort"),
        tmp_path,
    )

    assert compiled["path"] is None
    assert compiled["gate"] == {
        "status": "failed",
        "reason": "http_target_not_applicable:catalogue-db",
    }


def test_compile_dns_fault_matches_the_live_sock_shop_service_domain(tmp_path):
    compiled = compile_hypothesis_to_mutation(
        _hypothesis("Protocol/HTTP fault", "catalogue", "dns_error"),
        tmp_path,
    )

    document = yaml.safe_load(Path(compiled["path"]).read_text(encoding="utf-8"))
    assert compiled["kind"] == "DNSChaos"
    assert document["spec"]["selector"]["labelSelectors"] == {"name": "front-end"}
    assert document["spec"]["patterns"] == ["catalogue.chaosatlas-sock-shop.svc.cluster.local"]
    assert compiled["dns_route"]["source"] == "sock-shop-call-chain:front-end->catalogue"


def test_compile_dns_fault_uses_orders_as_the_lookup_source_for_payment(tmp_path):
    compiled = compile_hypothesis_to_mutation(
        _hypothesis("Protocol/HTTP fault", "payment", "dns_error"),
        tmp_path,
    )

    document = yaml.safe_load(Path(compiled["path"]).read_text(encoding="utf-8"))
    assert document["spec"]["selector"]["labelSelectors"] == {"name": "orders"}
    assert document["spec"]["patterns"] == ["payment.chaosatlas-sock-shop.svc.cluster.local"]


def test_compile_scheduled_fault_to_namespace_local_schedule(tmp_path):
    compiled = compile_hypothesis_to_mutation(
        _hypothesis("Composite/scheduled fault", "payment", "scheduled-delay"),
        tmp_path,
    )

    document = yaml.safe_load(Path(compiled["path"]).read_text(encoding="utf-8"))
    assert compiled["kind"] == "Schedule"
    assert document["metadata"]["namespace"] == "chaosatlas-sock-shop"
    assert document["spec"]["type"] == "PodChaos"
    assert document["spec"]["schedule"] == "@every 30s"
    assert document["spec"]["podChaos"]["selector"]["namespaces"] == ["chaosatlas-sock-shop"]


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
    assert method["runtime_candidates"] == 3
    assert method["gate_failed"] == 0
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


def test_fresh_only_rejects_prior_runtime_roots_before_planning(tmp_path):
    discovery = {
        "method": "native-full",
        "hypotheses": [_hypothesis("Pod disruption", "orders", "pod-kill")],
    }

    import pytest

    with pytest.raises(ValueError, match="fresh-only"):
        plan_confidence_runtime(
            {"native-full": discovery},
            output_dir=tmp_path / "fresh",
            execute=False,
            prior_runtime_roots=[tmp_path / "prior"],
            fresh_only=True,
        )


def test_runtime_planner_rejects_confidence_incomplete_discovery(tmp_path):
    discovery = {
        "method": "native-full",
        "status": "confidence_incomplete",
        "hypotheses": [_hypothesis("Pod disruption", "orders", "pod-kill")],
    }

    import pytest

    with pytest.raises(ValueError, match="confidence-incomplete"):
        plan_confidence_runtime(
            {"native-full": discovery},
            output_dir=tmp_path / "incomplete",
            fresh_only=True,
        )
