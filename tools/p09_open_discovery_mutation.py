"""Compile frozen P09 discovery hypotheses into auditable Chaos Mesh mutations."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from tools.open_discovery_mutation_compiler import MutationCompileError, compile_mutation


NAMESPACE = "chaosatlas-p09"
PROJECT_ID = "P09"


class P09MutationCompileError(ValueError):
    """Fail-closed P09 mutation compilation error."""


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _validate_identity(hypothesis: dict[str, Any]) -> None:
    if hypothesis.get("project_id") != PROJECT_ID:
        raise P09MutationCompileError("hypothesis project_id must be P09")
    if hypothesis.get("namespace") != NAMESPACE:
        raise P09MutationCompileError(
            "hypothesis namespace must be chaosatlas-p09"
        )


def _write_result(
    hypothesis: dict[str, Any],
    provenance: dict[str, Any],
    yaml_text: str,
    output_dir: Path,
) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise P09MutationCompileError(
            "refusing to write into non-empty output directory"
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    document = yaml.safe_load(yaml_text)
    name = str(document["metadata"]["name"])
    mutation_path = output_dir / f"{name}.yaml"
    provenance_path = output_dir / f"{name}.provenance.json"
    mutation_hash = _sha256(yaml_text.encode("utf-8"))

    enriched = {
        **provenance,
        "project_id": PROJECT_ID,
        "namespace": NAMESPACE,
        "yaml_path": str(mutation_path).replace("\\", "/"),
        "yaml_sha256": mutation_hash,
        "human_review": "pending",
        "execution_ready": False,
    }
    mutation_path.write_bytes(yaml_text.encode("utf-8"))
    provenance_path.write_text(
        json.dumps(enriched, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "unified-mutation-v1",
        "project_id": PROJECT_ID,
        "namespace": NAMESPACE,
        "candidate_or_hypothesis_id": hypothesis.get("hypothesis_id"),
        "mutation_path": str(mutation_path).replace("\\", "/"),
        "provenance_path": str(provenance_path).replace("\\", "/"),
        "mutation_sha256": mutation_hash,
        "execution_ready": False,
        "human_review": "pending",
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return {
        "yaml": yaml_text,
        "provenance": enriched,
        "manifest": manifest,
        "mutation_path": mutation_path,
        "provenance_path": provenance_path,
    }


def compile_p09_hypothesis(
    hypothesis: dict[str, Any],
    topology: dict[str, Any],
    runtime_map: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    """Compile one accepted P09 hypothesis and optionally materialize evidence."""

    if not isinstance(hypothesis, dict):
        raise P09MutationCompileError("hypothesis must be an object")
    _validate_identity(hypothesis)
    if not isinstance(runtime_map, dict) or not runtime_map.get("targets"):
        raise P09MutationCompileError("P09 runtime mapping is required")
    try:
        provenance, yaml_text = compile_mutation(
            hypothesis,
            topology,
            runtime_map,
        )
    except (MutationCompileError, KeyError, TypeError, ValueError) as exc:
        raise P09MutationCompileError(str(exc)) from exc
    return _write_result(hypothesis, provenance, yaml_text, output_dir)


def runtime_map_from_profile(profile_path: Path) -> dict[str, Any]:
    """Build a namespace-local target map from a reviewed P09 profile."""

    try:
        documents = list(
            yaml.safe_load_all(profile_path.read_text(encoding="utf-8"))
        )
    except OSError as exc:
        raise P09MutationCompileError(f"profile cannot be read: {exc}") from exc

    targets: dict[str, Any] = {}
    aliases = {
        "init-permissions": "init_permissions",
        "worker-beat": "worker_beat",
        "postgres": "db_postgres",
    }
    for document in documents:
        if not isinstance(document, dict):
            continue
        if document.get("kind") not in {"Deployment", "StatefulSet"}:
            continue
        metadata = document.get("metadata") or {}
        if metadata.get("namespace") != NAMESPACE:
            continue
        name = str(metadata.get("name") or "")
        template_labels = (
            document.get("spec", {})
            .get("template", {})
            .get("metadata", {})
            .get("labels", {})
        )
        if not name or not isinstance(template_labels, dict):
            continue
        target_name = aliases.get(name, name.replace("-", "_"))
        targets[f"compose/service/{target_name}"] = {
            "namespace": NAMESPACE,
            "workload": {
                "kind": str(document.get("kind")),
                "name": name,
            },
            "selector": {
                str(key): str(value)
                for key, value in template_labels.items()
                if str(key).strip() and value is not None
            },
        }
    if not targets:
        raise P09MutationCompileError(
            "profile yielded no namespace-local runtime mapping"
        )
    return {"targets": targets}


def compile_frozen_discovery_results(
    results_root: Path,
    topology: dict[str, Any],
    runtime_map: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    """Materialize unique mutations from frozen P09 discovery result files."""

    if output_dir.exists() and any(output_dir.iterdir()):
        raise P09MutationCompileError(
            "refusing to write into non-empty output directory"
        )
    result_paths = sorted(results_root.rglob("result.json"))
    hypotheses: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[str] = set()

    for result_path in result_paths:
        try:
            result = json.loads(result_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            rejected.append({"path": str(result_path), "reason": str(exc)})
            continue
        if result.get("project_id") not in (None, PROJECT_ID):
            continue
        if result.get("status") != "valid":
            continue
        accepted = ((result.get("compiled") or {}).get("accepted") or [])
        for hypothesis in accepted:
            if not isinstance(hypothesis, dict):
                rejected.append(
                    {"path": str(result_path), "reason": "accepted hypothesis is not an object"}
                )
                continue
            signature = str(hypothesis.get("canonical_signature") or "")
            if not signature:
                rejected.append(
                    {"path": str(result_path), "reason": "missing canonical signature"}
                )
                continue
            if signature in seen:
                continue
            seen.add(signature)
            hypotheses.append(hypothesis)

    output_dir.mkdir(parents=True, exist_ok=True)
    generated: list[dict[str, Any]] = []
    for index, hypothesis in enumerate(hypotheses, start=1):
        mutation_dir = output_dir / f"mutation-{index:03d}"
        try:
            result = compile_p09_hypothesis(
                hypothesis=hypothesis,
                topology=topology,
                runtime_map=runtime_map,
                output_dir=mutation_dir,
            )
            generated.append(
                {
                    "index": index,
                    "hypothesis_id": hypothesis.get("hypothesis_id"),
                    "canonical_signature": hypothesis.get("canonical_signature"),
                    "mutation_path": result["manifest"]["mutation_path"],
                    "provenance_path": result["manifest"]["provenance_path"],
                    "mutation_sha256": result["manifest"]["mutation_sha256"],
                    "execution_ready": False,
                }
            )
        except P09MutationCompileError as exc:
            rejected.append(
                {
                    "hypothesis_id": hypothesis.get("hypothesis_id"),
                    "canonical_signature": hypothesis.get("canonical_signature"),
                    "reason": str(exc),
                }
            )

    summary = {
        "schema_version": "unified-discovery-mutation-v1",
        "project_id": PROJECT_ID,
        "namespace": NAMESPACE,
        "status": "completed" if not rejected else "completed_with_rejections",
        "source_result_count": len(result_paths),
        "unique_hypotheses": len(hypotheses),
        "generated_mutations": len(generated),
        "rejected_count": len(rejected),
        "execution_ready_count": 0,
        "human_review": "pending",
        "knowledge_base_updated": False,
        "generated": generated,
        "rejected": rejected,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return summary
