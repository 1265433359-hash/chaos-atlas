"""Typed stopping and intensity planning for the experiment policy."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.experiment_policy import decision_confidence, score_experiment, select_next_experiment


def evaluate_stop(candidates: list[dict[str, Any]], states: dict[str, dict[str, Any]], context: dict[str, Any] | None = None) -> dict[str, Any]:
    context = context or {}
    confidence_threshold = float(context.get("resolved_confidence", 0.90))
    actionable = [candidate for candidate in candidates if candidate.get("status") != "blocked" and states.get(str(candidate.get("candidate_id")), {}).get("status") != "blocked"]
    if actionable and all(decision_confidence(states.get(str(candidate.get("candidate_id")), {}).get("posterior", {})) >= confidence_threshold for candidate in actionable):
        return {"stop_reason": "resolved", "next_candidate_id": None, "scores": []}
    if not actionable:
        return {"stop_reason": "blocked", "next_candidate_id": None, "scores": []}
    selected = select_next_experiment(candidates, states, context, budget=1)
    if selected is None or float(selected["value_per_cost"]) < float(context.get("minimum_value_per_cost", 0.05)):
        return {"stop_reason": "low_expected_value", "next_candidate_id": None, "scores": []}
    return {
        "stop_reason": None,
        "next_candidate_id": selected["candidate_id"],
        "scores": [selected],
    }


def plan_intensity_step(ladder: list[int | float], *, observed: list[int | float], boundary: int | float | None = None) -> dict[str, Any]:
    seen = {float(value) for value in observed}
    candidates = sorted(float(value) for value in ladder if float(value) not in seen and (boundary is None or float(value) <= float(boundary)))
    if not candidates:
        return {"next_value": None, "status": "exhausted"}
    value = candidates[0]
    return {"next_value": int(value) if value.is_integer() else value, "status": "planned"}
