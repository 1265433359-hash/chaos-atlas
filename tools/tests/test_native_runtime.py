from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.native_rca_executor import NativeRCAExecutor
from tools.kubernetes_evidence import KubernetesEvidenceCollector


class FakeRunner:
    def __init__(self, responses: dict[tuple[str, ...], tuple[int, str, str]]):
        self.responses = responses
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, args: list[str], timeout: int = 30, input_text: str | None = None):
        self.calls.append(tuple(args))
        return self.responses.get(tuple(args), (1, "", "not configured"))


def test_kubernetes_collector_rejects_namespace_outside_allowlist(tmp_path: Path):
    runner = FakeRunner({})
    collector = KubernetesEvidenceCollector(
        root=tmp_path,
        allowed_namespaces={"sock-shop-lab"},
        runner=runner,
    )
    with pytest.raises(ValueError, match="namespace"):
        collector.collect_events(
            namespace="default",
            claim_scope="deployment:front-end",
            evidence_id="EV-EVENT-1",
        )
    assert runner.calls == []


def test_kubernetes_collector_writes_hashed_event_and_log_evidence(tmp_path: Path):
    runner = FakeRunner({
        ("get", "events", "-n", "sock-shop-lab", "-o", "json"): (
            0,
            json.dumps({"items": [{"reason": "Killing", "message": "pod replaced"}]}),
            "",
        ),
        ("logs", "deployment/front-end", "-n", "sock-shop-lab", "--since=2m"): (
            0,
            "connection refused while dependency unavailable\n",
            "",
        ),
    })
    collector = KubernetesEvidenceCollector(
        root=tmp_path,
        allowed_namespaces={"sock-shop-lab"},
        runner=runner,
    )
    event = collector.collect_events(
        namespace="sock-shop-lab",
        claim_scope="deployment:front-end",
        evidence_id="EV-EVENT-1",
    )
    log = collector.collect_logs(
        namespace="sock-shop-lab",
        workload="deployment/front-end",
        claim_scope="deployment:front-end",
        evidence_id="EV-LOG-1",
        since="2m",
    )
    assert event["kind"] == "kubernetes_event"
    assert log["kind"] == "runtime_log"
    assert event["sha256"] and log["sha256"]
    assert (tmp_path / event["source_ref"]).is_file()
    assert (tmp_path / log["source_ref"]).is_file()


def test_kubernetes_collector_collects_planned_resource_facts(tmp_path: Path):
    runner = FakeRunner({
        ("get", "deployment", "front-end", "-n", "sock-shop-lab", "-o", "json"): (
            0, json.dumps({"metadata": {"name": "front-end"}, "spec": {"replicas": 1}}), ""
        ),
        ("get", "service", "front-end", "-n", "sock-shop-lab", "-o", "json"): (
            0, json.dumps({"metadata": {"name": "front-end"}, "spec": {"ports": [{"port": 80}]}}), ""
        ),
        ("get", "pods", "-n", "sock-shop-lab", "-l", "name=front-end", "-o", "json"): (
            0, json.dumps({"items": [{"metadata": {"name": "front-end-1"}, "status": {"phase": "Running"}}]}), ""
        ),
    })
    collector = KubernetesEvidenceCollector(
        root=tmp_path,
        allowed_namespaces={"sock-shop-lab"},
        runner=runner,
    )

    deployment = collector.collect_deployment_facts(
        namespace="sock-shop-lab", deployment="front-end", claim_scope="deployment:front-end", evidence_id="EV-DEP-1"
    )
    service = collector.collect_service_facts(
        namespace="sock-shop-lab", service="front-end", claim_scope="deployment:front-end", evidence_id="EV-SVC-1"
    )
    pods = collector.collect_pod_state(
        namespace="sock-shop-lab", selector={"name": "front-end"}, claim_scope="deployment:front-end", evidence_id="EV-PODS-1"
    )

    assert deployment["kind"] == "manifest"
    assert service["kind"] == "config"
    assert pods["kind"] == "config"
    assert all(item["sha256"] for item in (deployment, service, pods))
    assert runner.calls == [
        ("get", "deployment", "front-end", "-n", "sock-shop-lab", "-o", "json"),
        ("get", "service", "front-end", "-n", "sock-shop-lab", "-o", "json"),
        ("get", "pods", "-n", "sock-shop-lab", "-l", "name=front-end", "-o", "json"),
    ]


