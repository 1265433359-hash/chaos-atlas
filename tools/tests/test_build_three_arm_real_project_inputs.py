from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.build_three_arm_real_project_inputs import (
    build_three_arm_bundle_set,
    build_full_v1_projection,
    write_three_arm_bundle_root,
)


def manifest() -> dict:
    return {
        "project_id": "demo",
        "common_input": {
            "schema_version": "common-v1",
            "project_id": "demo",
            "project_commit": "a" * 40,
            "topology": {"project_id": "demo", "nodes": [], "edges": [], "graph_hash": "g"},
            "business_oracle": {"workflow": "GET /", "success": "HTTP 200"},
        },
    }


def projection(version: str) -> dict:
    return {
        "schema_version": f"chaosatlas-generic-knowledge-projection-{version}",
        "human_review": "pending",
        "knowledge_base_updated": False,
        "projection_sha256": version,
    }


def test_three_arm_bundles_share_common_input_and_separate_knowledge() -> None:
    bundles = build_three_arm_bundle_set(
        manifest(),
        seed=1001,
        full_v1=projection("v1"),
        full_v2=projection("v2"),
    )

    assert set(bundles) == {"ChaosAtlas-full-v1", "ChaosAtlas-full-v2", "ChaosAtlas-ablation"}
    common_values = {json.dumps(bundle["common_input"], sort_keys=True) for bundle in bundles.values()}
    assert len(common_values) == 1
    assert bundles["ChaosAtlas-full-v1"]["knowledge_view"]["schema_version"].endswith("v1")
    assert bundles["ChaosAtlas-full-v2"]["knowledge_view"]["schema_version"].endswith("v2")
    assert bundles["ChaosAtlas-ablation"]["knowledge_view"] is None


def test_three_arm_bundles_reject_non_pending_or_updated_projection() -> None:
    invalid = projection("v2")
    invalid["human_review"] = "approved"
    with pytest.raises(ValueError, match="pending"):
        build_three_arm_bundle_set(manifest(), seed=1001, full_v1=projection("v1"), full_v2=invalid)


def test_three_arm_bundles_have_distinct_hashes_only_for_method_envelope() -> None:
    bundles = build_three_arm_bundle_set(
        manifest(),
        seed=1001,
        full_v1=projection("v1"),
        full_v2=projection("v2"),
    )
    assert bundles["ChaosAtlas-full-v1"]["common_input_sha256"] == bundles["ChaosAtlas-ablation"]["common_input_sha256"]
    assert bundles["ChaosAtlas-full-v1"]["method_id"] != bundles["ChaosAtlas-full-v2"]["method_id"]


def test_full_v1_projection_is_versioned_and_pending() -> None:
    value = build_full_v1_projection()
    assert value["schema_version"] == "chaosatlas-generic-knowledge-projection-v1"
    assert value["human_review"] == "pending"
    assert value["knowledge_base_updated"] is False
    assert len(value["projection_sha256"]) == 64


def test_writer_emits_three_method_files_and_refuses_nonempty_output(tmp_path: Path) -> None:
    manifest_value = manifest()
    full_v1 = projection("v1")
    full_v2 = projection("v2")
    result = write_three_arm_bundle_root(
        {"demo": manifest_value},
        tmp_path / "inputs",
        full_v1=full_v1,
        full_v2=full_v2,
        projects=("demo",),
    )

    seed_dir = tmp_path / "inputs" / "input_bundles" / "demo" / "seed-1001"
    assert (seed_dir / "chaosatlas-full-v1.json").is_file()
    assert (seed_dir / "chaosatlas-full-v2.json").is_file()
    assert (seed_dir / "chaosatlas-ablation.json").is_file()
    assert result["methods"] == [
        "ChaosAtlas-full-v1",
        "ChaosAtlas-full-v2",
        "ChaosAtlas-ablation",
    ]

    with pytest.raises(FileExistsError, match="non-empty"):
        write_three_arm_bundle_root(
            {"demo": manifest_value},
            tmp_path / "inputs",
            full_v1=full_v1,
            full_v2=full_v2,
            projects=("demo",),
        )


def test_writer_accepts_per_project_full_v2_projection_map(tmp_path: Path) -> None:
    alpha = manifest()
    alpha["project_id"] = "alpha"
    alpha["common_input"]["project_id"] = "alpha"
    beta = manifest()
    beta["project_id"] = "beta"
    beta["common_input"]["project_id"] = "beta"
    full_v1 = projection("v1")
    full_v2_alpha = projection("v2")
    full_v2_alpha["projection_sha256"] = "alpha-v2"
    full_v2_beta = projection("v2")
    full_v2_beta["projection_sha256"] = "beta-v2"

    result = write_three_arm_bundle_root(
        {"alpha": alpha, "beta": beta},
        tmp_path / "inputs",
        full_v1=full_v1,
        full_v2_by_project={"alpha": full_v2_alpha, "beta": full_v2_beta},
        projects=("alpha", "beta"),
    )

    alpha_bundle = json.loads(
        (tmp_path / "inputs" / "input_bundles" / "alpha" / "seed-1001" / "chaosatlas-full-v2.json").read_text()
    )
    beta_bundle = json.loads(
        (tmp_path / "inputs" / "input_bundles" / "beta" / "seed-1001" / "chaosatlas-full-v2.json").read_text()
    )
    assert alpha_bundle["knowledge_view"]["projection_sha256"] == "alpha-v2"
    assert beta_bundle["knowledge_view"]["projection_sha256"] == "beta-v2"
    assert result["records"][0]["full_v2_projection_sha256"] == "alpha-v2"
    assert result["records"][3]["full_v2_projection_sha256"] == "beta-v2"
