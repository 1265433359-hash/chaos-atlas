from __future__ import annotations

from tools.build_deployment_preflight_index import build


def test_preflight_index_is_secret_free_and_keeps_environment_separate() -> None:
    result = build()
    assert result["secret_free"] is True
    assert result["no_model_calls"] is True
    assert result["no_cluster_mutations"] is True
    assert {item["project_id"] for item in result["records"]} == {"P01", "P03", "P06", "P09"}
    assert all(item["status"] == "blocked" for item in result["records"])
