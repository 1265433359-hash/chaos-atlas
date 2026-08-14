from __future__ import annotations

import json

import pytest

from tools.build_full_v2_projection import build_leave_one_project_out_projection, build_projection


def runtime_card(*, card_id: str = "KB-GENERIC-001", project: str = "project-a") -> dict:
    return {
        "id": card_id,
        "status": "validated_runtime",
        "evidence_state": "runtime_observed",
        "project": project,
        "project_commit": "a" * 40,
        "test_node": {
            "family": "NetworkChaos",
            "operation": "delay",
            "direction": "to",
            "mode": "one",
            "duration": "30s",
        },
        "test_node_centered_graph": {
            "nodes": [
                {"id": "test.node", "kind": "TestNode"},
                {"id": "deploy.api", "kind": "TargetDeployment"},
                {"id": "call.downstream", "kind": "DownstreamCall"},
                {"id": "response.business", "kind": "BusinessOutcome"},
            ],
            "edges": [
                {"from": "test.node", "to": "deploy.api", "type": "selects", "confidence": "confirmed_runtime"},
                {"from": "deploy.api", "to": "call.downstream", "type": "calls", "confidence": "confirmed_static"},
                {"from": "call.downstream", "to": "response.business", "type": "flows_to", "confidence": "confirmed_runtime"},
            ],
        },
        "result_classification": {
            "classification": "latency_degradation",
            "defense_experience": "business response preserved while latency increased",
        },
    }


def async_queue_card() -> dict:
    card = runtime_card(card_id="KB-GENERIC-ASYNC", project="project-c")
    card["test_node"]["family"] = "PodChaos"
    card["test_node"]["operation"] = "pod-kill"
    card["test_node_centered_graph"] = {
        "nodes": [
            {"id": "test.node", "kind": "TestNode"},
            {"id": "deploy.worker", "kind": "TargetDeployment"},
            {"id": "queue.orders", "kind": "AsyncQueue"},
            {"id": "store.orders", "kind": "StateStore"},
            {"id": "response.business", "kind": "BusinessOutcome"},
        ],
        "edges": [
            {"from": "test.node", "to": "deploy.worker", "type": "selects", "confidence": "confirmed_runtime"},
            {"from": "deploy.worker", "to": "queue.orders", "type": "publishes", "confidence": "confirmed_runtime"},
            {"from": "queue.orders", "to": "store.orders", "type": "persists", "confidence": "confirmed_static"},
            {"from": "store.orders", "to": "response.business", "type": "flows_to", "confidence": "confirmed_runtime"},
        ],
    }
    card["runtime_result"] = {"classification": "station_success_response_preserved_with_small_latency_increase"}
    return card


def test_projection_abstracts_test_nodes_and_call_chain_roles() -> None:
    projection = build_projection([runtime_card()])

    assert projection["schema_version"] == "chaosatlas-generic-knowledge-projection-v2"
    assert projection["human_review"] == "pending"
    assert projection["knowledge_base_updated"] is False
    assert "test_node_patterns" not in projection
    assert "call_chain_patterns" not in projection
    assert projection["test_node_rules"][0]["fault"] == "network_delay"
    assert projection["test_node_rules"][0]["when"]["target_role"] == "workload"
    assert projection["call_chain_rules"][0]["path"] == [
        "test_node",
        "workload",
        "synchronous_downstream_call",
        "business_outcome",
    ]
    assert projection["call_chain_rules"][0]["properties"]["sync_boundary"] is True
    assert projection["call_chain_rules"][0]["properties"]["async_boundary"] is False
    encoded = json.dumps(projection, ensure_ascii=True)
    assert "project-a" not in encoded
    assert "KB-GENERIC-001" not in encoded
    assert "deploy.api" not in encoded


def test_projection_excludes_pending_cards_from_positive_rules() -> None:
    card = runtime_card()
    card["status"] = "pending_review"
    projection = build_projection([runtime_card(card_id="KB-RUNTIME"), card])

    assert projection["provenance"]["source_card_count"] == 2
    assert projection["provenance"]["runtime_validated_card_count"] == 1
    assert len(projection["test_node_rules"]) == 1
    assert projection["negative_evidence"][0]["evidence_state"] == "pending_review"


def test_projection_extracts_async_and_stateful_call_chain_properties() -> None:
    projection = build_projection([async_queue_card()])

    rule = projection["call_chain_rules"][0]
    assert rule["path"] == [
        "test_node",
        "workload",
        "async_queue",
        "state_store",
        "business_outcome",
    ]
    assert rule["properties"]["async_boundary"] is True
    assert rule["properties"]["stateful_dependency"] is True
    assert rule["properties"]["target_position"] == "workload"


