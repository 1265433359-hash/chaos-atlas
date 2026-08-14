"""Build frozen three-arm input envelopes for full-v1, full-v2, and ablation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


SEEDS = (1001, 1002, 1003)
METHODS = ("ChaosAtlas-full-v1", "ChaosAtlas-full-v2", "ChaosAtlas-ablation")
FORBIDDEN_TERMS = (
    "candidate_id",
    "candidate_pool",
    "mutation_path",
    "runtime_observation",
    "post_run_rca",
    "oracle_label",
)


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_full_v1_projection() -> dict[str, Any]:
    """Return the frozen v1 projection with the same review contract as v2."""
    try:
        from tools.build_two_arm_real_project_inputs import generic_knowledge_projection
    except ModuleNotFoundError:
        from build_two_arm_real_project_inputs import generic_knowledge_projection

    projection = dict(generic_knowledge_projection())
    projection["knowledge_base_updated"] = False
    projection["projection_sha256"] = _canonical_sha256(projection)
    return projection


def _validate_projection(projection: dict[str, Any], expected_version: str) -> None:
    if projection.get("schema_version") != expected_version:
        raise ValueError(f"projection schema must be {expected_version}")
    if projection.get("human_review") != "pending":
        raise ValueError("projection human_review must remain pending")
    if projection.get("knowledge_base_updated") is not False:
        raise ValueError("projection knowledge_base_updated must remain false")
    if not projection.get("projection_sha256"):
        raise ValueError("projection hash is required")


def build_three_arm_bundle_set(
    manifest: dict[str, Any],
    *,
    seed: int,
    full_v1: dict[str, Any],
    full_v2: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    if seed not in SEEDS:
        raise ValueError(f"seed is not registered: {seed}")
    _validate_projection(full_v1, "chaosatlas-generic-knowledge-projection-v1")
    _validate_projection(full_v2, "chaosatlas-generic-knowledge-projection-v2")
    common = manifest.get("common_input")
    project_id = manifest.get("project_id")
    if not isinstance(common, dict) or not project_id:
        raise ValueError("manifest requires project_id and common_input")
    common_hash = _canonical_sha256(common)
    shared = {
        "project_id": project_id,
        "seed": seed,
        "common_input": common,
        "common_input_sha256": common_hash,
    }
    bundles = {
        "ChaosAtlas-full-v1": {**shared, "method_id": "ChaosAtlas-full-v1", "knowledge_view": full_v1},
        "ChaosAtlas-full-v2": {**shared, "method_id": "ChaosAtlas-full-v2", "knowledge_view": full_v2},
        "ChaosAtlas-ablation": {**shared, "method_id": "ChaosAtlas-ablation", "knowledge_view": None},
    }
    for bundle in bundles.values():
        encoded = json.dumps(bundle, ensure_ascii=True).lower()
        if any(term in encoded for term in FORBIDDEN_TERMS):
            raise ValueError("three-arm bundle contains forbidden runtime or candidate field")
    return bundles


def write_three_arm_bundle_root(
    manifests: dict[str, dict[str, Any]],
    output_root: Path,
    *,
    full_v1: dict[str, Any],
    full_v2: dict[str, Any] | None = None,
    full_v2_by_project: dict[str, dict[str, Any]] | None = None,
    projects: tuple[str, ...] | list[str] | None = None,
) -> dict[str, Any]:
    """Write a non-empty-safe, prompt-facing three-arm input tree."""
    output_root = Path(output_root)
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"refusing non-empty directory: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    selected_projects = tuple(projects or sorted(manifests))
    missing = sorted(set(selected_projects) - set(manifests))
    if missing:
        raise ValueError(f"missing project manifests: {missing}")
    if full_v2 is None and full_v2_by_project is None:
        raise ValueError("full_v2 or full_v2_by_project is required")
    if full_v2_by_project is not None:
        missing_projection = sorted(set(selected_projects) - set(full_v2_by_project))
        if missing_projection:
            raise ValueError(f"missing full_v2 projections: {missing_projection}")

    records: list[dict[str, Any]] = []
    for project_id in selected_projects:
        manifest = manifests[project_id]
        project_full_v2 = full_v2_by_project[project_id] if full_v2_by_project is not None else full_v2
        if project_full_v2 is None:
            raise ValueError(f"missing full_v2 projection: {project_id}")
        common = manifest.get("common_input")
        if not isinstance(common, dict):
            raise ValueError(f"manifest has no common_input: {project_id}")
        project_dir = output_root / "manifests" / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        project_record = {key: value for key, value in manifest.items() if key != "common_input"}
        (project_dir / "manifest.json").write_text(
            json.dumps(project_record, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        if "deployable_manifest" in manifest:
            (project_dir / "manifest.yaml").write_text(
                str(manifest["deployable_manifest"]),
                encoding="utf-8",
            )

        for seed in SEEDS:
            bundles = build_three_arm_bundle_set(
                manifest,
                seed=seed,
                full_v1=full_v1,
                full_v2=project_full_v2,
            )
            seed_dir = output_root / "input_bundles" / project_id / f"seed-{seed}"
            seed_dir.mkdir(parents=True, exist_ok=True)
            (seed_dir / "common.json").write_text(
                json.dumps(common, indent=2, ensure_ascii=True) + "\n",
                encoding="utf-8",
            )
            prompt_header = (
                "ChaosAtlas three-arm discovery input. Return JSON only. "
                "Use only the supplied topology, frozen business oracle, and "
                "method knowledge view. Describe bounded fault hypotheses and "
                "validation intent; do not emit executable commands, historical "
                "identifiers, or post-run observations.\n\n"
            )
            for method_id, bundle in bundles.items():
                filename = {
                    "ChaosAtlas-full-v1": "chaosatlas-full-v1.json",
                    "ChaosAtlas-full-v2": "chaosatlas-full-v2.json",
                    "ChaosAtlas-ablation": "chaosatlas-ablation.json",
                }[method_id]
                (seed_dir / filename).write_text(
                    json.dumps(bundle, indent=2, ensure_ascii=True) + "\n",
                    encoding="utf-8",
                )
                (seed_dir / filename.replace(".json", ".prompt.txt")).write_text(
                    prompt_header + json.dumps(bundle, indent=2, ensure_ascii=True) + "\n",
                    encoding="utf-8",
                )
            records.append({
                "project_id": project_id,
                "seed": seed,
                "common_sha256": bundles["ChaosAtlas-full-v1"]["common_input_sha256"],
                "full_v1_projection_sha256": full_v1["projection_sha256"],
                "full_v2_projection_sha256": project_full_v2["projection_sha256"],
            })

    result = {
        "schema_version": "chaosatlas-three-arm-input-manifest-v1",
        "projects": list(selected_projects),
        "seeds": list(SEEDS),
        "methods": list(METHODS),
        "records": records,
        "human_review": "pending",
        "model_calls": False,
        "runtime_started": False,
        "knowledge_base_updated": False,
    }
    (output_root / "manifest.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return result
