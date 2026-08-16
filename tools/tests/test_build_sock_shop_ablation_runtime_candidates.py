import json

from tools.build_sock_shop_ablation_runtime_candidates import (
    build_ablation_runtime_candidates,
    infer_runtime_category,
)


def test_posthoc_category_inference_is_not_part_of_discovery():
    assert infer_runtime_category("pod-kill") == "Pod disruption"
    assert infer_runtime_category("delay") == "Network degradation"
    assert infer_runtime_category("cpu") == "Resource pressure"
    assert infer_runtime_category("dns") == "Protocol/HTTP fault"
    assert infer_runtime_category("unknown") is None


def test_builder_keeps_source_discovery_immutable_and_marks_posthoc_mapping(tmp_path):
    discovery_path = tmp_path / "discovery.json"
    source = {
        "method": "chaosatlas-ablation",
        "status": "completed",
        "self_stop": True,
        "hypotheses": [
            {
                "id": "h-1",
                "target_service": "catalogue",
                "action_or_target": "delay",
                "call_chain_position": "business-service",
            },
            {
                "id": "h-2",
                "target_service": "orders",
                "action_or_target": "unknown",
                "call_chain_position": "business-service",
            },
        ],
    }
    discovery_path.write_text(json.dumps(source), encoding="utf-8")
    original = discovery_path.read_bytes()

    result = build_ablation_runtime_candidates(discovery_path, tmp_path / "runtime")

    assert discovery_path.read_bytes() == original
    assert result["source_hypotheses"] == 2
    assert result["compiled_hypotheses"] == 1
    assert result["blocked_hypotheses"] == 1
    compiled = json.loads((tmp_path / "runtime" / "posthoc-runtime-discovery.json").read_text(encoding="utf-8"))
    assert compiled["hypotheses"][0]["category"] == "Network degradation"
    assert compiled["hypotheses"][0]["category_assignment"] == "posthoc_runtime_adapter"
    assert "category" not in source["hypotheses"][0]
    assert (tmp_path / "runtime" / "runtime" / "runtime_plan.json").exists()


def test_builder_accepts_yaml15_arm_without_erasing_its_classification_boundary(tmp_path):
    discovery_path = tmp_path / "discovery.json"
    source = {
        "method": "chaosatlas-ablation-yaml15",
        "status": "completed",
        "self_stop": True,
        "yaml15_provenance": {"prompt_sha256": "a" * 64},
        "hypotheses": [
            {
                "id": "yaml15-h-1",
                "target_service": "catalogue",
                "action_or_target": "delay",
                "call_chain_position": "after front-end",
                "call_chain_position_source": "model_inference",
            }
        ],
    }
    discovery_path.write_text(json.dumps(source), encoding="utf-8")

    result = build_ablation_runtime_candidates(discovery_path, tmp_path / "runtime")

    compiled = json.loads((tmp_path / "runtime" / "posthoc-runtime-discovery.json").read_text(encoding="utf-8"))
    assert result["method"] == "chaosatlas-ablation-yaml15"
    assert compiled["hypotheses"][0]["method"] == "chaosatlas-ablation-yaml15"
    assert compiled["posthoc_runtime_adapter"]["classification_examples_visible_to_discovery"] is True
    plan = json.loads((tmp_path / "runtime" / "runtime" / "runtime_plan.json").read_text(encoding="utf-8"))
    assert "chaosatlas-ablation-yaml15" in plan["methods"]


def test_yaml15_builder_deduplicates_before_runtime_and_preserves_family_members(tmp_path):
    discovery_path = tmp_path / "discovery.json"
    repeated = {
        "target_service": "catalogue",
        "action_or_target": "pod-kill",
        "call_chain_position": "catalogue browse step",
        "call_chain_position_source": "model_inference",
    }
    source = {
        "method": "chaosatlas-ablation-yaml15",
        "status": "completed",
        "self_stop": True,
        "hypotheses": [
            {"id": "yaml15-h-1", **repeated},
            {"id": "yaml15-h-2", **repeated},
            {
                "id": "yaml15-h-3",
                "target_service": "orders",
                "action_or_target": "delay",
                "call_chain_position": "orders read step",
                "call_chain_position_source": "model_inference",
            },
        ],
    }
    discovery_path.write_text(json.dumps(source), encoding="utf-8")

    result = build_ablation_runtime_candidates(discovery_path, tmp_path / "runtime")

    assert result["source_hypotheses"] == 3
    assert result["deduplicated_hypotheses"] == 2
    assert result["duplicate_hypotheses"] == 1
    compiled = json.loads((tmp_path / "runtime" / "posthoc-runtime-discovery.json").read_text(encoding="utf-8"))
    first = compiled["hypotheses"][0]
    assert first["id"] == "yaml15-h-1"
    assert first["family_size"] == 2
    assert first["family_members"] == ["yaml15-h-1", "yaml15-h-2"]
