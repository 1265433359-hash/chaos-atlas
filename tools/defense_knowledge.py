"""Promote repeated, independently captured runtime defense evidence.

This module consumes immutable ChaosAtlas run directories. It does not execute
faults and does not infer source-level mechanisms; promotion is limited to the
deployment-boundary defense claim already emitted by the live classifier.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from tools.compile_rca_regression import compile_regression_intents
from tools.rca_loop import _contains_sensitive_value, evaluate_knowledge_promotion


def _load_payload(root: Path, name: str) -> dict[str, Any]:
    value = json.loads((root / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{root / name} must contain an object")
    payload = value.get("payload", value)
    if not isinstance(payload, dict):
        raise ValueError(f"{root / name} payload must contain an object")
    return payload


def _validate_run(root: Path) -> dict[str, Any]:
    classification = _load_payload(root, "classify.json")
    observation = _load_payload(root, "observe.json").get("observation") or {}
    cleanup = _load_payload(root, "cleanup_report.json")
    manifest = _load_payload(root, "run_manifest.json")
    inventory = _load_payload(root, "inventory.json") if (root / "inventory.json").is_file() else {}
    defense = classification.get("defense_evidence")
    attestation = classification.get("attestation")
    if classification.get("result") != "availability_defended":
        raise ValueError(f"{root}: defense result is not availability_defended")
    if not isinstance(defense, dict) or not defense.get("claim_type"):
        raise ValueError(f"{root}: defense claim evidence is missing")
    if not isinstance(attestation, dict) or not all(attestation.get(field) is True for field in ("baseline", "injection", "observation", "recovery", "cleanup", "independent_oracle")):
        raise ValueError(f"{root}: lifecycle attestation is incomplete")
    if observation.get("status") != "pass" or not observation.get("samples"):
        raise ValueError(f"{root}: business observation window is incomplete")
    if cleanup.get("status") != "verified" or cleanup.get("errors"):
        raise ValueError(f"{root}: cleanup is not verified")
    return {
        "root": str(root),
        "claim_type": str(defense["claim_type"]),
        "defense_evidence": defense,
        "evidence_refs": list(classification.get("evidence_refs") or []),
        "run_id": str(manifest.get("run_id") or root.name),
        "run_fingerprint": hashlib.sha256((root / "classify.json").read_bytes()).hexdigest(),
        "project_id": str(inventory.get("project_id") or manifest.get("project_id") or "sock-shop"),
        "project_commit": str(inventory.get("project_commit") or manifest.get("project_commit") or "runtime-unknown"),
        "target": str(defense.get("target") or "front-end"),
    }


def promote_repeated_defense(*, run_roots: list[Path], output_root: Path) -> dict[str, Any]:
    """Promote two independent defended runs to a local reusable card."""

    roots = [Path(root) for root in run_roots]
    if len(roots) < 2:
        raise ValueError("defense promotion requires at least two independent runs")
    if len({root.resolve() for root in roots}) != len(roots):
        raise ValueError("defense promotion requires distinct run roots")
    runs = [_validate_run(root) for root in roots]
    if len({run["run_fingerprint"] for run in runs}) != len(runs):
        raise ValueError("defense promotion requires independent run artifacts")
    claim_types = {run["claim_type"] for run in runs}
    if len(claim_types) != 1:
        raise ValueError("defense runs must use the same claim_type")
    projects = {(run["project_id"], run["project_commit"]) for run in runs}
    if len(projects) != 1:
        raise ValueError("defense runs must target the same project revision")
    claim_type = runs[0]["claim_type"]
    project_id, project_commit = next(iter(projects))
    target = runs[0]["target"]
    card_id = "KB-DEF-" + hashlib.sha256(f"{project_id}:{project_commit}:{target}:{claim_type}".encode("utf-8")).hexdigest()[:16]
    promotion = evaluate_knowledge_promotion(
        current="provisional",
        weakness_status="protected",
        rca_status="bounded",
        valid_reproductions=len(runs),
        valid_counterfactuals=0,
        lifecycle_complete=True,
        direct_evidence=True,
        applicability_complete=True,
        regression_complete=True,
        contradiction=False,
    )
    if not promotion.get("allowed") or promotion.get("next_status") != "local_reusable":
        raise ValueError(f"defense promotion gate rejected evidence: {promotion}")
    card = {
        "schema_version": "chaosatlas-defense-knowledge-v1",
        "id": card_id,
        "project": project_id,
        "project_commit": project_commit,
        "target": target,
        "test_node": {"target": target, "target_kind": "deployment", "family": "pod_kill", "operation": "pod_kill"},
        "weakness_status": "protected",
        "rca_status": "bounded",
        "knowledge_status": "local_reusable",
        "classification": "protected",
        "defense_claim_type": claim_type,
        "mechanism_level": "deployment_boundary",
        "applicability_conditions": ["same project and commit", "target deployment has at least two Ready replicas"],
        "exclusion_conditions": ["does not prove an application-internal timeout, retry or fallback mechanism", "single-replica deployments are not covered"],
        "evidence_runs": [
            {
                "run_id": run["run_id"],
                "run_fingerprint": run["run_fingerprint"],
                "root": run["root"],
                "evidence_refs": run["evidence_refs"],
                "defense_evidence": run["defense_evidence"],
            }
            for run in runs
        ],
        "valid_reproductions": len(runs),
        "counter_evidence": [],
        "promotion_audit": promotion,
        "next_evidence": ["repeat_defense_oracle", "verify_replica_count_before_injection"],
        "stop_rule": "stop after two valid defensive reproductions or one counterexample",
        "regression_recipe": {"oracle": "project business oracle", "selected_next_action": None},
    }
    snapshot = {"card": card, "run_ids": [run["run_id"] for run in runs]}
    regression = compile_regression_intents([card], snapshot=snapshot)
    card["regression_intents"] = regression["intents"]
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    for name, value in (("defense_card.json", card), (f"{card_id}.json", card), ("regression_intents.json", regression)):
        text = json.dumps(value, indent=2, ensure_ascii=True) + "\n"
        if _contains_sensitive_value(text):
            raise ValueError(f"refusing to write sensitive defense artifact: {name}")
        (output_root / name).write_text(text, encoding="utf-8")
    return {"status": "promoted", **card, "regression": regression}
