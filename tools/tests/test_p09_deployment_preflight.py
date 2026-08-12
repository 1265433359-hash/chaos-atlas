from __future__ import annotations

from pathlib import Path

from tools.p09_deployment_preflight import build


def test_p09_requires_reduced_profile_env_and_digest_pinning() -> None:
    result = build()
    assert result["status"] == "blocked"
    assert result["runtime_apply_allowed"] is False
    assert "required_env_missing:docker/.env,docker/middleware.env" in result["reasons"]
    assert "api" in result["core_profile"]
    if result["compose_sha256"] is None:
        assert "source_missing:docker/docker-compose.yaml" in result["reasons"]
    else:
        assert "mutable_images_require_digest_pinning" in result["reasons"]


def test_p09_preflight_uses_verified_restored_source_when_frozen_source_is_incomplete(monkeypatch, tmp_path: Path) -> None:
    frozen = tmp_path / "sources" / "P09"
    restored = tmp_path / "sources_restored" / "P09"
    frozen.mkdir(parents=True)
    restored.mkdir(parents=True)
    (restored / "docker").mkdir()
    (restored / "docker" / "docker-compose.yaml").write_text(
        "services:\n  init-permissions:\n    image: busybox:latest\n  api:\n    image: dify:latest\n",
        encoding="utf-8",
    )

    import tools.p09_deployment_preflight as preflight

    monkeypatch.setattr(preflight, "PROJECT", frozen)
    monkeypatch.setattr(preflight, "RESTORED_PROJECT", restored)
    result = preflight.build()

    assert result["source_root"].endswith("sources_restored/P09")
    assert result["all_service_count"] == 2
    assert "mutable_images_require_digest_pinning" in result["reasons"]
    assert "core_profile_service_missing" in result["reasons"]
