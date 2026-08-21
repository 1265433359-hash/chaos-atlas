from __future__ import annotations

import json
from pathlib import Path
import pytest

from tools.sock_shop_disambiguation import (
    classify_business_readiness_contradiction,
    collect_frontend_disambiguation,
    summarize_disambiguation_timeline,
)


class FakeRunner:
    def __init__(self, responses: dict[tuple[str, ...], tuple[int, str, str]]):
        self.responses = responses
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, args: list[str], timeout: int = 30, input_text: str | None = None):
        self.calls.append(tuple(args))
        return self.responses.get(tuple(args), (1, "", "not configured"))


def _pod(uid: str, *, ready: bool, deletion_timestamp: str | None = None, ip: str = "10.0.0.1") -> dict:
    metadata = {"name": f"front-end-{uid}", "uid": uid, "creationTimestamp": "2026-08-20T14:00:00Z"}
    if deletion_timestamp:
        metadata["deletionTimestamp"] = deletion_timestamp
    return {
        "metadata": metadata,
        "status": {
            "podIP": ip,
            "phase": "Running",
            "conditions": [{"type": "Ready", "status": "True" if ready else "False"}],
        },
    }


def test_collector_captures_pods_endpoints_deployment_and_events(tmp_path: Path):
    responses = {
        ("get", "pods", "-n", "sock-shop-lab", "-l", "name=front-end", "-o", "json"): (0, json.dumps({"items": [_pod("new", ready=True)]}), ""),
        ("get", "endpoints", "front-end", "-n", "sock-shop-lab", "-o", "json"): (0, json.dumps({"subsets": [{"addresses": [{"ip": "10.0.0.1"}]}]}), ""),
        ("get", "deployment", "front-end", "-n", "sock-shop-lab", "-o", "json"): (0, json.dumps({"spec": {"replicas": 1, "strategy": {"type": "RollingUpdate", "rollingUpdate": {"maxUnavailable": 1, "maxSurge": 0}}, "template": {"spec": {"containers": [{"name": "front-end", "readinessProbe": {"httpGet": {"path": "/", "port": 8079}}}]}}}}), ""),
        ("get", "events", "-n", "sock-shop-lab", "-o", "json"): (0, json.dumps({"items": [{"reason": "Killing"}]}), ""),
    }
    result = collect_frontend_disambiguation(
        root=tmp_path,
        namespace="sock-shop-lab",
        service="front-end",
        selector="name=front-end",
        window={"start": "2026-08-20T14:55:00Z", "end": "2026-08-20T14:56:00Z"},
        runner=FakeRunner(responses),
    )
    assert set(result) == {"observations", "evidence"}
    assert result["observations"]["pods"]["items"][0]["metadata"]["uid"] == "new"
    assert {item["kind"] for item in result["evidence"]} == {"config", "kubernetes_event"}
    assert all(item["sha256"] for item in result["evidence"])


def test_collector_marks_events_unavailable_without_bounded_window(tmp_path: Path):
    result = collect_frontend_disambiguation(root=tmp_path, namespace="sock-shop-lab", runner=FakeRunner({}))
    event = next(item for item in result["evidence"] if item["evidence_id"] == "EV-DISAMBIG-EVENTS-001")
    assert event["polarity"] == "unavailable"
    assert event["unavailable_reason"] == "event_window_required"


def test_collector_rejects_non_isolated_sock_shop_namespace(tmp_path: Path):
    with pytest.raises(ValueError, match="sock-shop-lab"):
        collect_frontend_disambiguation(root=tmp_path, namespace="default")


def test_classifier_marks_http_200_as_old_pod_serving_when_endpoint_keeps_terminating_ip():
    result = classify_business_readiness_contradiction(
        pod_before={"items": [_pod("old", ready=True, ip="10.0.0.9")]},
        pod_during={"items": [_pod("old", ready=False, deletion_timestamp="2026-08-20T14:55:00Z", ip="10.0.0.9"), _pod("new", ready=True, ip="10.0.0.8")]},
        endpoints_during={"subsets": [{"addresses": [{"ip": "10.0.0.9"}], "notReadyAddresses": [{"ip": "10.0.0.8"}]}]},
        business_samples=[{"status_code": 200}, {"status_code": 200}],
        observation_phase="during_injection",
    )
    assert result["classification"] == "old_pod_still_serving"
    assert result["deterministic"] is True


