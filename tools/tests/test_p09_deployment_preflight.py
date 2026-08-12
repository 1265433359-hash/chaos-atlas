from __future__ import annotations

from tools.p09_deployment_preflight import build


def test_p09_requires_reduced_profile_env_and_digest_pinning() -> None:
    result = build()
    assert result["status"] == "blocked"
    assert result["runtime_apply_allowed"] is False
    assert "required_env_missing:docker/.env,docker/middleware.env" in result["reasons"]
    assert "mutable_images_require_digest_pinning" in result["reasons"]
    assert "api" in result["core_profile"]
