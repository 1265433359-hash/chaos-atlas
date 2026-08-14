from __future__ import annotations

import json
from pathlib import Path

import yaml

from tools.prepare_followup_online_boutique import (
    TARGET_NAMESPACE,
    build_fresh_manifest,
    pin_fresh_manifest,
    pin_manifest_images,
    write_preparation,
)


def _source_manifest(tmp_path: Path, *, include_loadgenerator: bool = False) -> Path:
    docs = [
        {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {"name": "online-boutique-lab"},
        },
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "namespace": "online-boutique-lab",
                "name": "frontend",
            },
            "spec": {
                "template": {
                    "spec": {
                        "containers": [{"name": "server", "image": "frontend:lab"}]
                    }
                }
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "namespace": "online-boutique-lab",
                "name": "frontend",
            },
            "spec": {"ports": [{"port": 80}]},
        },
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "namespace": "online-boutique-lab",
                "name": "checkoutservice",
            },
            "spec": {
                "template": {
                    "spec": {
                        "containers": [{"name": "server", "image": "checkout:lab"}]
                    }
                }
            },
        },
    ]
    if include_loadgenerator:
        docs.append(
            {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {
                    "namespace": "online-boutique-lab",
                    "name": "loadgenerator",
                },
                "spec": {"template": {"spec": {"containers": []}}},
            }
        )
    path = tmp_path / "source.yaml"
    path.write_text(
        "\n---\n".join(yaml.safe_dump(doc, sort_keys=False) for doc in docs),
        encoding="utf-8",
    )
    return path


def test_build_fresh_manifest_rewrites_namespace_and_keeps_business_services(tmp_path: Path) -> None:
    source = _source_manifest(tmp_path)

    result = build_fresh_manifest(source)

    assert result["static_gate"]["status"] == "passed"
    assert result["static_gate"]["loadgenerator_absent"] is True
    assert result["oracle_contract"]["frontend"]["path"] == "/_healthz"
    assert result["oracle_contract"]["place_order"]["workflow"] == "AddItem_then_PlaceOrder"
    assert result["input"]["source_namespace"] == "online-boutique-lab"
    assert result["input"]["target_namespace"] == TARGET_NAMESPACE
    docs = list(yaml.safe_load_all(result["manifest_yaml"]))
    assert docs[0]["metadata"]["name"] == TARGET_NAMESPACE
    assert all(
        doc.get("metadata", {}).get("namespace") in {None, TARGET_NAMESPACE}
        for doc in docs
    )
    assert {doc["metadata"]["name"] for doc in docs if doc["kind"] == "Deployment"} == {
        "frontend",
        "checkoutservice",
    }


def test_build_fresh_manifest_rejects_loadgenerator(tmp_path: Path) -> None:
    source = _source_manifest(tmp_path, include_loadgenerator=True)

    result = build_fresh_manifest(source)

    assert result["static_gate"]["status"] == "blocked"
    assert "loadgenerator_present" in result["static_gate"]["blocked_reasons"]


def test_write_preparation_refuses_nonempty_directory(tmp_path: Path) -> None:
    source = _source_manifest(tmp_path)
    result = build_fresh_manifest(source)
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


def test_write_preparation_preserves_manifest_sha256(tmp_path: Path) -> None:
    source = _source_manifest(tmp_path)
    result = build_fresh_manifest(source)
    output = write_preparation(result, tmp_path / "profile")

    manifest = (output / "manifest.yaml").read_bytes()
    recorded = json.loads((output / "fresh-manifest.json").read_text(encoding="utf-8"))

    import hashlib

    assert hashlib.sha256(manifest).hexdigest() == recorded["input"]["manifest_sha256"]


def test_pin_manifest_images_rewrites_every_image_to_immutable_reference() -> None:
    manifest = """
apiVersion: apps/v1
kind: Deployment
metadata:
  namespace: chaosatlas-online-boutique
  name: frontend
spec:
  template:
    spec:
      containers:
      - name: server
        image: online-boutique-lab/frontend:lab
---
apiVersion: apps/v1
kind: Deployment
metadata:
  namespace: chaosatlas-online-boutique
  name: redis-cart
spec:
  template:
    spec:
      containers:
      - name: redis
        image: redis:alpine
"""
    pinned, records = pin_manifest_images(
        manifest,
        {
            "online-boutique-lab/frontend:lab": (
                "us-central1-docker.pkg.dev/google-samples/"
                "microservices-demo/frontend@sha256:frontend"
            ),
            "redis:alpine": "docker.io/library/redis@sha256:redis",
        },
    )

    assert "image: us-central1-docker.pkg.dev/google-samples/microservices-demo/frontend@sha256:frontend" in pinned
    assert "image: docker.io/library/redis@sha256:redis" in pinned
    assert {record["source"] for record in records} == {
        "online-boutique-lab/frontend:lab",
        "redis:alpine",
    }
    assert all(record["pinned"].count("@sha256:") == 1 for record in records)


def test_pin_manifest_images_fails_closed_for_missing_or_mutable_digest() -> None:
    manifest = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
spec:
  template:
    spec:
      containers:
      - name: server
        image: online-boutique-lab/frontend:lab
"""

    try:
        pin_manifest_images(manifest, {})
    except ValueError as exc:
        assert "missing immutable digest" in str(exc)
    else:
        raise AssertionError("missing image digest was accepted")


def test_pin_fresh_manifest_updates_hash_and_provenance(tmp_path: Path) -> None:
    result = build_fresh_manifest(_source_manifest(tmp_path))
    original_hash = result["input"]["manifest_sha256"]
    pinned = pin_fresh_manifest(
        result,
        {
            "frontend:lab": "registry.example/frontend@sha256:frontend",
            "checkout:lab": "registry.example/checkout@sha256:checkout",
        },
        provenance_source="minikube-local-repodigest",
    )

    assert pinned is result
    assert pinned["input"]["unpinned_manifest_sha256"] == original_hash
    assert pinned["input"]["manifest_sha256"] != original_hash
    assert pinned["image_provenance"]["status"] == "verified_local_repo_digests"
    assert pinned["image_provenance"]["provenance_source"] == "minikube-local-repodigest"
    assert pinned["runtime"]["runtime_apply_allowed"] is False