def test_classifier_does_not_treat_not_ready_endpoint_as_serving():
    result = classify_business_readiness_contradiction(
        pod_before={"items": [_pod("old", ready=True, ip="10.0.0.9")]},
        pod_during={"items": [_pod("old", ready=False, deletion_timestamp="2026-08-20T14:55:00Z", ip="10.0.0.9"), _pod("new", ready=True, ip="10.0.0.8")]},
        endpoints_during={"subsets": [{"addresses": [{"ip": "10.0.0.8"}], "notReadyAddresses": [{"ip": "10.0.0.9"}]}]},
        business_samples=[{"status_code": 200}],
        observation_phase="during_injection",
    )
    assert result["classification"] == "defended"


def test_classifier_marks_http_200_as_old_pod_serving_when_old_uid_remains_in_endpoints():
    result = classify_business_readiness_contradiction(
        pod_before={"items": [_pod("old", ready=True, ip="10.0.0.9")]},
        pod_during={"items": [_pod("old", ready=True, ip="10.0.0.9"), _pod("new", ready=True, ip="10.0.0.8")]},
        endpoints_during={"subsets": [{"addresses": [{"ip": "10.0.0.9"}, {"ip": "10.0.0.8"}]}]},
        business_samples=[{"status_code": 200}],
        observation_phase="during_injection",
    )
    assert result["classification"] == "old_pod_still_serving"


def test_classifier_requires_endpoint_and_timeline_for_defended():
    result = classify_business_readiness_contradiction(
        pod_before={"items": [_pod("old", ready=True, ip="10.0.0.9")]},
        pod_during={"items": [_pod("new", ready=True, ip="10.0.0.8")]},
        endpoints_during={"subsets": [{"addresses": [{"ip": "10.0.0.8"}]}]},
        business_samples=[{"status_code": 200}, {"status_code": 200}],
        observation_phase="during_injection",
    )
    assert result["classification"] == "defended"
    assert result["deterministic"] is True


def test_classifier_is_inconclusive_without_business_samples_or_endpoint_observation():
    result = classify_business_readiness_contradiction(
        pod_before={"items": [_pod("old", ready=True)]},
        pod_during={"items": [_pod("new", ready=True)]},
        endpoints_during={},
        business_samples=[],
        observation_phase="during_injection",
    )
    assert result["classification"] == "observation_inconclusive"
    assert result["deterministic"] is False


def test_classifier_rejects_post_recovery_snapshot_as_observation_window_artifact():
    result = classify_business_readiness_contradiction(
        pod_before={"items": [_pod("old", ready=True, ip="10.0.0.9")]},
        pod_during={"items": [_pod("new", ready=True, ip="10.0.0.8")]},
        endpoints_during={"subsets": [{"addresses": [{"ip": "10.0.0.8"}]}]},
        business_samples=[{"status_code": 200}],
        observation_phase="post_recovery",
    )
    assert result["classification"] == "observation_inconclusive"
    assert result["deterministic"] is False
    assert result["reason"] == "Pod and Endpoint snapshots are not from the injection window"


def test_classifier_defaults_to_unknown_phase_and_fails_closed():
    result = classify_business_readiness_contradiction(
        pod_before={"items": [_pod("old", ready=True, ip="10.0.0.9")]},
        pod_during={"items": [_pod("new", ready=True, ip="10.0.0.8")]},
        endpoints_during={"subsets": [{"addresses": [{"ip": "10.0.0.8"}]}]},
        business_samples=[{"status_code": 200}],
    )
    assert result["classification"] == "observation_inconclusive"
    assert result["deterministic"] is False
    assert result["observation_phase"] == "unknown"


