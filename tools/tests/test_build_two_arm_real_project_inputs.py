from __future__ import annotations

import json
from pathlib import Path

import yaml

from tools.build_two_arm_real_project_inputs import (
    build_bundle_pair,
    build_project_manifest,
    build_blocked_project_record,
    generic_knowledge_projection,
    render_pinned_manifest,
    render_deployable_manifest,
    write_bundle_root,
)


def source_manifest(tmp_path: Path) -> Path:
    path = tmp_path / "manifest.yaml"
    docs = [
        {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "source-lab"}},
        {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "api", "namespace": "source-lab", "labels": {"app": "api"}}, "spec": {"replicas": 1, "selector": {"matchLabels": {"app": "api"}}, "template": {"metadata": {"labels": {"app": "api"}}, "spec": {"containers": [{"name": "api", "image": "example/api@sha256:" + "a" * 64}]}}}},
        {"apiVersion": "v1", "kind": "Service", "metadata": {"name": "api", "namespace": "source-lab"}, "spec": {"selector": {"app": "api"}, "ports": [{"port": 80}]}},
    ]
    path.write_text(yaml.safe_dump_all(docs, sort_keys=False), encoding="utf-8")
    return path


def test_project_manifest_requires_namespace_and_business_oracle(tmp_path: Path) -> None:
    manifest = build_project_manifest(
        project_id="demo",
        source_commit="a" * 40,
        source_manifest_path=source_manifest(tmp_path),
        namespace="chaosatlas-demo",
        business_oracle={"workflow": "GET /", "success": "HTTP 200"},
    )
    assert manifest["project_id"] == "demo"
    assert manifest["namespace"] == "chaosatlas-demo"
    assert manifest["oracle_contract"]["workflow"] == "GET /"
    assert manifest["topology"]["nodes"]
    assert manifest["image_provenance"]["all_immutable"] is True


def test_topology_preserves_workload_identity_and_selector(tmp_path: Path) -> None:
    manifest = build_project_manifest(
        project_id="demo",
        source_commit="a" * 40,
        source_manifest_path=source_manifest(tmp_path),
        namespace="chaosatlas-demo",
        business_oracle={"workflow": "GET /", "success": "HTTP 200"},
    )
    nodes = {node["id"]: node for node in manifest["topology"]["nodes"]}

    assert nodes["workload/api"] == {
        "id": "workload/api",
        "role": "workload",
        "kind": "Deployment",
        "name": "api",
        "replicas": 1,
        "pod_labels": {"app": "api"},
    }
    assert nodes["service/api"] == {
        "id": "service/api",
        "role": "routing",
        "kind": "Service",
        "name": "api",
        "selector": {"app": "api"},
    }
    assert {"source": "service/api", "target": "workload/api", "kind": "selector_routes", "relation": "selects"} in manifest["topology"]["edges"]


def test_bundle_pair_is_shared_except_knowledge_view(tmp_path: Path) -> None:
    manifest = build_project_manifest(
        project_id="demo",
        source_commit="a" * 40,
        source_manifest_path=source_manifest(tmp_path),
        namespace="chaosatlas-demo",
        business_oracle={"workflow": "GET /", "success": "HTTP 200"},
    )
    knowledge = generic_knowledge_projection()
    full, ablation = build_bundle_pair(manifest, seed=1001, knowledge=knowledge)
    assert full["knowledge_view"]["human_review"] == "pending"
    assert ablation["knowledge_view"] is None
    assert full["common_input"] == ablation["common_input"]
    assert full["common_input_sha256"] == ablation["common_input_sha256"]
    assert "mutation_path" not in json.dumps(full, ensure_ascii=True)
    assert "candidate_id" not in json.dumps(full, ensure_ascii=True)


def test_mutable_image_blocks_project_manifest(tmp_path: Path) -> None:
    path = source_manifest(tmp_path)
    text = path.read_text(encoding="utf-8").replace("@sha256:" + "a" * 64, ":latest")
    path.write_text(text, encoding="utf-8")
    manifest = build_project_manifest(
        project_id="demo",
        source_commit="a" * 40,
        source_manifest_path=path,
        namespace="chaosatlas-demo",
        business_oracle={"workflow": "GET /", "success": "HTTP 200"},
    )
    assert manifest["static_gate"]["status"] == "blocked"
    assert "mutable_image" in manifest["static_gate"]["blocked_reasons"]


