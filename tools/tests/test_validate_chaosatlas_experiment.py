from __future__ import annotations

from tools.validate_chaosatlas_experiment import PROJECT_ORDER, validate_feedback_manifest


def test_feedback_manifest_requires_registered_order_and_prior_project() -> None:
    card = {
        "card_id": "FA-1",
        "project_id": "P01",
        "project_commit": "a" * 40,
        "source_round_id": "round-1",
        "classification": "protected",
        "review": {"status": "human_reviewed"},
        "abstraction": {"weakness_family": "single_replica", "target_role": "entrypoint"},
    }
    manifest = {"project_order": PROJECT_ORDER, "target_project": "P02", "round_id": "round-1", "cards": [card]}
    assert validate_feedback_manifest(manifest)["valid"] is True
    same_project = dict(manifest, target_project="P01")
    assert validate_feedback_manifest(same_project)["valid"] is False


def test_feedback_manifest_rejects_unreviewed_or_runtime_abstraction() -> None:
    card = {
        "card_id": "FA-2",
        "project_id": "P01",
        "project_commit": "a" * 40,
        "source_round_id": "round-1",
        "classification": "confirmed_weakness",
        "review": {"status": "pending"},
        "abstraction": {"mutation_path": "podchaos/delete"},
    }
    manifest = {"project_order": PROJECT_ORDER, "target_project": "P02", "round_id": "round-1", "cards": [card]}
    result = validate_feedback_manifest(manifest)
    assert result["valid"] is False
    assert any(item["reason"] == "knowledge_boundary_failed" for item in result["errors"])
