from __future__ import annotations

import json

import pytest

from pathlib import Path

from tools.run_two_arm_deepseek_discovery import build_messages, bundle_path_for, discovery_status, redact_secret, validate_response_shape


def test_messages_keep_method_knowledge_boundary() -> None:
    bundle = {
        "project_id": "opentelemetry-demo",
        "method_id": "ChaosAtlas-full",
        "seed": 1001,
        "common_input": {"project_id": "opentelemetry-demo", "topology": {"nodes": []}},
        "knowledge_view": {"facts": [{"pattern": "single_replica_workload"}]},
    }
    system, user = build_messages(bundle)
    assert "Return only JSON" in system
    assert "target_kind must be exactly service or dependency_edge" in system
    assert "call_chain must be an array" in system
    assert '"method_id": "ChaosAtlas-full"' in user
    assert "single_replica_workload" in user


def test_ablation_message_does_not_add_knowledge() -> None:
    bundle = {
        "project_id": "opentelemetry-demo",
        "method_id": "ChaosAtlas-ablation",
        "seed": 1001,
        "common_input": {"project_id": "opentelemetry-demo", "topology": {"nodes": []}},
        "knowledge_view": None,
    }
    _, user = build_messages(bundle)
    assert '"knowledge_view": null' in user


def test_messages_include_topology_derived_fault_family_contract() -> None:
    bundle = {
        "project_id": "demo",
        "method_id": "ChaosAtlas-ablation",
        "seed": 1002,
        "common_input": {
            "project_id": "demo",
            "topology": {
                "nodes": [
                    {"id": "workload/api", "role": "workload"},
                    {"id": "service/api", "role": "routing"},
                ],
                "edges": [],
            },
        },
        "knowledge_view": None,
    }

    system, user = build_messages(bundle)

    assert "pod_kill is permitted only for workload targets" in system
    payload = json.loads(user)
    assert payload["allowed_fault_families"]["workload/api"] == [
        "container_cpu_stress",
        "network_delay",
        "network_loss",
        "pod_kill",
    ]
    assert payload["allowed_fault_families"]["service/api"] == ["network_delay", "network_loss"]


def test_response_shape_rejects_non_object_or_too_many_hypotheses() -> None:
    with pytest.raises(ValueError, match="object"):
        validate_response_shape([])
    with pytest.raises(ValueError, match="at most 8"):
        validate_response_shape({"hypotheses": [{}] * 9})


def test_secret_redaction_does_not_write_plaintext() -> None:
    raw = "token=super-secret-value"
    redacted = redact_secret(raw, "super-secret-value")
    assert "super-secret-value" not in redacted
    assert "[REDACTED]" in redacted


def test_bundle_path_is_parameterized_by_project() -> None:
    root = Path("inputs")
    assert bundle_path_for(root, "sock-shop", 1002, "ChaosAtlas-ablation") == root / "input_bundles" / "sock-shop" / "seed-1002" / "chaosatlas-ablation.json"


def test_discovery_status_requires_exactly_four_selected_and_compiled_mutations() -> None:
    ready = {"status": "handoff_ready", "selected_hypotheses": [{}, {}, {}, {}]}
    compiled = {"status": "valid", "generated": [{}, {}, {}, {}]}
    assert discovery_status(ready, compiled) == "valid"
    assert discovery_status({**ready, "selected_hypotheses": [{}, {}, {}]}, compiled) == "method_invalid"
    assert discovery_status(ready, {**compiled, "generated": [{}, {}, {}]}) == "method_invalid"