def test_explicit_image_overrides_create_immutable_runtime_manifest(tmp_path: Path) -> None:
    path = source_manifest(tmp_path)
    manifest = build_project_manifest(
        project_id="demo",
        source_commit="a" * 40,
        source_manifest_path=path,
        namespace="chaosatlas-demo",
        business_oracle={"workflow": "GET /", "success": "HTTP 200"},
        image_overrides={"example/api@sha256:" + "a" * 64: "registry.example/api@sha256:" + "b" * 64},
    )
    assert manifest["image_provenance"]["all_immutable"] is True
    assert manifest["static_gate"]["status"] == "passed"


def test_blocked_project_record_preserves_unprovenance_without_fake_commit() -> None:
    record = build_blocked_project_record(
        project_id="sock-shop",
        namespace="chaosatlas-sock-shop",
        source_manifest_path=Path("artifacts/sock-shop/sock-shop-lab-manifest.yaml"),
        blocked_reasons=["source_commit_not_proven"],
    )
    assert record["status"] == "blocked"
    assert record["source_commit"] is None
    assert record["model_calls"] is False


def test_prompt_instructions_do_not_trip_input_contamination_scan(tmp_path: Path) -> None:
    manifest = build_project_manifest(
        project_id="demo",
        source_commit="a" * 40,
        source_manifest_path=source_manifest(tmp_path),
        namespace="chaosatlas-demo",
        business_oracle={"workflow": "GET /", "success": "HTTP 200"},
    )
    output = tmp_path / "bundles"
    write_bundle_root(
        {"online-boutique": manifest, "opentelemetry-demo": manifest, "sock-shop": manifest},
        output,
        generic_knowledge_projection(),
    )
    prompt = (output / "input_bundles" / "online-boutique" / "seed-1001" / "chaosatlas-full.prompt.txt").read_text(encoding="utf-8")
    assert "mutation_path" not in prompt
    assert "candidate_id" not in prompt


def test_render_pinned_manifest_replaces_deployable_image_references(tmp_path: Path) -> None:
    source = source_manifest(tmp_path)
    rendered = render_pinned_manifest(
        source,
        {"example/api@sha256:" + "a" * 64: "registry.example/api@sha256:" + "b" * 64},
    )
    assert "registry.example/api@sha256:" + "b" * 64 in rendered
    assert "example/api@sha256:" + "a" * 64 not in rendered


def test_render_deployable_manifest_is_namespace_local(tmp_path: Path) -> None:
    source = source_manifest(tmp_path)
    rendered = render_deployable_manifest(
        source,
        namespace="chaosatlas-demo",
        image_overrides={"example/api@sha256:" + "a" * 64: "registry.example/api@sha256:" + "b" * 64},
    )
    assert "name: chaosatlas-demo" in rendered
    assert "namespace: chaosatlas-demo" in rendered
    assert "name: source-lab" not in rendered
    assert "namespace: source-lab" not in rendered


def test_written_project_manifest_contains_deployable_yaml(tmp_path: Path) -> None:
    manifest = build_project_manifest(
        project_id="demo",
        source_commit="a" * 40,
        source_manifest_path=source_manifest(tmp_path),
        namespace="chaosatlas-demo",
        business_oracle={"workflow": "GET /", "success": "HTTP 200"},
    )
    output = tmp_path / "bundles"
    write_bundle_root(
        {"online-boutique": manifest, "opentelemetry-demo": manifest, "sock-shop": manifest},
        output,
        generic_knowledge_projection(),
    )
    assert (output / "manifests" / "online-boutique" / "manifest.yaml").is_file()


def test_written_bundle_root_can_be_limited_to_one_project(tmp_path: Path) -> None:
    manifest = build_project_manifest(
        project_id="demo",
        source_commit="a" * 40,
        source_manifest_path=source_manifest(tmp_path),
        namespace="chaosatlas-demo",
        business_oracle={"workflow": "GET /", "success": "HTTP 200"},
    )
    output = tmp_path / "otel-only"
    result = write_bundle_root(
        {"opentelemetry-demo": manifest},
        output,
        generic_knowledge_projection(),
        projects=("opentelemetry-demo",),
    )

    assert result["projects"] == ["opentelemetry-demo"]
    assert (output / "input_bundles" / "opentelemetry-demo" / "seed-1001" / "chaosatlas-full.json").is_file()
    assert not (output / "input_bundles" / "online-boutique").exists()
