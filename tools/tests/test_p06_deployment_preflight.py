from __future__ import annotations

from tools.p06_deployment_preflight import build


def test_p06_sparse_snapshot_fails_closed_without_application_service() -> None:
    result = build()
    assert result["status"] == "blocked"
    assert result["runtime_apply_allowed"] is False
    assert "package.json" in result["reasons"][0]
    assert result["application_service_present"] is False
    assert "no_directus_application_service" in result["reasons"][1]
