from __future__ import annotations

import json
from pathlib import Path

from tools.build_native_full_inputs import build_native_knowledge_view, write_native_bundle_root


def test_native_knowledge_view_preserves_project_cards_and_marks_native_scope(tmp_path: Path) -> None:
    knowledge_root = tmp_path / "knowledge_base"
    knowledge_root.mkdir()
    (knowledge_root / "index.json").write_text(
        json.dumps({"schema_version": 1, "project": "demo", "cards": [{"id": "KB-1", "path": "KB-1.json"}]}),
        encoding="utf-8",
    )
    (knowledge_root / "KB-1.json").write_text(
        json.dumps({"id": "KB-1", "test_node_centered_graph": {"nodes": [{"id": "n1"}]}}),
        encoding="utf-8",
    )

    view = build_native_knowledge_view("demo", knowledge_root)

    assert view["schema_version"] == "chaosatlas-native-project-knowledge-v1"
    assert view["project_id"] == "demo"
    assert view["projection_used"] is False
    assert view["pollution_intentionally_not_excluded"] is True
    assert [card["id"] for card in view["cards"]] == ["KB-1"]
    assert view["cards"][0]["content"]["test_node_centered_graph"]["nodes"][0]["id"] == "n1"


def test_native_bundle_root_writes_only_native_full_and_keeps_common_input_identical(tmp_path: Path) -> None:
    common = {
        "schema_version": "common-v1",
        "project_id": "demo",
        "project_commit": "a" * 40,
        "namespace": "chaosatlas-demo",
        "topology": {"nodes": [{"id": "workload/api", "role": "workload"}], "edges": []},
        "business_oracle": {"workflow": "GET /", "success": "HTTP 200"},
    }
    knowledge = {
        "schema_version": "chaosatlas-native-project-knowledge-v1",
        "cards": [],
        "projection_used": False,
    }
    output = tmp_path / "native"

    result = write_native_bundle_root(
        project_id="demo",
        common_inputs={1001: common},
        native_knowledge=knowledge,
        output_root=output,
        seeds=(1001,),
    )

    bundle_path = output / "input_bundles" / "demo" / "seed-1001" / "chaosatlas-native-full.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    assert result["method"] == "ChaosAtlas-native-full"
    assert bundle["method_id"] == "ChaosAtlas-native-full"
    assert bundle["common_input"] == common
    assert bundle["knowledge_view"] == knowledge
    assert bundle["projection_used"] is False
    assert bundle["pollution_intentionally_not_excluded"] is True
    assert not (output / "input_bundles" / "demo" / "seed-1001" / "chaosatlas-full.json").exists()


def test_native_bundle_manifest_records_relative_or_absolute_path_without_crashing(tmp_path: Path) -> None:
    knowledge = {
        "schema_version": "chaosatlas-native-project-knowledge-v1",
        "cards": [],
        "projection_used": False,
    }
    common = {
        "project_id": "demo",
        "project_commit": "a" * 40,
        "namespace": "chaosatlas-demo",
        "topology": {"nodes": [], "edges": []},
        "business_oracle": {"workflow": "GET /", "success": "HTTP 200"},
    }

    result = write_native_bundle_root(
        project_id="demo",
        common_inputs={1001: common},
        native_knowledge=knowledge,
        output_root=tmp_path / "native",
        seeds=(1001,),
    )

    assert result["records"][0]["bundle"].endswith("chaosatlas-native-full.json")
    assert result["knowledge_snapshot"].endswith("native-knowledge.json")
