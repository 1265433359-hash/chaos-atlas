"""Convert deterministic policy decisions into the existing candidate contract."""

from __future__ import annotations

import math
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.experiment_policy import score_experiment
from tools.experiment_policy_schema import validate_policy_state
from tools.stop_policy import evaluate_stop


MODES = {"legacy", "observe", "shadow", "guarded", "default"}
SCHEMA = "chaosatlas-policy-selection-gate-v1"


def _candidate_ids(candidates: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError("candidate must be an object")
        candidate_id = str(candidate.get("candidate_id") or "")
        if not candidate_id:
            raise ValueError("candidate_id is required")
        if candidate_id in ids:
            raise ValueError(f"duplicate candidate_id: {candidate_id}")
        ids.append(candidate_id)
    return ids


def _legacy_ids(candidates: list[dict[str, Any]], budget: int) -> list[str]:
    return _candidate_ids(candidates)[:budget]


def _policy_scores(
    candidates: list[dict[str, Any]],
    state: dict[str, Any],
    context: dict[str, Any],
    budget: int,
) -> list[dict[str, Any]]:
    states = state.get("candidate_states") or {}
    scored = [
        score_experiment(candidate, states.get(str(candidate.get("candidate_id")), {}), context)
        for candidate in candidates
    ]
    scored = [item for item in scored if math.isfinite(float(item.get("value_per_cost", float("-inf"))))]
    scored.sort(key=lambda item: (-float(item["value_per_cost"]), str(item.get("candidate_id"))))
    minimum = float(context.get("minimum_value_per_cost", 0.05))
    return [item for item in scored if float(item["value_per_cost"]) >= minimum][:budget]


def select_candidates_with_policy(
    candidates: list[dict[str, Any]],
    policy_state: dict[str, Any],
    *,
    mode: str = "legacy",
    budget: int = 1,
    legacy_budget: int | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply policy selection while preserving the main runner's candidate contract.

    ``legacy`` and ``shadow`` retain the existing execution IDs. ``guarded`` and
    ``default`` execute only policy-selected IDs that are present in the frozen
    candidate list. Any policy failure falls back to the bounded legacy prefix.
    """
    if mode not in MODES:
        raise ValueError(f"unsupported policy mode: {mode}")
    if isinstance(budget, bool) or int(budget) < 1:
        raise ValueError("policy budget must be a positive integer")
    budget = int(budget)
    if legacy_budget is None:
        legacy_budget = budget
    if isinstance(legacy_budget, bool) or int(legacy_budget) < 1:
        raise ValueError("legacy budget must be a positive integer")
    legacy_budget = int(legacy_budget)
    context = dict(context or {})
    ids = _candidate_ids(candidates)
    legacy_ids = ids[:legacy_budget]
    result: dict[str, Any] = {
        "schema_version": SCHEMA,
        "policy_mode": mode,
        "legacy_candidate_ids": legacy_ids,
        "policy_selected_candidate_ids": [],
        "execution_candidate_ids": legacy_ids,
        "decision_changed": False,
        "stop_reason": None,
        "scores": [],
        "fallback_used": False,
        "fallback_reason": None,
        "policy_error": None,
        "policy_context": deepcopy(context),
    }
    if mode == "legacy":
        return result

    try:
        validation = validate_policy_state(policy_state)
        if not validation["valid"]:
            raise ValueError("invalid policy state: " + ",".join(validation["errors"]))
        states = policy_state.get("candidate_states") or {}
        missing = [candidate_id for candidate_id in ids if candidate_id not in states]
        if missing:
            raise ValueError("policy state missing candidates: " + ",".join(missing))
        stop = evaluate_stop(candidates, states, context)
        result["stop_reason"] = stop.get("stop_reason")
        if stop.get("stop_reason") is None:
            scores = _policy_scores(candidates, policy_state, context, budget)
            selected_ids = [str(item.get("candidate_id")) for item in scores]
            allowed = set(ids)
            if any(candidate_id not in allowed for candidate_id in selected_ids):
                raise ValueError("policy selected candidate outside frozen candidate list")
            result["scores"] = scores
            result["policy_selected_candidate_ids"] = selected_ids
            if mode in {"guarded", "default"}:
                result["execution_candidate_ids"] = selected_ids
        result["decision_changed"] = result["policy_selected_candidate_ids"] != legacy_ids
        return result
    except Exception as exc:
        result["fallback_used"] = True
        result["fallback_reason"] = "policy_error"
        result["policy_error"] = f"{type(exc).__name__}: {exc}"
        result["stop_reason"] = None
        return result
