from __future__ import annotations

import hashlib
import json

from tools.contamination_audit import audit_bundle, audit_feedback_manifest, canonical_sha256


def test_ablation_and_chaoseater_cannot_receive_knowledge_view() -> None:
    shared = {
        "project_id": "P08",
        "seed": 1001,
        "common_input": {"project_id": "P08"},
        "topology_evidence": {"nodes": []},
    }
    knowledge = {"knowledge_status": "source_only_pre_runtime", "project_id": "P08"}

    ablation = audit_bundle(dict(shared, arm="ChaosAtlas-ablation", knowledge_view=knowledge), "")
    eater = audit_bundle(dict(shared, arm="ChaosEater-full", knowledge_view=knowledge), "")

    assert ablation["valid"] is False
    assert "knowledge_view_forbidden_for_ablation" in ablation["errors"]
    assert eater["valid"] is False
    assert "knowledge_view_forbidden_for_chaoseater" in eater["errors"]


def test_full_method_rejects_runtime_feedback_from_same_project() -> None:
    bundle = {
        "project_id": "P09",
        "seed": 1001,
        "arm": "ChaosAtlas-full",
        "knowledge_view": {
            "content": {
                "source_project_id": "P09",
                "source_round_id": "r3",
                "abstraction": {"weakness_family": "pod_kill"},
            }
        },
    }
    result = audit_bundle(bundle, "")
    assert result["valid"] is False
    assert "same_project_runtime_feedback" in result["errors"]


def test_feedback_manifest_requires_projection_hash_and_isolates_methods() -> None:
    projection = {
        "source_project_id": "P01",
        "source_project_commit": "a" * 40,
        "source_round_id": "round-1",
        "abstraction": {"weakness_family": "single_replica"},
    }
    manifest = {
        "target_project": "P02",
        "target_commit": "b" * 40,
        "target_method": "ChaosAtlas-full",
        "feedback_round": "round-1",
        "project_order": ["P01", "P02"],
        "human_review": {"status": "approved"},
        "projections": [dict(projection, projection_sha256=canonical_sha256(projection))],
    }
    assert audit_feedback_manifest(manifest)["valid"] is True

    bad = json.loads(json.dumps(manifest))
    bad["target_method"] = "ChaosAtlas-ablation"
    assert audit_feedback_manifest(bad)["valid"] is False
    assert "feedback_forbidden_for_method" in audit_feedback_manifest(bad)["errors"]

    bad_hash = json.loads(json.dumps(manifest))
    bad_hash["projections"][0]["projection_sha256"] = "0" * 64
    assert audit_feedback_manifest(bad_hash)["valid"] is False
    assert "projection_hash_mismatch" in audit_feedback_manifest(bad_hash)["errors"]


def test_feedback_projection_rejects_runtime_fields() -> None:
    projection = {
        "source_project_id": "P01",
        "source_project_commit": "a" * 40,
        "source_round_id": "round-1",
        "abstraction": {"weakness_family": "pod_kill", "mutation_path": "secret"},
    }
    manifest = {
        "target_project": "P02",
        "target_commit": "b" * 40,
        "target_method": "ChaosAtlas-full",
        "feedback_round": "round-1",
        "project_order": ["P01", "P02"],
        "human_review": {"status": "approved"},
        "projections": [dict(projection, projection_sha256=hashlib.sha256(b"wrong").hexdigest())],
    }
    result = audit_feedback_manifest(manifest)
    assert result["valid"] is False
    assert "forbidden_runtime_field:abstraction.mutation_path" in result["errors"]
