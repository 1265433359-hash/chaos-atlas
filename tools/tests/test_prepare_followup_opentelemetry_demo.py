from __future__ import annotations

import json
from pathlib import Path

import yaml

from tools.prepare_followup_opentelemetry_demo import (
    TARGET_NAMESPACE,
    build_fresh_manifest,
    write_preparation,
)


def _source_files(tmp_path: Path) -> tuple[Path, Path, Path]:
    documents = [
        {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {"name": "otel-demo-lab"},
        },
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"namespace": "otel-demo-lab", "name": "checkout"},
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": "checkout",
                                "image": "ghcr.io/open-telemetry/demo:3.0.0-checkout",
                                "env": [
                                    {
                                        "name": "CHECKOUT_PORT",
                                        "value": "5050",
                                    }
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
            "metadata": {"namespace": "otel-demo-lab", "name": "checkout"},
            "spec": {"ports": [{"port": 5050, "targetPort": 5050}]},
        },
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"namespace": "otel-demo-lab", "name": "cart"},
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": "cart",
                                "image": "ghcr.io/open-telemetry/demo:3.0.0-cart",
                                "env": [
                                    {
                                        "name": "ASPNETCORE_URLS",
                                        "value": "http://*:7070",
                                    }
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
            "metadata": {"namespace": "otel-demo-lab", "name": "cart"},
            "spec": {"ports": [{"port": 7070, "targetPort": 7070}]},
        },
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"namespace": "otel-demo-lab", "name": "postgres"},
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": "postgres",
                                "image": "postgres:18.4",
                                "env": [
                                    {
                                        "name": "POSTGRES_PASSWORD",
                                        "value": "astronomy_password",
                                    }
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
            "metadata": {"namespace": "otel-demo-lab", "name": "postgres"},
            "spec": {"ports": [{"port": 5432, "targetPort": 5432}]},
        },
    ]
    source = tmp_path / "source.yaml"
    source.write_text(
        "\n---\n".join(yaml.safe_dump(doc, sort_keys=False) for doc in documents),
        encoding="utf-8",
    )
    init_sql = tmp_path / "init.sql"
    init_sql.write_text("CREATE SCHEMA catalog;\n", encoding="utf-8")
    flagd = tmp_path / "demo.flagd.json"
    flagd.write_text(json.dumps({"flags": {}}) + "\n", encoding="utf-8")
    return source, init_sql, flagd


def test_build_fresh_manifest_rewrites_namespace_materializes_configmaps_and_scrubs_password(
    tmp_path: Path,
) -> None:
    source, init_sql, flagd = _source_files(tmp_path)

    result = build_fresh_manifest(source, init_sql=init_sql, flagd_config=flagd)

    assert result["project_id"] == "opentelemetry-demo"
    assert result["static_gate"]["namespace_local"] is True
    assert result["static_gate"]["configmaps_present"] is True
    assert result["oracle_contract"]["workflow"] == "AddItem_then_PlaceOrder"
    assert result["trace_backend"]["status"] == "recorded_unavailable"
    assert "astronomy_password" not in result["manifest_yaml"]
    assert "CHAOSATLAS_OTEL_DB_PASSWORD_PLACEHOLDER" in result["manifest_yaml"]
    docs = list(yaml.safe_load_all(result["manifest_yaml"]))
    assert docs[0]["metadata"]["name"] == TARGET_NAMESPACE
    assert {
        doc["metadata"]["name"]
        for doc in docs
        if doc.get("kind") == "ConfigMap"
    } == {"postgres-init", "flagd-config"}
    assert all(
        doc.get("metadata", {}).get("namespace") in {None, TARGET_NAMESPACE}
        for doc in docs
    )


def test_build_fresh_manifest_blocks_mutable_images(tmp_path: Path) -> None:
    source, init_sql, flagd = _source_files(tmp_path)

    result = build_fresh_manifest(source, init_sql=init_sql, flagd_config=flagd)

    assert result["image_provenance"]["status"] == "pending_digest_resolution"
    assert result["static_gate"]["status"] == "blocked"
    assert "immutable_image_provenance_missing" in result["static_gate"]["blocked_reasons"]
    assert result["runtime"]["runtime_apply_allowed"] is False


def test_build_fresh_manifest_accepts_explicit_registry_replacements(tmp_path: Path) -> None:
    source, init_sql, flagd = _source_files(tmp_path)
    image_digests = {
        "ghcr.io/open-telemetry/demo:3.0.0-checkout": (
            "docker.io/otel/demo@sha256:" + "1" * 64
        ),
        "ghcr.io/open-telemetry/demo:3.0.0-cart": (
            "docker.io/otel/demo@sha256:" + "2" * 64
        ),
        "postgres:18.4": "docker.io/library/postgres@sha256:" + "3" * 64,
    }

    result = build_fresh_manifest(
        source,
        init_sql=init_sql,
        flagd_config=flagd,
        image_digests=image_digests,
    )

    assert "immutable_image_provenance_missing" not in result["static_gate"]["blocked_reasons"]
    assert "ghcr.io/open-telemetry/demo:3.0.0-checkout" not in result["manifest_yaml"]
    assert "docker.io/otel/demo@sha256:" + "1" * 64 in result["manifest_yaml"]
    assert result["image_provenance"]["status"] == "verified_manifest_digests"


def test_cli_loads_image_digest_mapping(tmp_path: Path) -> None:
    from tools.prepare_followup_opentelemetry_demo import load_image_digests

    path = tmp_path / "digests.json"
    path.write_text(
        json.dumps(
            {
                "images": [
                    {
                        "source": "ghcr.io/open-telemetry/demo:3.0.0-checkout",
                        "pinned": "docker.io/otel/demo@sha256:" + "a" * 64,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert load_image_digests(path) == {
        "ghcr.io/open-telemetry/demo:3.0.0-checkout": (
            "docker.io/otel/demo@sha256:" + "a" * 64
        )
    }


def test_write_preparation_refuses_nonempty_directory_and_preserves_hash(
    tmp_path: Path,
) -> None:
    source, init_sql, flagd = _source_files(tmp_path)
    result = build_fresh_manifest(source, init_sql=init_sql, flagd_config=flagd)
    output = tmp_path / "profile"
    output.mkdir()
    (output / "existing.txt").write_text("keep\n", encoding="utf-8")

    try:
        write_preparation(result, output)
    except FileExistsError:
        pass
    else:
        raise AssertionError("non-empty preparation directory was overwritten")

    assert (output / "existing.txt").read_text(encoding="utf-8") == "keep\n"

    fresh_output = write_preparation(result, tmp_path / "fresh-profile")
    manifest = (fresh_output / "manifest.yaml").read_bytes()
    recorded = json.loads(
        (fresh_output / "fresh-manifest.json").read_text(encoding="utf-8")
    )
    import hashlib

    assert hashlib.sha256(manifest).hexdigest() == recorded["input"]["manifest_sha256"]
