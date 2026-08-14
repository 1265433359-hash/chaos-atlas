from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from tools.prepare_followup_train_ticket import (
    TARGET_NAMESPACE,
    build_fresh_manifest,
    write_preparation,
)


def _source_files(tmp_path: Path) -> list[Path]:
    docs = [
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "ts-station-service"},
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": "station",
                                "image": "codewisdom/ts-station-service:1.0.1",
                                "envFrom": [
                                    {"secretRef": {"name": "ts-station-mysql"}},
                                    {"configMapRef": {"name": "nacos"}},
                                ],
                            }
                        ]
                    }
                }
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": "ts-station-service"},
            "spec": {"ports": [{"port": 12345, "targetPort": 12345}]},
        },
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "nacos"},
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": "nacos",
                                "image": "nacos/nacos-server:2.0.1",
                            }
                        ]
                    }
                }
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": "nacos"},
            "spec": {"ports": [{"port": 8848, "targetPort": 8848}]},
        },
    ]
    first = tmp_path / "first.yaml"
    second = tmp_path / "second.yaml"
    first.write_text(
        "\n---\n".join(yaml.safe_dump(doc, sort_keys=False) for doc in docs[:2]),
        encoding="utf-8",
    )
    second.write_text(
        "\n---\n".join(yaml.safe_dump(doc, sort_keys=False) for doc in docs[1:]),
        encoding="utf-8",
    )
    return [first, second]


def test_build_fresh_manifest_deduplicates_rewrites_namespace_and_records_oracles(
    tmp_path: Path,
) -> None:
    sources = _source_files(tmp_path)

    result = build_fresh_manifest(sources)

    assert result["project_id"] == "train-ticket"
    assert result["static_gate"]["namespace_local"] is True
    assert result["oracle_contract"]["success"]["path"].endswith("/shanghai")
    assert result["oracle_contract"]["not_found"]["expected_body"]["msg"] == "Not exists"
    docs = list(yaml.safe_load_all(result["manifest_yaml"]))
    identities = [
        (doc["kind"], doc["metadata"]["name"])
        for doc in docs
    ]
    assert len(identities) == len(set(identities))
    assert all(
        doc.get("metadata", {}).get("namespace") in {None, TARGET_NAMESPACE}
        for doc in docs
    )
    assert any(
        doc["kind"] == "Namespace"
        and doc["metadata"]["name"] == TARGET_NAMESPACE
        for doc in docs
    )


def test_build_fresh_manifest_fails_closed_for_missing_dependencies_and_mutable_images(
    tmp_path: Path,
) -> None:
    result = build_fresh_manifest(_source_files(tmp_path))

    assert result["static_gate"]["status"] == "blocked"
    assert "required_dependency_resources_missing" in result["static_gate"]["blocked_reasons"]
    assert "immutable_image_provenance_missing" in result["static_gate"]["blocked_reasons"]
    assert result["image_provenance"]["status"] == "pending_digest_resolution"
    assert result["runtime"]["runtime_apply_allowed"] is False


def test_write_preparation_preserves_hash_and_refuses_overwrite(tmp_path: Path) -> None:
    result = build_fresh_manifest(_source_files(tmp_path))
    output = tmp_path / "profile"
    output.mkdir()
    (output / "existing.txt").write_text("keep\n", encoding="utf-8")

    try:
        write_preparation(result, output)
    except FileExistsError:
        pass
    else:
        raise AssertionError("non-empty preparation directory was overwritten")

    fresh_output = write_preparation(result, tmp_path / "fresh-profile")
    manifest = (fresh_output / "manifest.yaml").read_bytes()
    recorded = json.loads(
        (fresh_output / "fresh-manifest.json").read_text(encoding="utf-8")
    )
    assert hashlib.sha256(manifest).hexdigest() == recorded["input"]["manifest_sha256"]


def test_write_preparation_emits_image_provenance_sidecar(tmp_path: Path) -> None:
    result = build_fresh_manifest(_source_files(tmp_path))

    output = write_preparation(result, tmp_path / "profile-with-provenance")

    provenance = json.loads(
        (output / "image-provenance.json").read_text(encoding="utf-8")
    )
    assert provenance["status"] == "pending_digest_resolution"
    assert provenance["runtime_apply_allowed"] is False
    assert "codewisdom/ts-station-service:1.0.1" in provenance["image_references"]
