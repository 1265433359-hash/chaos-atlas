"""Project-agnostic adaptive budget accounting.

The planner treats a budget as remaining required work, not a hard-coded
number of candidates. Candidate-specific adapters provide states; this module
only reasons about baseline coverage, triggered parameter variants, and
reproduction confirmations.
"""

from __future__ import annotations

from typing import Any


BASELINE_LEVELS = {"baseline", "default"}


def _level(candidate: dict[str, Any]) -> str:
    return str(candidate.get("parameter_level") or "baseline").strip().lower()


def _cluster(candidate: dict[str, Any]) -> str:
    return str(candidate.get("causal_cluster_id") or candidate.get("candidate_id") or "")


def _cost(candidate: dict[str, Any]) -> float:
    value = candidate.get("estimated_cost", candidate.get("cost_units", 1.0))
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = 1.0
    return max(0.0, parsed)


def _parameter_audit_config(config: dict[str, Any] | None) -> dict[str, Any]:
    value = config if isinstance(config, dict) else {}
    enabled = value.get("enabled") is True
    try:
        minimum = int(value.get("min_levels_per_cluster", 1))
    except (TypeError, ValueError):
        minimum = 1
    preferred = value.get("preferred_levels")
    if not isinstance(preferred, list):
        preferred = ["low", "medium", "high", "boundary"]
    preferred_levels = [str(item).strip().lower() for item in preferred if str(item).strip()]
    return {
        "enabled": enabled,
        "min_levels_per_cluster": max(0, minimum),
        "preferred_levels": preferred_levels or ["low", "medium", "high", "boundary"],
    }


