"""Build fresh, secret-free inputs for the two-arm real-project experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

try:
    from tools.chaosatlas_two_arm_protocol import METHODS, PROJECTS, SEEDS, canonical_sha256
except ModuleNotFoundError:
    from chaosatlas_two_arm_protocol import METHODS, PROJECTS, SEEDS, canonical_sha256


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "artifacts/experiments/chaosatlas_two_arm_real_projects_2026-08-13"
FORBIDDEN_TERMS = ("candidate_id", "candidate_pool", "mutation_path", "runtime_observation", "post_run_rca", "oracle_label")


def _load_documents(path: Path) -> list[dict[str, Any]]:
    docs = [doc for doc in yaml.safe_load_all(path.read_text(encoding="utf-8-sig")) if doc is not None]
    if not docs or any(not isinstance(doc, dict) for doc in docs):
        raise ValueError(f"invalid Kubernetes manifest: {path}")
    return docs


def _metadata(doc: dict[str, Any]) -> dict[str, Any]:
    value = doc.get("metadata")
    return value if isinstance(value, dict) else {}


def _containers(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return (
        doc.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        if doc.get("kind") == "Deployment"
        else []
    )


def _topology(project_id: str, docs: list[dict[str, Any]]) -> dict[str, Any]:
    nodes = []
    edges = []
    deployments = {str(_metadata(doc).get("name")): doc for doc in docs if doc.get("kind") == "Deployment"}
    services = {str(_metadata(doc).get("name")): doc for doc in docs if doc.get("kind") == "Service"}
    for name, doc in sorted(deployments.items()):
        template = doc.get("spec", {}).get("template", {})
        template_metadata = template.get("metadata", {}) if isinstance(template, dict) else {}
        pod_labels = template_metadata.get("labels", {}) if isinstance(template_metadata, dict) else {}
        nodes.append({
            "id": f"workload/{name}",
            "role": "workload",
            "kind": str(doc.get("kind")),
            "name": name,
            "replicas": doc.get("spec", {}).get("replicas", 1),
            "pod_labels": {str(key): str(value) for key, value in pod_labels.items()},
        })
    for name, doc in sorted(services.items()):
        selector = doc.get("spec", {}).get("selector") or {}
        nodes.append({
            "id": f"service/{name}",
            "role": "routing",
            "kind": str(doc.get("kind")),
            "name": name,
            "selector": {str(key): str(value) for key, value in selector.items()},
        })
        matches = []
        for deployment_name, deployment in deployments.items():
            labels = deployment.get("spec", {}).get("template", {}).get("metadata", {}).get("labels", {})
            if all(labels.get(key) == value for key, value in selector.items()):
                matches.append(deployment_name)
        for deployment_name in matches:
            edges.append({"source": f"service/{name}", "target": f"workload/{deployment_name}", "kind": "selector_routes", "relation": "selects"})
    graph = {"project_id": project_id, "nodes": nodes, "edges": edges}
    return {**graph, "graph_hash": canonical_sha256(graph)}


def _image_provenance(docs: list[dict[str, Any]], image_overrides: dict[str, str] | None = None) -> dict[str, Any]:
    image_overrides = image_overrides or {}
    images: list[dict[str, Any]] = []
    for doc in docs:
        for container in _containers(doc):
            source_image = str(container.get("image", ""))
            image = str(image_overrides.get(source_image, source_image))
            images.append({
                "deployment": _metadata(doc).get("name"),
                "container": container.get("name"),
                "source_image": source_image,
                "image": image,
                "immutable": "@sha256:" in image,
            })
    blocked = [str(item["image"]) for item in images if not item["immutable"]]
    return {"images": images, "all_immutable": bool(images) and not blocked, "mutable_images": blocked}


def render_pinned_manifest(source_manifest_path: Path, image_overrides: dict[str, str] | None = None) -> str:
    docs = _load_documents(Path(source_manifest_path))
    image_overrides = image_overrides or {}
    for doc in docs:
        for container in _containers(doc):
            source_image = str(container.get("image", ""))
            if source_image in image_overrides:
                container["image"] = image_overrides[source_image]
    return yaml.safe_dump_all(docs, sort_keys=False, allow_unicode=False)


def render_deployable_manifest(source_manifest_path: Path, *, namespace: str, image_overrides: dict[str, str] | None = None) -> str:
    docs = _load_documents(Path(source_manifest_path))
    image_overrides = image_overrides or {}
    for doc in docs:
        metadata = _metadata(doc)
        if doc.get("kind") == "Namespace":
            metadata["name"] = namespace
        elif metadata:
            metadata["namespace"] = namespace
        for container in _containers(doc):
            source_image = str(container.get("image", ""))
            if source_image in image_overrides:
                container["image"] = image_overrides[source_image]
    return yaml.safe_dump_all(docs, sort_keys=False, allow_unicode=False)


def build_project_manifest(*, project_id: str, source_commit: str, source_manifest_path: Path, namespace: str, business_oracle: dict[str, Any], image_overrides: dict[str, str] | None = None) -> dict[str, Any]:
    if not project_id or not source_commit or len(source_commit) != 40:
        raise ValueError("project identity requires a 40-character source commit")
    if not namespace.startswith("chaosatlas-"):
        raise ValueError("runtime namespace must be project-local chaosatlas-* namespace")
    if not business_oracle.get("workflow") or not business_oracle.get("success"):
        raise ValueError("business oracle workflow and success condition are required")
    docs = _load_documents(Path(source_manifest_path))
    topology = _topology(project_id, docs)
    provenance = _image_provenance(docs, image_overrides=image_overrides)
    source_namespaces = sorted({str(_metadata(doc).get("namespace")) for doc in docs if _metadata(doc).get("namespace")})
    blocked: list[str] = []
    if not provenance["all_immutable"]:
        blocked.append("mutable_image")
    if any(ns == namespace for ns in source_namespaces):
        blocked.append("source_target_namespace_collision")
    if not topology["nodes"]:
        blocked.append("deployment_topology_empty")
    common = {
        "schema_version": "chaosatlas-two-arm-common-v1",
        "project_id": project_id,
        "project_commit": source_commit,
        "source_manifest_sha256": hashlib.sha256(Path(source_manifest_path).read_bytes()).hexdigest(),
        "namespace": namespace,
        "topology": topology,
        "business_oracle": business_oracle,
        "runtime_contract": {
            "fault_families": ["pod_kill", "network_delay", "network_loss", "container_cpu_stress"],
            "max_hypotheses": 8,
            "max_executed_hypotheses": 4,
            "repetitions": 2,
            "lifecycle": ["baseline", "inject", "observe", "recover", "cleanup", "washout"],
            "namespace_scope": namespace,
        },
        "image_provenance": provenance,
        "deployable_manifest_sha256": hashlib.sha256(render_deployable_manifest(source_manifest_path, namespace=namespace, image_overrides=image_overrides).encode("utf-8")).hexdigest(),
    }
    return {
        "schema_version": "chaosatlas-two-arm-project-manifest-v1",
        "project_id": project_id,
        "source_commit": source_commit,
        "namespace": namespace,
        "source_manifest_path": str(Path(source_manifest_path).resolve()),
        "source_namespaces": source_namespaces,
        "topology": topology,
        "image_provenance": provenance,
        "deployable_manifest": render_deployable_manifest(source_manifest_path, namespace=namespace, image_overrides=image_overrides),
        "oracle_contract": business_oracle,
        "common_input": common,
        "static_gate": {"status": "blocked" if blocked else "passed", "blocked_reasons": sorted(set(blocked))},
        "runtime": {"server_side_dry_run": "pending", "baseline_windows": "pending", "recovery_rehearsal": "pending", "runtime_ready": False},
        "human_review": "pending",
    }


def generic_knowledge_projection() -> dict[str, Any]:
    return {
        "schema_version": "chaosatlas-generic-knowledge-projection-v1",
        "human_review": "pending",
        "source_scope": "cross_project_generic_only",
        "facts": [
            {"pattern": "synchronous_downstream_call", "condition": "timeout_or_deadline_is_not_evidenced", "use": "prioritize bounded delay/loss hypothesis"},
            {"pattern": "single_replica_workload", "condition": "replica redundancy is not evidenced", "use": "prioritize bounded pod-kill hypothesis"},
            {"pattern": "defense_boundary", "condition": "timeout/retry/fallback is evidenced", "use": "retain protected hypothesis and validate behavior"},
        ],
        "projection_policy": "abstract patterns only; runtime evidence and target-project history excluded",
    }


def build_blocked_project_record(*, project_id: str, namespace: str, source_manifest_path: Path, blocked_reasons: list[str], source_commit: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": "chaosatlas-two-arm-blocked-project-v1",
        "project_id": project_id,
        "namespace": namespace,
        "source_manifest_path": str(Path(source_manifest_path).resolve()),
        "source_manifest_sha256": hashlib.sha256(Path(source_manifest_path).read_bytes()).hexdigest(),
        "source_commit": source_commit,
        "status": "blocked",
        "blocked_reasons": sorted(set(blocked_reasons)),
        "model_calls": False,
        "runtime_started": False,
        "human_review": "pending",
        "knowledge_base_updated": False,
    }


def build_bundle_pair(manifest: dict[str, Any], *, seed: int, knowledge: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if seed not in SEEDS:
        raise ValueError(f"seed is not registered: {seed}")
    common = manifest["common_input"]
    common_hash = canonical_sha256(common)
    shared = {"project_id": manifest["project_id"], "seed": seed, "common_input": common, "common_input_sha256": common_hash}
    full = {**shared, "method_id": "ChaosAtlas-full", "knowledge_view": knowledge}
    ablation = {**shared, "method_id": "ChaosAtlas-ablation", "knowledge_view": None}
    for bundle in (full, ablation):
        encoded = json.dumps(bundle, ensure_ascii=True).lower()
        if any(term in encoded for term in FORBIDDEN_TERMS):
            raise ValueError("forbidden runtime or candidate field in prompt-facing bundle")
    return full, ablation


def write_bundle_root(
    manifests: dict[str, dict[str, Any]],
    output_root: Path,
    knowledge: dict[str, Any],
    blocked_projects: dict[str, dict[str, Any]] | None = None,
    projects: tuple[str, ...] | list[str] | None = None,
) -> dict[str, Any]:
    output_root = Path(output_root)
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty directory: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    selected_projects = tuple(projects or PROJECTS)
    unknown_projects = sorted(set(selected_projects) - set(PROJECTS))
    if unknown_projects:
        raise ValueError(f"unknown projects: {unknown_projects}")
    missing_manifests = sorted(set(selected_projects) - set(manifests))
    if missing_manifests:
        raise ValueError(f"missing project manifests: {missing_manifests}")
    records = []
    blocked_projects = blocked_projects or {}
    for project_id in selected_projects:
        if project_id in blocked_projects:
            continue
        manifest = manifests[project_id]
        project_dir = output_root / "manifests" / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "manifest.json").write_text(json.dumps({key: value for key, value in manifest.items() if key != "common_input"}, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        (project_dir / "manifest.yaml").write_text(str(manifest["deployable_manifest"]), encoding="utf-8")
        for seed in SEEDS:
            seed_dir = output_root / "input_bundles" / project_id / f"seed-{seed}"
            seed_dir.mkdir(parents=True, exist_ok=True)
            full, ablation = build_bundle_pair(manifest, seed=seed, knowledge=knowledge)
            (seed_dir / "common.json").write_text(json.dumps(full["common_input"], indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
            prompt_header = (
                "ChaosAtlas two-arm discovery input. Return JSON only. "
                "Use only the supplied topology and frozen business oracle. "
                "Describe bounded fault hypotheses and validation intent; do not emit executable commands, historical identifiers, or post-run observations.\n\n"
            )
            for bundle in (full, ablation):
                filename = "chaosatlas-full.json" if bundle["method_id"] == "ChaosAtlas-full" else "chaosatlas-ablation.json"
                (seed_dir / filename).write_text(json.dumps(bundle, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
                prompt_name = filename.replace(".json", ".prompt.txt")
                (seed_dir / prompt_name).write_text(prompt_header + json.dumps(bundle, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
            records.append({"project_id": project_id, "seed": seed, "common_sha256": full["common_input_sha256"], "knowledge_review": knowledge["human_review"]})
    manifest = {"schema_version": "chaosatlas-two-arm-input-manifest-v1", "projects": list(selected_projects), "seeds": list(SEEDS), "methods": list(METHODS), "records": records, "blocked_projects": blocked_projects, "human_review": "pending", "model_calls": False, "runtime_started": False}
    (output_root / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    raise SystemExit("Use build_project_manifest and write_bundle_root with project-specific manifest paths; no implicit source selection is allowed.")


if __name__ == "__main__":
    main()