def test_projection_normalizes_project_specific_outcomes() -> None:
    projection = build_projection([async_queue_card()])
    encoded = json.dumps(projection, ensure_ascii=True)

    assert "station_success_response" not in encoded
    taxonomy = {item["outcome"]: item for item in projection["outcome_taxonomy"]}
    assert taxonomy["business_response_preserved"]["runtime_support_count"] == 1
    assert taxonomy["latency_degradation"]["runtime_support_count"] == 1


def test_projection_records_platform_blocked_as_negative_evidence_only() -> None:
    blocked = runtime_card(card_id="KB-BLOCKED")
    blocked["status"] = "blocked_by_platform_prerequisite"
    blocked["evidence_state"] = "runtime_injection_blocked"
    blocked["result_classification"] = {"classification": "platform blocked by kernel dependency"}

    projection = build_projection([runtime_card(card_id="KB-RUNTIME"), blocked])

    assert projection["provenance"]["runtime_validated_card_count"] == 1
    assert all(rule["evidence"] == "runtime_observed" for rule in projection["test_node_rules"])
    assert any(item["outcome"] == "platform_blocked" for item in projection["negative_evidence"])


def test_projection_uses_status_when_blocked_card_has_no_classification() -> None:
    blocked = runtime_card(card_id="KB-BLOCKED")
    blocked["status"] = "blocked_by_platform_prerequisite"
    blocked["evidence_state"] = "runtime_injection_blocked"
    blocked.pop("result_classification")
    blocked.pop("runtime_result", None)

    projection = build_projection([runtime_card(card_id="KB-RUNTIME"), blocked])

    assert projection["negative_evidence"][0]["outcome"] == "platform_blocked"


def test_projection_is_deterministic_and_records_evidence_boundaries() -> None:
    first = build_projection([runtime_card(card_id="KB-2", project="project-b")])
    second = build_projection([runtime_card(card_id="KB-2", project="project-b")])

    assert first == second
    assert first["evidence_boundaries"]
    assert first["provenance"]["source_card_count"] == 1
    assert len(first["projection_sha256"]) == 64


def test_projection_accepts_historical_catalog_as_static_ranking_prior() -> None:
    catalog = {
        "source": {"file_count": 1935},
        "nodes": [
            {
                "node": "network_delay",
                "document_count": 213,
                "kind_counts": {"NetworkChaos": 213},
                "examples": ["raw_yaml/NetworkChaos/example.yaml"],
                "status": "candidate_pattern",
            },
            {
                "node": "pod_pod-kill",
                "document_count": 220,
                "kind_counts": {"PodChaos": 220},
                "examples": ["raw_yaml/PodChaos/example.yaml"],
                "status": "candidate_pattern",
            },
        ],
    }

    projection = build_projection([runtime_card()], historical_catalog=catalog)

    support = {item["fault_family"]: item for item in projection["historical_fault_pattern_support"]}
    assert support["network_delay"]["document_count"] == 213
    assert support["network_delay"]["evidence"] == "static_corpus_pattern_only"
    assert "raw_yaml" not in json.dumps(projection, ensure_ascii=True)


def test_leave_one_project_out_projection_excludes_target_project_cards() -> None:
    heldout = runtime_card(card_id="KB-OB", project="GoogleCloudPlatform/microservices-demo")
    transfer = runtime_card(card_id="KB-OTEL", project="open-telemetry/opentelemetry-demo")

    projection = build_leave_one_project_out_projection(
        [heldout, transfer],
        heldout_project_id="online-boutique",
    )

    assert projection["provenance"]["source_card_count"] == 1
    assert projection["provenance"]["runtime_validated_card_count"] == 1
    encoded = json.dumps(projection, ensure_ascii=True)
    assert "GoogleCloudPlatform" not in encoded
    assert "microservices-demo" not in encoded
    assert "online-boutique" not in encoded


def test_leave_one_project_out_projection_keeps_all_cards_for_project_without_prior_kb() -> None:
    cards = [
        runtime_card(card_id="KB-OB", project="GoogleCloudPlatform/microservices-demo"),
        runtime_card(card_id="KB-OTEL", project="open-telemetry/opentelemetry-demo"),
    ]

    projection = build_leave_one_project_out_projection(cards, heldout_project_id="sock-shop")

    assert projection["provenance"]["source_card_count"] == 2
    assert projection["provenance"]["runtime_validated_card_count"] == 2
