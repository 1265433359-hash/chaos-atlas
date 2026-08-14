"""Offline contamination gate for the three-method experiment.

The gate treats runtime results as audit-only data.  Only an explicitly
reviewed, hashed abstraction from an earlier project may enter the full
ChaosAtlas method.  The ablation and ChaosEater methods are always isolated
from that projection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "artifacts/experiments/chaosatlas_10_projects"
PROJECT_ORDER = [f"P{i:02d}" for i in range(1, 11)]
FULL_METHODS = {"ChaosAtlas-full", "ChaosAtlas-KB-open"}
ABLATION_METHODS = {"ChaosAtlas-ablation", "ChaosAtlas-noKB-open"}
CHAOSEATER_METHODS = {"ChaosEater-full", "ChaosEater-official", "ChaosEater-open", "ChaosEater-adapter-open"}
FORBIDDEN_RUNTIME_FIELDS = {
    "evidence", "oracle", "oracle_label", "oracle_verdict", "runtime_observation",
    "post_run_rca", "rca", "mutation", "mutation_path", "candidate_mutation_path",
    "final_verdict", "classification", "result", "outcome", "selected_by_", "prior_method",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    """Hash a JSON value using the protocol's canonical serialization."""
    return hashlib.sha256(_canonical(value)).hexdigest()