def test_classifier_rejects_replacement_without_uid():
    result = classify_business_readiness_contradiction(
        pod_before={"items": [_pod("old", ready=True, ip="10.0.0.9")]},
        pod_during={"items": [{"status": {"podIP": "10.0.0.8", "conditions": [{"type": "Ready", "status": "True"}]}}]},
        endpoints_during={"subsets": [{"addresses": [{"ip": "10.0.0.8"}]}]},
        business_samples=[{"status_code": 200}],
        observation_phase="during_injection",
    )
    assert result["classification"] == "observation_inconclusive"
    assert result["deterministic"] is False


def test_classifier_does_not_call_failed_business_contract_defended():
    result = classify_business_readiness_contradiction(
        pod_before={"items": [_pod("old", ready=True, ip="10.0.0.9")]},
        pod_during={"items": [_pod("new", ready=True, ip="10.0.0.8")]},
        endpoints_during={"subsets": [{"addresses": [{"ip": "10.0.0.8"}]}]},
        business_samples=[{"status_code": 200, "contract_ok": False}],
        observation_phase="during_injection",
    )
    assert result["classification"] == "observation_inconclusive"
    assert result["deterministic"] is False


def test_classifier_handles_malformed_items_without_raising():
    result = classify_business_readiness_contradiction(
        pod_before={"items": None},
        pod_during={"items": "invalid"},
        endpoints_during={"subsets": [{"addresses": [{"ip": "10.0.0.8"}]}]},
        business_samples=[{"status_code": 200}],
        observation_phase="during_injection",
    )
    assert result["classification"] == "observation_inconclusive"
    assert result["deterministic"] is False


def test_classifier_treats_endpoint_object_without_subsets_as_observed_empty():
    result = classify_business_readiness_contradiction(
        pod_before={"items": [_pod("old", ready=True, ip="10.0.0.9")]},
        pod_during={"items": [_pod("new", ready=False, ip="10.0.0.8")]},
        endpoints_during={"kind": "Endpoints", "metadata": {"name": "front-end"}},
        business_samples=[{"status_code": 200}],
        observation_phase="during_injection",
    )
    assert result["endpoint_observed"] is True
    assert result["classification"] == "observation_inconclusive"
    assert result["observation_window_artifact"] is True


def test_collector_marks_malformed_json_unavailable(tmp_path: Path):
    runner = FakeRunner({
        ("get", "pods", "-n", "sock-shop-lab", "-l", "name=front-end", "-o", "json"): (0, "not-json", ""),
    })
    result = collect_frontend_disambiguation(root=tmp_path, namespace="sock-shop-lab", runner=runner)
    pods = next(item for item in result["evidence"] if item["evidence_id"] == "EV-DISAMBIG-PODS-001")
    assert pods["polarity"] == "unavailable"
    assert pods["unavailable_reason"] == "invalid_json"


def test_timeline_summary_prefers_old_pod_serving_when_any_injection_sample_proves_it():
    result = summarize_disambiguation_timeline(
        pod_before={"items": [_pod("old", ready=True, ip="10.0.0.9")]},
        samples=[
            {
                "observed_at": "2026-08-20T14:55:01Z",
                "pods": {"items": [_pod("old", ready=False, deletion_timestamp="2026-08-20T14:55:00Z", ip="10.0.0.9"), _pod("new", ready=True, ip="10.0.0.8")]},
                "endpoints": {"subsets": [{"addresses": [{"ip": "10.0.0.9"}], "notReadyAddresses": [{"ip": "10.0.0.8"}]}]},
                "business": {"status_code": 200},
            }
        ],
    )
    assert result["classification"] == "old_pod_still_serving"
    assert result["sample_count"] == 1


def test_timeline_summary_stays_inconclusive_when_http_200_has_no_ready_endpoint():
    result = summarize_disambiguation_timeline(
        pod_before={"items": [_pod("old", ready=True, ip="10.0.0.9")]},
        samples=[
            {
                "observed_at": "2026-08-20T14:55:01Z",
                "pods": {"items": [_pod("new", ready=True, ip="10.0.0.8")]},
                "endpoints": {"subsets": []},
                "business": {"status_code": 200},
            }
        ],
    )
    assert result["classification"] == "observation_inconclusive"
    assert result["deterministic"] is False
