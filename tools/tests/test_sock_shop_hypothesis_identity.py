import hashlib
import json
from pathlib import Path

import yaml

from tools.sock_shop_hypothesis_identity import (
    fault_family_key,
    load_runtime_candidates,
    mutation_instance_key,
    normalize_action,
    normalize_kind,
    normalized_parameters,
    partition_method_sets,
    select_method_representatives,
)


def _hypothesis(**overrides):
    value = {
        "id": "h-1",
        "method": "native-full",
        "category": "Network degradation",
        "target_service": "catalogue-service",
        "action_or_target": "network-delay",
        "call_chain_position": "business service",
        "confidence": 0.7,
        "evidence_completeness": 1,
    }
    value.update(overrides)
    return value


def _mutation(**overrides):
    doc = {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "NetworkChaos",
        "metadata": {"name": "generated", "namespace": "chaosatlas-sock-shop"},
        "spec": {
            "action": "delay",
            "mode": "one",
            "duration": "30s",
            "direction": "to",
            "selector": {
                "labelSelectors": {"name": "catalogue"},
                "namespaces": ["chaosatlas-sock-shop"],
            },
            "delay": {"latency": "500ms", "correlation": "0"},
        },
    }
    doc["spec"].update(overrides)
    return doc


def _record(method, hypothesis, mutation, order):
    return {
        "method": method,
        "hypothesis": hypothesis,
        "mutation": mutation,
        "source_order": order,
        "source_path": f"{method}/{order}.yaml",
    }


def test_normalization_collapses_aliases_but_preserves_semantics():
    assert normalize_kind("network-chaos") == "NetworkChaos"
    assert normalize_action("NetworkChaos", "network-delay") == "delay"
    assert normalize_action("PodChaos", "kill") == "pod-kill"

    first = normalized_parameters(_mutation())
    second = normalized_parameters(_mutation(delay={"latency": "2s", "correlation": "0"}))
    assert first != second
    assert "metadata" not in first
    assert "duration=30s" in first
    assert "delay.latency=500ms" in first


def test_family_key_contains_call_chain_position_and_instance_key_contains_parameters():
    hypothesis = _hypothesis()
    mutation = _mutation()
    family = fault_family_key(hypothesis, mutation)
    instance = mutation_instance_key(hypothesis, mutation)

    assert "NetworkChaos" in family
    assert "delay" in family
    assert "catalogue" in family
    assert "business-service" in family
    assert instance.startswith(family + "|")
    assert "duration=30s" in instance


def test_full_representative_is_highest_confidence_then_evidence_then_order():
    mutation = _mutation()
    records = [
        _record("native-full", _hypothesis(id="first", confidence=0.9, evidence_completeness=0), mutation, 0),
        _record("native-full", _hypothesis(id="best", confidence=0.9, evidence_completeness=2), mutation, 1),
        _record("native-full", _hypothesis(id="lower", confidence=0.8, evidence_completeness=3), mutation, 2),
    ]

    selected = select_method_representatives(records, method="native-full")

    assert len(selected) == 1
    assert selected[0]["hypothesis"]["id"] == "best"


def test_ablation_representative_does_not_use_confidence_or_runtime_result():
    mutation = _mutation()
    records = [
        _record("chaosatlas-ablation", _hypothesis(id="first", confidence=0.1), mutation, 0),
        _record("chaosatlas-ablation", _hypothesis(id="later", confidence=0.99), mutation, 1),
    ]
    records[0]["runtime_classification"] = "no_business_impact"

    selected = select_method_representatives(records, method="chaosatlas-ablation")

    assert len(selected) == 1
    assert selected[0]["hypothesis"]["id"] == "first"


def test_partition_reports_family_and_strict_overlap_separately():
    full_mutation = _mutation()
    ablation_mutation = _mutation(delay={"latency": "2s", "correlation": "0"})
    full = [_record("native-full", _hypothesis(id="full"), full_mutation, 0)]
    ablation = [_record("chaosatlas-ablation", _hypothesis(id="ab", method="chaosatlas-ablation"), ablation_mutation, 0)]

    result = partition_method_sets(full, ablation)

    assert len(result["family_overlap"]) == 1
    assert len(result["strict_overlap"]) == 0
    assert not result["full_only"]
    assert not result["ablation_only"]


def test_runtime_plan_loader_uses_referenced_candidates_and_verifies_yaml_sha(tmp_path):
    mutation = _mutation()
    mutation_path = tmp_path / "mutations" / "candidate.yaml"
    mutation_path.parent.mkdir()
    mutation_path.write_text(yaml.safe_dump(mutation, sort_keys=False), encoding="utf-8")
    digest = hashlib.sha256(mutation_path.read_bytes()).hexdigest()
    plan = {
        "method": "native-full",
        "methods": {
            "native-full": {
                "candidates": [
                    {
                        "hypothesis_id": "h-1",
                        "path": str(mutation_path),
                        "sha256": digest,
                        "hypothesis": _hypothesis(),
                    }
                ]
            }
        },
    }
    plan_path = tmp_path / "runtime_plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    (mutation_path.parent / "unreferenced.yaml").write_text("kind: PodChaos\n", encoding="utf-8")

    result = load_runtime_candidates(plan_path, method="native-full")

    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["mutation_sha256"] == digest
    assert result["ignored_mutation_files"] == 1
