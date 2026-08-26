"""Deterministic experiment-state and value-based selection primitives."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.causal_identity import causal_cluster_id, canonical_causal_identity
from tools.experiment_policy_schema import POLICY_VERSION, STATE_SCHEMA


def _input_hash(project_id: str, commit: str, seed: int, candidates: list[dict[str, Any]]) -> str:
    payload = {"project_id": project_id, "project_commit": commit, "seed": seed, "candidates": candidates}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def new_policy_state(project_id: str, project_commit: str, seed: int, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    rows: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id") or "")
        if not candidate_id:
            continue
        identity = canonical_causal_identity(candidate)
        rows[candidate_id] = {
            "causal_cluster_id": candidate.get("causal_cluster_id") or causal_cluster_id(candidate),
            "causal_identity": identity,
            "canonical_signature": candidate.get("canonical_signature"),
            "status": "blocked" if candidate.get("status") == "blocked" else "unknown",
            "posterior": {"weakness": 1 / 3, "protected": 1 / 3, "below_threshold": 1 / 3},
            "evidence_quality": "none",
            "run_count": 0,
            "observed_outcomes": [],
            "last_result_sha256": None,
        }
    return {
        "schema_version": STATE_SCHEMA,
        "policy_version": POLICY_VERSION,
        "project_id": project_id,
        "project_commit": project_commit,
        "seed": seed,
        "candidate_states": rows,
        "history": [],
        "input_sha256": _input_hash(project_id, project_commit, seed, candidates),
    }


def _normalize(values: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, float(value)) for value in values.values())
    if total <= 0:
        return {"weakness": 1 / 3, "protected": 1 / 3, "below_threshold": 1 / 3}
    return {key: max(0.0, float(value)) / total for key, value in values.items()}


def update_candidate_state(state: dict[str, Any], runtime_result: dict[str, Any]) -> dict[str, Any]:
    candidate_id = str(runtime_result.get("candidate_id") or "")
    row = state.get("candidate_states", {}).get(candidate_id)
    if not row:
        raise ValueError(f"unknown candidate_id: {candidate_id}")
    classification = str(runtime_result.get("classification") or "")
    mapping = {
        "confirmed_weakness": ("weakness", {"weakness": 0.85, "protected": 0.05, "below_threshold": 0.10}),
        "protected": ("defended", {"weakness": 0.05, "protected": 0.90, "below_threshold": 0.05}),
        "latent_risk": ("below_threshold", {"weakness": 0.20, "protected": 0.10, "below_threshold": 0.70}),
        "unsupported": ("unknown", {"weakness": 0.34, "protected": 0.16, "below_threshold": 0.50}),
        "environment_blocked": ("blocked", {"weakness": 1 / 3, "protected": 1 / 3, "below_threshold": 1 / 3}),
        "method_invalid": ("unknown", {"weakness": 1 / 3, "protected": 1 / 3, "below_threshold": 1 / 3}),
    }
    if classification not in mapping:
        raise ValueError(f"unsupported deterministic classification: {classification}")
    status, likelihood = mapping[classification]
    prior = row.get("posterior")
    if not isinstance(prior, dict):
        prior = {"weakness": 1 / 3, "protected": 1 / 3, "below_threshold": 1 / 3}
    # Treat each complete runtime result as another independent observation.
    # Multiplying the prior by the deterministic outcome likelihood makes
    # repeated evidence increase confidence instead of resetting it to the
    # same one-shot guess on every run.
    posterior = {
        key: max(0.0, float(prior.get(key, 0.0))) * max(0.0, float(likelihood.get(key, 0.0)))
        for key in ("weakness", "protected", "below_threshold")
    }
    row["status"] = status
    row["posterior"] = _normalize(posterior)
    row["run_count"] = int(row.get("run_count", 0)) + 1
    row["evidence_quality"] = str(runtime_result.get("evidence_quality") or "complete" if classification in {"confirmed_weakness", "protected"} else "partial")
    result_hash = runtime_result.get("result_sha256")
    row["last_result_sha256"] = result_hash
    row.setdefault("observed_outcomes", []).append({"classification": classification, "result_sha256": result_hash})
    state.setdefault("history", []).append({"candidate_id": candidate_id, "classification": classification, "result_sha256": result_hash})
    return state


def posterior_entropy(posterior: dict[str, float]) -> float:
    if not isinstance(posterior, dict):
        return float("inf")
    values = [float(posterior.get(key, 0.0)) for key in ("weakness", "protected", "below_threshold")]
    if any(not math.isfinite(value) or value < 0 for value in values):
        return float("inf")
    total = sum(values)
    if total <= 0:
        return float("inf")
    return -sum((value / total) * math.log2(value / total) for value in values if value > 0)


def decision_confidence(posterior: dict[str, float]) -> float:
    if not isinstance(posterior, dict):
        return 0.0
    values = [float(posterior.get(key, 0.0)) for key in ("weakness", "protected", "below_threshold")]
    return max(values) if values and all(math.isfinite(value) for value in values) else 0.0


def score_experiment(candidate: dict[str, Any], state: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    context = context or {}
    if candidate.get("status") == "blocked" or state.get("status") == "blocked":
        return {"candidate_id": candidate.get("candidate_id"), "value": float("-inf"), "value_per_cost": float("-inf"), "components": {"blocked": 1.0}}
    registry_bonus = 0.0
    registry_map = context.get("registry_priority_bonus")
    if isinstance(registry_map, dict):
        raw_bonus = registry_map.get(str(candidate.get("candidate_id")))
        cap = context.get("registry_priority_bonus_cap", 0.25)
        if isinstance(cap, (int, float)) and not isinstance(cap, bool) and math.isfinite(float(cap)) and float(cap) > 0:
            if isinstance(raw_bonus, (int, float)) and not isinstance(raw_bonus, bool) and math.isfinite(float(raw_bonus)):
                registry_bonus = min(float(cap), max(0.0, float(raw_bonus)))
    components = {
        "uncertainty_reduction": posterior_entropy(state.get("posterior") or {"weakness": 1 / 3, "protected": 1 / 3, "below_threshold": 1 / 3}),
        "decision_impact": float(candidate.get("decision_impact", 1.0)),
        "coverage_gain": 1.0 if candidate.get("causal_cluster_id") not in set(context.get("seen_cluster_ids") or set()) else 0.0,
        "boundary_proximity": 2.0 if str(candidate.get("candidate_id")) in set(context.get("boundary_candidate_ids") or set()) else 0.0,
        "transfer_value": float(candidate.get("transfer_value", 0.0)),
        "cost": max(0.1, float(candidate.get("estimated_cost", 1.0))),
        "blast_radius": max(0.0, float(candidate.get("blast_radius", 0.0))),
        "redundancy": min(2.0, float(state.get("run_count", 0)) * 0.5),
        "registry_priority_bonus": registry_bonus,
    }
    value = (
        components["uncertainty_reduction"]
        + components["decision_impact"]
        + components["coverage_gain"]
        + components["boundary_proximity"]
        + components["transfer_value"]
        + components["registry_priority_bonus"]
        - components["blast_radius"]
        - components["redundancy"]
    )
    return {
        "candidate_id": candidate.get("candidate_id"),
        "value": value,
        "value_per_cost": value / components["cost"],
        "components": components,
    }


def select_next_experiment(candidates: list[dict[str, Any]], states: dict[str, dict[str, Any]], context: dict[str, Any] | None = None, budget: int = 1) -> dict[str, Any] | None:
    scored = [score_experiment(candidate, states.get(str(candidate.get("candidate_id")), {}), context) for candidate in candidates]
    scored = [item for item in scored if math.isfinite(float(item["value_per_cost"]))]
    scored.sort(key=lambda item: (-float(item["value_per_cost"]), str(item.get("candidate_id"))))
    if not scored or budget <= 0:
        return None
    return scored[0]
