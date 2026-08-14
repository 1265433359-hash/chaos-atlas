from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from tools.prepare_p03_p06_runtime_profiles import build_profile, write_profile


def _images(project_id: str) -> dict[str, str]:
    if project_id == "P03":
        return {
            "saleor": "chaosatlas/p03-saleor@sha256:" + "a" * 64,
            "db": "postgres@sha256:" + "b" * 64,
            "cache": "valkey@sha256:" + "c" * 64,
        }
    return {
        "directus": "chaosatlas/p06-directus@sha256:" + "d" * 64,
        "postgres": "postgres@sha256:" + "e" * 64,
    }


@pytest.mark.parametrize("project_id", ["P03", "P06"])
def test_profile_requires_source_built_application_digest(project_id: str) -> None:
    with pytest.raises(ValueError, match="application image digest"):
        build_profile(project_id, {})


@pytest.mark.parametrize("project_id", ["P03", "P06"])
def test_profile_emits_bounded_namespace_local_resources(project_id: str, tmp_path: Path) -> None:
    profile = build_profile(project_id, _images(project_id))
    assert profile["project_id"] == project_id
    assert profile["namespace"] == f"chaosatlas-{project_id.lower()}"
    assert profile["static_gate"]["status"] == "passed"
    assert profile["runtime_apply_allowed"] is False

    docs = list(yaml.safe_load_all(profile["yaml"]))
    assert all(doc["metadata"].get("namespace") == profile["namespace"] for doc in docs if doc["kind"] != "Namespace")
    deployments = [doc for doc in docs if doc["kind"] == "Deployment"]
    assert deployments
    for deployment in deployments:
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        assert "@sha256:" in container["image"]
        assert container["resources"]["requests"]
        assert container["resources"]["limits"]
        assert container["readinessProbe"]
        assert container["livenessProbe"]

    output = write_profile(profile, tmp_path / f"{project_id}-r4")
    assert (output / "static-profile.yaml").is_file()
    manifest = json.loads((output / "profile-manifest.json").read_text(encoding="utf-8"))
    assert manifest["runtime_apply_allowed"] is False
    assert manifest["server_side_dry_run"] == "pending_authorized_cluster_session"


def test_profile_rejects_mutable_image() -> None:
    images = _images("P06")
    images["directus"] = "chaosatlas/p06-directus:local"
    with pytest.raises(ValueError, match="immutable digest"):
        build_profile("P06", images)


@pytest.mark.parametrize("project_id", ["P03", "P06"])
def test_profile_does_not_embed_example_passwords(project_id: str) -> None:
    profile = build_profile(project_id, _images(project_id))
    secrets = [doc for doc in yaml.safe_load_all(profile["yaml"]) if doc["kind"] == "Secret"]
    assert secrets
    assert all(value == "REPLACE_BEFORE_APPLY" for doc in secrets for value in doc["stringData"].values())
