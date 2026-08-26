from __future__ import annotations

from pathlib import Path

from tools.planned_evidence import collect_planned_evidence


class RecordingCollector:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def collect_deployment_facts(self, **kwargs):
        self.calls.append(("deployment_facts", kwargs))
        return {"evidence_id": kwargs["evidence_id"], "kind": "manifest", "source_ref": "runtime/deployment.json", "polarity": "supports"}

    def collect_service_facts(self, **kwargs):
        self.calls.append(("service_facts", kwargs))
        return {"evidence_id": kwargs["evidence_id"], "kind": "config", "source_ref": "runtime/service.json", "polarity": "supports"}

    def collect_pod_state(self, **kwargs):
        self.calls.append(("pod_state", kwargs))
        return {"evidence_id": kwargs["evidence_id"], "kind": "config", "source_ref": "runtime/pods.json", "polarity": "supports"}

    def collect_events(self, **kwargs):
        self.calls.append(("pod_events", kwargs))
        return {"evidence_id": kwargs["evidence_id"], "kind": "kubernetes_event", "source_ref": "runtime/events.json", "polarity": "supports"}

    def collect_logs(self, **kwargs):
        self.calls.append(("pod_logs", kwargs))
        return {"evidence_id": kwargs["evidence_id"], "kind": "runtime_log", "source_ref": "runtime/logs.log", "polarity": "supports"}


def _plan() -> dict:
    return {
        "status": "planned",
        "selection": {"candidate_ids": ["candidate-1"]},
        "actions": [
            {"action_id": "candidate-1:deployment_facts", "action_kind": "deployment_facts", "candidate_id": "candidate-1", "target": "front-end", "target_kind": "deployment", "read_only": True},
            {"action_id": "candidate-1:service_facts", "action_kind": "service_facts", "candidate_id": "candidate-1", "target": "front-end", "target_kind": "deployment", "read_only": True},
            {"action_id": "candidate-1:pod_state", "action_kind": "pod_state", "candidate_id": "candidate-1", "target": "front-end", "target_kind": "deployment", "read_only": True},
            {"action_id": "candidate-1:pod_events", "action_kind": "pod_events", "candidate_id": "candidate-1", "target": "front-end", "target_kind": "deployment", "read_only": True},
            {"action_id": "candidate-1:pod_logs", "action_kind": "pod_logs", "candidate_id": "candidate-1", "target": "front-end", "target_kind": "deployment", "read_only": True},
        ],
    }


def test_collect_planned_evidence_dispatches_only_allowlisted_actions(tmp_path: Path) -> None:
    collector = RecordingCollector()

    records = collect_planned_evidence(
        plan=_plan(),
        collector=collector,
        output_root=tmp_path,
        namespace="sock-shop-lab",
        target="front-end",
        selector={"name": "front-end"},
        evidence_prefix="planned-r1",
        claim_scope="deployment:front-end",
    )

    assert [kind for kind, _ in collector.calls] == [
        "deployment_facts", "service_facts", "pod_state", "pod_events", "pod_logs",
    ]
    assert len(records) == 5
    assert all(item["evidence_id"].startswith("planned-r1-") for item in records)
    assert [item["planned_action_id"] for item in records] == [
        "candidate-1:deployment_facts", "candidate-1:service_facts", "candidate-1:pod_state",
        "candidate-1:pod_events", "candidate-1:pod_logs",
    ]


def test_blocked_or_unplanned_actions_are_not_dispatched(tmp_path: Path) -> None:
    collector = RecordingCollector()
    plan = _plan()
    plan["status"] = "blocked"

    records = collect_planned_evidence(
        plan=plan,
        collector=collector,
        output_root=tmp_path,
        namespace="sock-shop-lab",
        target="front-end",
        selector={"name": "front-end"},
        evidence_prefix="blocked-r1",
        claim_scope="deployment:front-end",
    )

    assert records == []
    assert collector.calls == []


def test_service_action_uses_its_planned_service_target(tmp_path: Path) -> None:
    collector = RecordingCollector()
    plan = _plan()
    plan["actions"][1]["target"] = "catalogue-service"
    plan["actions"][1]["deployment_target"] = "front-end"

    collect_planned_evidence(
        plan=plan,
        collector=collector,
        output_root=tmp_path,
        namespace="sock-shop-lab",
        target="front-end",
        selector={"name": "front-end"},
        evidence_prefix="planned-r2",
        claim_scope="deployment:front-end",
    )

    service_calls = [kwargs for kind, kwargs in collector.calls if kind == "service_facts"]
    assert len(service_calls) == 1
    assert service_calls[0]["service"] == "catalogue-service"