def _walk(value: Any, path: str = "") -> Iterable[tuple[str, str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            yield child_path, str(key), child
            yield from _walk(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]")


def _project_number(project: str) -> int | None:
    if project in PROJECT_ORDER:
        return PROJECT_ORDER.index(project)
    return None


def _target_commit(bundle: dict[str, Any]) -> str:
    return str(bundle.get("project_commit") or (bundle.get("common_input") or {}).get("project_commit") or "")


def _knowledge_content(bundle: dict[str, Any]) -> dict[str, Any] | None:
    view = bundle.get("knowledge_view")
    if not view:
        return None
    if isinstance(view, dict) and isinstance(view.get("content"), dict):
        return view["content"]
    return view if isinstance(view, dict) else None


def _runtime_field_hits(value: Any) -> list[str]:
    hits: list[str] = []
    for path, key, _ in _walk(value):
        lowered = key.lower()
        if lowered in FORBIDDEN_RUNTIME_FIELDS or any(lowered.startswith(prefix) for prefix in ("selected_by_", "prior_method")):
            hits.append(path)
    return sorted(set(hits))


def audit_bundle(bundle: dict[str, Any], prompt_text: str = "") -> dict[str, Any]:
    """Audit one prompt bundle without consulting runtime artifacts."""
    errors: list[str] = []
    project = str(bundle.get("project_id", ""))
    arm = str(bundle.get("arm") or bundle.get("target_method") or "")
    knowledge = _knowledge_content(bundle)
    source_project = str((knowledge or {}).get("source_project_id") or "")
    source_round = str((knowledge or {}).get("source_round_id") or "")
    source_commit = str((knowledge or {}).get("source_project_commit") or (knowledge or {}).get("project_commit") or "")
    target_commit = _target_commit(bundle)
    runtime_hits = _runtime_field_hits((knowledge or {}).get("abstraction", knowledge or {}))
    runtime_hits.extend(_runtime_field_hits(bundle.get("prompt_facing_projection") or {}))
    if runtime_hits:
        errors.extend(f"forbidden_runtime_field:{hit}" for hit in sorted(set(runtime_hits)))

    if arm in ABLATION_METHODS and knowledge is not None:
        errors.append("knowledge_view_forbidden_for_ablation")
    if arm in CHAOSEATER_METHODS and knowledge is not None:
        errors.append("knowledge_view_forbidden_for_chaoseater")
    if source_project == project and source_round:
        errors.append("same_project_runtime_feedback")
    source_index = _project_number(source_project)
    target_index = _project_number(project)
    future_blocked = bool(source_index is not None and target_index is not None and source_index >= target_index and source_round)
    if future_blocked:
        errors.append("future_project_feedback")
    # The prompt contract itself names forbidden fields to instruct the model.
    # Audit supplied structured views only; scanning the contract text would be
    # a deterministic false positive.

    return {
        "valid": not errors,
        "errors": sorted(set(errors)),
        "source_project": source_project or None,
        "target_project": project or None,
        "target_method": arm or None,
        "feedback_round": source_round or None,
        "source_commit": source_commit or None,
        "target_commit": target_commit or None,
        "forbidden_runtime_fields": sorted(set(runtime_hits)),
        "same_project_blocked": "same_project_runtime_feedback" in errors,
        "future_project_blocked": "future_project_feedback" in errors,
        "ablation_isolated": arm in ABLATION_METHODS and knowledge is None,
        "chaoseater_isolated": arm in CHAOSEATER_METHODS and knowledge is None,
    }


def _projection_without_hash(projection: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in projection.items() if key != "projection_sha256"}


def audit_feedback_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Validate a reviewed cross-project feedback manifest."""
    errors: list[str] = []
    target = str(manifest.get("target_project", ""))
    method = str(manifest.get("target_method", ""))
    round_id = str(manifest.get("feedback_round", ""))
    order = [str(item) for item in (manifest.get("project_order") or [])]
    target_index = order.index(target) if target in order else None
    if target_index is None:
        errors.append("target_project_order_missing")
    if not round_id:
        errors.append("feedback_round_required")
    if method in ABLATION_METHODS or method in CHAOSEATER_METHODS:
        errors.append("feedback_forbidden_for_method")
    if method not in FULL_METHODS:
        errors.append("unknown_target_method")
    review = manifest.get("human_review") or {}
    if review.get("status") != "approved":
        errors.append("human_review_required")

    projections = manifest.get("projections") or []
    for projection in projections:
        source = str(projection.get("source_project_id", ""))
        source_index = order.index(source) if source in order else None
        if source_index is None:
            errors.append("source_project_order_missing")
        elif target_index is not None and source_index >= target_index:
            errors.append("future_or_same_project_feedback")
        if str(projection.get("source_round_id", "")) != round_id:
            errors.append("round_mismatch")
        actual_hash = str(projection.get("projection_sha256", ""))
        if actual_hash != canonical_sha256(_projection_without_hash(projection)):
            errors.append("projection_hash_mismatch")
        for hit in _runtime_field_hits(projection.get("abstraction") or {}):
            errors.append(f"forbidden_runtime_field:abstraction.{hit}")
        if not projection.get("source_project_commit"):
            errors.append("source_commit_required")
    return {
        "valid": not errors,
        "errors": sorted(set(errors)),
        "source_project": ",".join(sorted({str(p.get("source_project_id")) for p in projections})) or None,
        "target_project": target or None,
        "target_method": method or None,
        "feedback_round": round_id or None,
        "source_commit": next((p.get("source_project_commit") for p in projections if p.get("source_project_commit")), None),
        "target_commit": manifest.get("target_commit"),
        "projection_hash": [p.get("projection_sha256") for p in projections],
        "forbidden_runtime_fields": sorted({hit.split(":", 1)[1] for hit in errors if hit.startswith("forbidden_runtime_field:")}),
        "same_project_blocked": "future_or_same_project_feedback" in errors,
        "future_project_blocked": "future_or_same_project_feedback" in errors,
        "ablation_isolated": method in ABLATION_METHODS and not projections,
        "chaoseater_isolated": method in CHAOSEATER_METHODS and not projections,
    }


def audit_repository(root: Path = EXPERIMENT) -> dict[str, Any]:
    root = root.resolve()
    records: list[dict[str, Any]] = []
    for bundle_path in sorted((root / "open_discovery_bundles").glob("P*/seed-*/**/*.json")):
        if bundle_path.name == "manifest.json":
            continue
        prompt_path = bundle_path.with_suffix(".prompt.txt")
        try:
            bundle = json.loads(bundle_path.read_text(encoding="utf-8-sig"))
            prompt = prompt_path.read_text(encoding="utf-8-sig") if prompt_path.exists() else ""
            record = audit_bundle(bundle, prompt)
            record["bundle"] = str(bundle_path.relative_to(ROOT.resolve())).replace("\\", "/")
        except (OSError, json.JSONDecodeError) as exc:
            record = {"valid": False, "errors": [f"load_error:{exc}"], "bundle": str(bundle_path)}
        records.append(record)
    return {
        "schema_version": "1.0",
        "status": "pass" if all(item["valid"] for item in records) else "blocked",
        "bundle_count": len(records),
        "records": records,
        "no_model_calls": True,
        "no_cluster_mutations": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=EXPERIMENT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit_repository(args.root)
    text = json.dumps(result, indent=2, ensure_ascii=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