def adaptive_budget_snapshot(
    candidates: list[dict[str, Any]],
    candidate_states: dict[str, dict[str, Any]],
    rows: list[dict[str, Any]],
    *,
    stable_repetitions: int = 3,
    parameter_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calculate the current remaining work for an adaptive test run.

    The returned unique budget is a moving ceiling: it includes all currently
    required untested baseline candidates and parameter variants whose
    baseline has triggered escalation. New anomalies can increase the ceiling
    on the next decision; clean results do not.
    """

    if stable_repetitions < 1:
        raise ValueError("stable_repetitions must be positive")
    unique_history = {
        str(row.get("candidate_id") or "")
        for row in rows
        if str(row.get("candidate_id") or "")
        and row.get("status") == "live_completed"
        and row.get("cleanup_status") == "verified"
    }
    baselines = [item for item in candidates if _level(item) in BASELINE_LEVELS]
    parameters = [item for item in candidates if _level(item) not in BASELINE_LEVELS]
    baseline_by_cluster: dict[str, dict[str, Any]] = {}
    for candidate in baselines:
        baseline_by_cluster[_cluster(candidate)] = candidate

    untested_baselines = [
        item for item in baselines
        if not (candidate_states.get(str(item.get("candidate_id") or ""), {}).get("valid_trials") or 0)
        and not candidate_states.get(str(item.get("candidate_id") or ""), {}).get("environment_blocked")
    ]
    triggered_clusters = {
        cluster_id
        for cluster_id, baseline in baseline_by_cluster.items()
        if (
            candidate_states.get(str(baseline.get("candidate_id") or ""), {}).get("anomaly_trials")
            or candidate_states.get(str(baseline.get("candidate_id") or ""), {}).get("near_boundary_trials")
        )
    }
    triggered_parameters = [
        item for item in parameters
        if _cluster(item) in triggered_clusters
        and not (candidate_states.get(str(item.get("candidate_id") or ""), {}).get("valid_trials") or 0)
        and not candidate_states.get(str(item.get("candidate_id") or ""), {}).get("environment_blocked")
        and candidate_states.get(str(item.get("candidate_id") or ""), {}).get("experience_disposition") != "deferred_by_experience"
    ]
    audit_config = _parameter_audit_config(parameter_audit)
    audit_parameters: list[dict[str, Any]] = []
    if audit_config["enabled"] and audit_config["min_levels_per_cluster"] > 0:
        parameters_by_cluster: dict[str, list[dict[str, Any]]] = {}
        for item in parameters:
            parameters_by_cluster.setdefault(_cluster(item), []).append(item)
        level_rank = {
            level: index for index, level in enumerate(audit_config["preferred_levels"])
        }
        for cluster_id, members in parameters_by_cluster.items():
            baseline = baseline_by_cluster.get(cluster_id)
            if not baseline:
                continue
            baseline_state = candidate_states.get(str(baseline.get("candidate_id") or ""), {})
            if not baseline_state.get("valid_trials") or baseline_state.get("environment_blocked"):
                continue
            covered = [
                item for item in members
                if candidate_states.get(str(item.get("candidate_id") or ""), {}).get("valid_trials")
                or candidate_states.get(str(item.get("candidate_id") or ""), {}).get("environment_blocked")
                or candidate_states.get(str(item.get("candidate_id") or ""), {}).get("experience_disposition") == "deferred_by_experience"
            ]
            needed = max(0, audit_config["min_levels_per_cluster"] - len(covered))
            if not needed:
                continue
            eligible = [
                item for item in members
                if item not in triggered_parameters
                and not candidate_states.get(str(item.get("candidate_id") or ""), {}).get("valid_trials")
                and not candidate_states.get(str(item.get("candidate_id") or ""), {}).get("environment_blocked")
                and candidate_states.get(str(item.get("candidate_id") or ""), {}).get("experience_disposition") != "deferred_by_experience"
            ]
            audit_parameters.extend(sorted(
                eligible,
                key=lambda item: (
                    level_rank.get(_level(item), len(level_rank)),
                    _cost(item),
                    str(item.get("candidate_id") or ""),
                ),
            )[:needed])
    required_parameter_ids = {
        str(item.get("candidate_id") or "")
        for item in triggered_parameters + audit_parameters
    }
    required_parameters = [
        item for item in parameters
        if str(item.get("candidate_id") or "") in required_parameter_ids
    ]
    pending_confirmations = [
        state for state in candidate_states.values()
        if 0 < int(state.get("anomaly_trials") or 0) < stable_repetitions
    ]
    confirmation_actions = sum(
        max(0, stable_repetitions - int(state.get("anomaly_trials") or 0))
        for state in pending_confirmations
    )
    required_unique = len(untested_baselines) + len(required_parameters)
    remaining_cost = sum(_cost(item) for item in untested_baselines) + sum(_cost(item) for item in required_parameters)
    confirmation_cost = sum(
        max(0, stable_repetitions - int(state.get("anomaly_trials") or 0))
        * _cost(next(
            (item for item in candidates if str(item.get("candidate_id") or "") == str(state.get("candidate_id") or "")),
            {},
        ))
        for state in pending_confirmations
    )
    return {
        "mode": "auto",
        "stable_repetitions": stable_repetitions,
        "unique_hypotheses_seen": len(unique_history),
        "baseline_total": len(baselines),
        "baseline_covered": len(baselines) - len(untested_baselines),
        "untested_baseline_count": len(untested_baselines),
        "blocked_candidate_count": sum(
            bool(state.get("environment_blocked")) for state in candidate_states.values()
        ),
        "triggered_cluster_count": len(triggered_clusters),
        "triggered_parameter_count": len(triggered_parameters),
        "parameter_audit_enabled": audit_config["enabled"],
        "parameter_audit_floor": audit_config["min_levels_per_cluster"],
        "parameter_audit_count": len(audit_parameters),
        "pending_confirmation_count": len(pending_confirmations),
        "required_confirmation_actions": confirmation_actions,
        "remaining_unique_work": required_unique,
        "remaining_action_work": required_unique + confirmation_actions,
        "remaining_cost_units": round(remaining_cost, 6),
        "remaining_confirmation_cost_units": round(confirmation_cost, 6),
        "remaining_total_cost_units": round(remaining_cost + confirmation_cost, 6),
        "dynamic_unique_budget": len(unique_history) + required_unique,
        "dynamic_action_upper_bound": len(unique_history) + required_unique + confirmation_actions,
        "untested_baseline_ids": [str(item.get("candidate_id") or "") for item in untested_baselines],
        "triggered_parameter_ids": [str(item.get("candidate_id") or "") for item in triggered_parameters],
        "parameter_audit_ids": [str(item.get("candidate_id") or "") for item in audit_parameters],
        "deferred_by_experience_ids": [
            str(item.get("candidate_id") or "") for item in parameters
            if candidate_states.get(str(item.get("candidate_id") or ""), {}).get("experience_disposition") == "deferred_by_experience"
        ],
        "blocked_candidate_ids": [
            str(candidate_id)
            for candidate_id, state in candidate_states.items()
            if state.get("environment_blocked")
        ],
    }
