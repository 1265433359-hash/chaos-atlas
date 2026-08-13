from __future__ import annotations

import importlib.util
from pathlib import Path

from tools.p09_deployment_preflight import build


GENERATOR_PATH = Path(__file__).resolve().parents[2] / (
    "artifacts/experiments/chaosatlas_10_projects/runtime_profiles/P09/"
    "generate_minimal_profile.py"
)


def load_generator():
    spec = importlib.util.spec_from_file_location("p09_minimal_profile_generator", GENERATOR_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    monkeypatch.setattr(preflight, "RESTORED_PROJECT_R2", tmp_path / "missing-r2")
    result = preflight.build()

    assert result["source_root"].endswith("sources_restored/P09")
    assert result["all_service_count"] == 2
    assert "mutable_images_require_digest_pinning" in result["reasons"]
    assert "core_profile_service_missing" in result["reasons"]


def test_p09_profile_validator_accepts_explicit_profile_and_output(monkeypatch, tmp_path: Path) -> None:
    import tools.p09_profile_validator as validator

    profile = tmp_path / "minimal-profile.yaml"
    output = tmp_path / "profile-preflight.json"
    profile.write_text(
        """apiVersion: v1
kind: Namespace
metadata:
  name: chaosatlas-p09
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: chaosatlas-p09
spec:
  template:
    spec:
      containers:
          - name: api
            image: example/api@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: worker
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: worker-beat
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: web
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: postgres
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: redis
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: init-permissions
""",
        encoding="utf-8",
    )
    assert validator.run(profile, output) == 0
    assert output.exists()


def test_p09_runtime_profile_uses_valid_local_config_and_postgres_entrypoint() -> None:
    generator = load_generator()
    config = generator.env_config()
    assert config["CODE_EXECUTION_ENDPOINT"] == "http://127.0.0.1:8194"
    assert config["PLUGIN_REMOTE_INSTALL_PORT"] == "5003"

    digests = {
        name: f"example/{name}@sha256:{'a' * 64}"
        for name in ("busybox", "dify-api", "dify-web", "postgres", "redis")
    }
    postgres = next(doc for doc in generator.generate(digests) if doc.get("kind") == "Deployment" and doc["metadata"]["name"] == "postgres")
    container = postgres["spec"]["template"]["spec"]["containers"][0]
    assert "command" not in container
    assert not any(doc.get("kind") == "Secret" for doc in generator.generate(digests))
