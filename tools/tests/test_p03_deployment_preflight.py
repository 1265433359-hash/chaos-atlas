from __future__ import annotations

from tools.p03_deployment_preflight import build


def test_p03_frozen_snapshot_is_blocked_by_missing_build_inputs() -> None:
    result = build()
    assert result["status"] == "blocked"
    assert result["runtime_apply_allowed"] is False
    assert any("pyproject.toml" in reason for reason in result["reasons"])
    assert "application_service_missing" in result["reasons"]
