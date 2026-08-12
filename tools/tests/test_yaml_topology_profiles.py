from __future__ import annotations

from tools.build_yaml_topology_profiles import merge_reports


def test_partial_profile_update_preserves_existing_projects() -> None:
    merged = merge_reports([{"project_id": "P01", "graph_hash": "old"}, {"project_id": "P02", "graph_hash": "old2"}], [{"project_id": "P02", "graph_hash": "new"}])
    assert [item["project_id"] for item in merged] == ["P01", "P02"]
    assert merged[1]["graph_hash"] == "new"