def test_kubernetes_resource_facts_are_projected_before_sensitive_scan(tmp_path: Path):
    runner = FakeRunner({
        ("get", "deployment", "api", "-n", "sock-shop-lab", "-o", "json"): (
            0,
            json.dumps({"metadata": {"name": "api"}, "spec": {"replicas": 1, "template": {"spec": {"serviceAccountName": "api"}}, "token": "must-not-persist"}}),
            "",
        ),
    })
    collector = KubernetesEvidenceCollector(root=tmp_path, allowed_namespaces={"sock-shop-lab"}, runner=runner)

    evidence = collector.collect_deployment_facts(
        namespace="sock-shop-lab", deployment="api", claim_scope="deployment:api", evidence_id="EV-DEP-SAFE"
    )

    assert evidence["polarity"] == "supports"
    content = (tmp_path / evidence["source_ref"]).read_text(encoding="utf-8")
    assert "must-not-persist" not in content
    assert "serviceAccountName" not in content
    assert '"name": "api"' in content


def test_kubernetes_collector_can_pin_an_explicit_kube_context(tmp_path: Path):
    runner = FakeRunner({
        ("--context", "minikube", "get", "events", "-n", "sock-shop-lab", "-o", "json"): (
            0, json.dumps({"items": []}), ""
        ),
    })
    collector = KubernetesEvidenceCollector(
        root=tmp_path,
        allowed_namespaces={"sock-shop-lab"},
        runner=runner,
        kube_context="minikube",
    )

    evidence = collector.collect_events(
        namespace="sock-shop-lab", claim_scope="deployment:front-end", evidence_id="EV-CONTEXT-1"
    )

    assert evidence["polarity"] == "supports"
    assert runner.calls == [("--context", "minikube", "get", "events", "-n", "sock-shop-lab", "-o", "json")]


def test_native_executor_config_lookup_returns_evidence_without_mutation(tmp_path: Path):
    runner = FakeRunner({
        ("get", "deployment", "api", "-n", "sock-shop-lab", "-o", "json"): (
            0,
            json.dumps({"metadata": {"name": "api"}, "spec": {"replicas": 1}}),
            "",
        ),
    })
    executor = NativeRCAExecutor(
        root=tmp_path,
        namespace="sock-shop-lab",
        allowed_namespaces={"sock-shop-lab"},
        runner=runner,
    )
    result = executor({
        "action_id": "A-NATIVE-API-CONFIG-001",
        "kind": "config_lookup",
        "target_scope": "deployment:api",
        "namespace": "sock-shop-lab",
    })
    assert result["status"] == "observed"
    assert result["evidence"][0]["kind"] == "config"
    assert result["evidence"][0]["polarity"] == "supports"
    assert runner.calls == [
        ("get", "deployment", "api", "-n", "sock-shop-lab", "-o", "json")
    ]


def test_native_executor_blocks_mutation_without_gate_and_manifest(tmp_path: Path):
    runner = FakeRunner({})
    executor = NativeRCAExecutor(
        root=tmp_path,
        namespace="sock-shop-lab",
        allowed_namespaces={"sock-shop-lab"},
        runner=runner,
    )
    result = executor({
        "action_id": "A-NATIVE-API-INJECT-001",
        "kind": "native_fault_injection",
        "target_scope": "deployment:api",
        "namespace": "sock-shop-lab",
    })
    assert result["status"] == "environment_blocked"
    assert "mutation_manifest" in result["errors"][0]
    assert runner.calls == []


def test_native_executor_collects_logs_and_events(tmp_path: Path):
    runner = FakeRunner({
        ("logs", "deployment/api", "-n", "sock-shop-lab", "--since=2m"): (0, "request failed\n", ""),
        ("get", "events", "-n", "sock-shop-lab", "-o", "json"): (0, json.dumps({"items": []}), ""),
    })
    executor = NativeRCAExecutor(
        root=tmp_path,
        namespace="sock-shop-lab",
        allowed_namespaces={"sock-shop-lab"},
        runner=runner,
    )
    logs = executor({
        "action_id": "A-LOG-1",
        "kind": "log_lookup",
        "target_scope": "deployment:api",
        "workload": "deployment/api",
        "namespace": "sock-shop-lab",
    })
    events = executor({
        "action_id": "A-EVENT-1",
        "kind": "event_lookup",
        "target_scope": "deployment:api",
        "namespace": "sock-shop-lab",
    })
    assert logs["status"] == "observed"
    assert logs["evidence"][0]["kind"] == "runtime_log"
    assert events["status"] == "observed"
    assert events["evidence"][0]["kind"] == "kubernetes_event"
