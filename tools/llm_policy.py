"""Project-agnostic LLM policy decisions and fail-closed validation."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any


POLICY_ACTIONS = {"screen", "confirm", "escalate", "stop"}
_TOP_LEVEL_FIELDS = {
    "action",
    "candidate_id",
    "hypothesis",
    "stop_reason",
    "reason",
    "confidence",
    "expected_information_gain",
    "policy_metadata",
}
_HYPOTHESIS_FIELDS = {
    "mechanism",
    "expected_observations",
    "missing_evidence",
    "next_actions",
}


def _bounded_text(value: Any, limit: int = 320) -> str:
    return str(value or "").strip()[:limit]


def _bounded_list(value: Any, *, limit: int = 4, item_limit: int = 240) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_bounded_text(item, item_limit) for item in value[:limit] if _bounded_text(item, item_limit)]


def _compact_value(value: Any, *, depth: int = 0) -> Any:
    """Keep policy prompts bounded when adapters attach large runtime specs."""

    if depth >= 2:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return _bounded_text(value, 180) if isinstance(value, str) else value
        return str(value)[:180]
    if isinstance(value, dict):
        return {
            str(key): _compact_value(child, depth=depth + 1)
            for key, child in list(value.items())[:12]
        }
    if isinstance(value, list):
        return [_compact_value(item, depth=depth + 1) for item in value[:8]]
    return _bounded_text(value, 180) if isinstance(value, str) else value


def _candidate_view(candidate: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "candidate_id",
        "target",
        "service_target",
        "target_kind",
        "fault_family",
        "operation",
        "causal_cluster_id",
        "parameter_level",
        "parameters",
        "estimated_cost",
        "cost_units",
        "risk_level",
    )
    view = {key: deepcopy(candidate[key]) for key in keys if key in candidate}
    if "parameters" in view:
        view["parameters"] = _compact_value(view["parameters"])
    return view


def build_policy_input(
    candidates: list[dict[str, Any]],
    states: dict[str, dict[str, Any]],
    rows: list[dict[str, Any]],
    budget_snapshot: dict[str, Any],
    *,
    knowledge_cards: list[dict[str, Any]] | None = None,
    project_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a bounded, secret-free decision request for any project adapter."""

    triggered_clusters = {
        str(state.get("causal_cluster_id") or "")
        for state in states.values()
        if state.get("anomaly_trials") or state.get("near_boundary_trials")
    }
    parameter_audit_ids = {
        str(item)
        for item in (budget_snapshot.get("parameter_audit_ids") or [])
    }
    frontier: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id") or "")
        state = states.get(candidate_id, {})
        level = str(candidate.get("parameter_level") or "baseline").lower()
        pending_confirmation = 0 < int(state.get("anomaly_trials") or 0) < 3
        untested_baseline = level in {"baseline", "default"} and not state.get("valid_trials")
        triggered_variant = level not in {"baseline", "default"} and str(
            candidate.get("causal_cluster_id") or state.get("causal_cluster_id") or ""
        ) in triggered_clusters and not state.get("valid_trials")
        parameter_audit = candidate_id in parameter_audit_ids
        if not state.get("environment_blocked") and (
            pending_confirmation
            or untested_baseline
            or (triggered_variant and state.get("experience_disposition") != "deferred_by_experience")
            or (parameter_audit and state.get("experience_disposition") != "deferred_by_experience")
        ):
            frontier.append(candidate)

    candidate_state = []
    for candidate in frontier:
        candidate_id = str(candidate.get("candidate_id") or "")
        state = states.get(candidate_id, {})
        level = str(candidate.get("parameter_level") or "baseline").lower()
        if 0 < int(state.get("anomaly_trials") or 0) < 3:
            required_action = "confirm"
        elif level in {"baseline", "default"}:
            required_action = "screen"
        else:
            required_action = "escalate"
        candidate_state.append({
            "candidate": _candidate_view(candidate),
            "state": {
                key: state.get(key)
                for key in (
                    "status",
                    "valid_trials",
                    "blocked_trials",
                    "environment_blocked",
                    "anomaly_trials",
                    "clean_trials",
                    "near_boundary_trials",
                    "rca_confirmed_trials",
                    "classifications",
                    "experience_disposition",
                    "experience_card_ids",
                    "experience_valid_reproductions",
                )
                if key in state
            },
            "required_action": required_action,
        })
    history = []
    for row in rows[-200:]:
        if not isinstance(row, dict):
            continue
        history.append({
            key: row.get(key)
            for key in (
                "candidate_id",
                "action",
                "repetition",
                "parameter_level",
                "status",
                "cleanup_status",
            )
            if row.get(key) is not None
        })
    cards = []
    for card in (knowledge_cards or [])[:100]:
        if not isinstance(card, dict):
            continue
        node = card.get("test_node") if isinstance(card.get("test_node"), dict) else {}
        cards.append({
            "id": _bounded_text(card.get("id"), 120),
            "status": _bounded_text(card.get("status") or card.get("knowledge_status"), 80),
            "target": _bounded_text(card.get("target") or node.get("target"), 160),
            "fault_family": _bounded_text(card.get("fault_family") or node.get("family"), 100),
            "parameter_level": _bounded_text(card.get("parameter_level") or node.get("parameter_level"), 40),
            "mechanism_claim": _bounded_text(card.get("mechanism_claim") or card.get("root_cause")),
            "applicability_conditions": _bounded_list(card.get("applicability_conditions")),
            "exclusion_conditions": _bounded_list(card.get("exclusion_conditions")),
            "next_evidence": _bounded_list(card.get("next_evidence")),
        })
    return {
        "schema_version": "chaosatlas-policy-input-v1",
        "project_context": deepcopy(project_context or {}),
        "candidates": candidate_state,
        "candidate_pool_summary": {
            "total": len(candidates),
            "decision_frontier": len(frontier),
            "omitted_non_actionable": len(candidates) - len(frontier),
        },
        "history": history,
        "budget": deepcopy(budget_snapshot),
        "knowledge_cards": cards,
        "allowed_actions": sorted(POLICY_ACTIONS),
        "hard_constraints": [
            "use an existing candidate_id only",
            "confirm an anomaly until three valid reproductions",
            "screen required baselines before untriggered parameter variants",
            "escalate a triggered causal cluster before stopping",
            "satisfy the configured parameter-audit floor before stopping",
            "reusable experience may defer only untested parameter variants after one clean audit; it never marks them tested",
            "never bypass recovery, cleanup, oracle, or environment safety gates",
        ],
    }


def _decode_json_object(raw: Any) -> dict[str, Any]:
    text = str(raw).strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("policy output must be an object")
    return value


def parse_policy_output(raw: Any, *, allowed_candidate_ids: set[str]) -> dict[str, Any]:
    """Parse a typed LLM decision and reject unsupported claims."""

    value = _decode_json_object(raw)
    unknown = set(value) - _TOP_LEVEL_FIELDS
    if unknown:
        raise ValueError(f"unsupported policy fields: {sorted(unknown)}")
    action = str(value.get("action") or "").strip().lower()
    if action not in POLICY_ACTIONS:
        raise ValueError(f"unsupported policy action: {action}")
    candidate_id = value.get("candidate_id")
    if action == "stop":
        if candidate_id not in (None, ""):
            raise ValueError("stop decision cannot contain candidate_id")
        candidate_id = None
    elif str(candidate_id or "") not in allowed_candidate_ids:
        raise ValueError(f"unknown candidate_id: {candidate_id}")
    reason = _bounded_text(value.get("reason"))
    if not reason:
        raise ValueError("policy reason is required")
    parsed: dict[str, Any] = {
        "schema_version": "chaosatlas-policy-decision-v1",
        "action": action,
        "candidate_id": str(candidate_id) if candidate_id else None,
        "reason": reason,
        "stop_reason": _bounded_text(value.get("stop_reason"), 120) or None,
    }
    for field in ("confidence", "expected_information_gain"):
        if field in value:
            try:
                number = float(value[field])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{field} must be numeric") from exc
            if not 0.0 <= number <= 1.0:
                raise ValueError(f"{field} must be between 0 and 1")
            parsed[field] = number
    hypothesis = value.get("hypothesis")
    if action != "stop":
        if not isinstance(hypothesis, dict):
            raise ValueError("hypothesis is required for an executable action")
        unsupported = set(hypothesis) - _HYPOTHESIS_FIELDS
        if unsupported:
            raise ValueError(f"unsupported hypothesis fields: {sorted(unsupported)}")
        mechanism = _bounded_text(hypothesis.get("mechanism"), 500)
        if not mechanism:
            raise ValueError("hypothesis.mechanism is required")
        parsed["hypothesis"] = {
            "mechanism": mechanism,
            "expected_observations": _bounded_list(hypothesis.get("expected_observations"), limit=3),
            "missing_evidence": _bounded_list(hypothesis.get("missing_evidence"), limit=3),
            "next_actions": _bounded_list(hypothesis.get("next_actions"), limit=3),
        }
    if "policy_metadata" in value and isinstance(value["policy_metadata"], dict):
        parsed["policy_metadata"] = {
            key: value["policy_metadata"][key]
            for key in (
                "backend",
                "model",
                "endpoint",
                "generation_time_ms",
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "finish_reason",
            )
            if key in value["policy_metadata"]
        }
    return parsed


def guard_policy_decision(
    decision: dict[str, Any],
    candidates: list[dict[str, Any]],
    states: dict[str, dict[str, Any]],
    *,
    unique_used: int,
    effective_budget: int,
    min_repetitions: int,
    anomaly_results: set[str],
    near_boundary_results: set[str],
    parameter_audit_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Validate an LLM choice against non-bypassable experiment constraints."""

    by_id = {str(item.get("candidate_id") or ""): item for item in candidates}
    pending = [
        item for item in candidates
        if int(states.get(str(item.get("candidate_id") or ""), {}).get("anomaly_trials") or 0) in range(1, min_repetitions)
    ]
    escalations: list[dict[str, Any]] = []
    clusters: dict[str, list[dict[str, Any]]] = {}
    for item in candidates:
        clusters.setdefault(str(item.get("causal_cluster_id") or item.get("candidate_id") or ""), []).append(item)
    for members in clusters.values():
        baseline = next((item for item in members if str(item.get("parameter_level") or "baseline").lower() in {"baseline", "default"}), None)
        if not baseline:
            continue
        baseline_state = states.get(str(baseline.get("candidate_id") or ""), {})
        if not (baseline_state.get("anomaly_trials") or baseline_state.get("near_boundary_trials")):
            continue
        escalations.extend(
            item for item in members
            if str(item.get("parameter_level") or "baseline").lower() not in {"baseline", "default"}
            and not states.get(str(item.get("candidate_id") or ""), {}).get("valid_trials")
            and not states.get(str(item.get("candidate_id") or ""), {}).get("environment_blocked")
            and states.get(str(item.get("candidate_id") or ""), {}).get("experience_disposition") != "deferred_by_experience"
        )
    baselines = [
        item for item in candidates
        if str(item.get("parameter_level") or "baseline").lower() in {"baseline", "default"}
        and not states.get(str(item.get("candidate_id") or ""), {}).get("valid_trials")
        and not states.get(str(item.get("candidate_id") or ""), {}).get("environment_blocked")
    ]
    parameter_audits = [
        item for item in candidates
        if str(item.get("candidate_id") or "") in (parameter_audit_ids or set())
        and not states.get(str(item.get("candidate_id") or ""), {}).get("valid_trials")
        and not states.get(str(item.get("candidate_id") or ""), {}).get("environment_blocked")
        and states.get(str(item.get("candidate_id") or ""), {}).get("experience_disposition") != "deferred_by_experience"
    ]
    action = decision.get("action")
    candidate_id = str(decision.get("candidate_id") or "")
    if action != "stop" and candidate_id not in by_id:
        return {"allowed": False, "reason": "candidate_not_registered"}
    if pending:
        pending_ids = {str(item.get("candidate_id")) for item in pending}
        if action != "confirm" or candidate_id not in pending_ids:
            return {"allowed": False, "reason": "confirmation_required", "required_candidate_ids": sorted(pending_ids)}
    elif escalations and unique_used < effective_budget:
        escalation_ids = {str(item.get("candidate_id")) for item in escalations}
        if action != "escalate" or candidate_id not in escalation_ids:
            return {"allowed": False, "reason": "escalation_required", "required_candidate_ids": sorted(escalation_ids)}
    elif baselines and unique_used < effective_budget:
        baseline_ids = {str(item.get("candidate_id")) for item in baselines}
        if action != "screen" or candidate_id not in baseline_ids:
            return {"allowed": False, "reason": "baseline_required", "required_candidate_ids": sorted(baseline_ids)}
    elif parameter_audits and unique_used < effective_budget:
        audit_ids = {str(item.get("candidate_id")) for item in parameter_audits}
        if action != "escalate" or candidate_id not in audit_ids:
            return {"allowed": False, "reason": "parameter_audit_required", "required_candidate_ids": sorted(audit_ids)}
    if action == "stop" and (
        pending
        or (escalations and unique_used < effective_budget)
        or (baselines and unique_used < effective_budget)
        or (parameter_audits and unique_used < effective_budget)
    ):
        return {"allowed": False, "reason": "mandatory_work_remaining"}
    if action in {"screen", "escalate"} and unique_used >= effective_budget:
        return {"allowed": False, "reason": "unique_budget_exhausted"}
    state = states.get(candidate_id, {})
    if action == "confirm" and not (0 < int(state.get("anomaly_trials") or 0) < min_repetitions):
        return {"allowed": False, "reason": "candidate_not_pending_confirmation"}
    if action == "screen" and str(by_id[candidate_id].get("parameter_level") or "baseline").lower() not in {"baseline", "default"}:
        return {"allowed": False, "reason": "screen_requires_baseline"}
    if action == "escalate" and str(by_id[candidate_id].get("parameter_level") or "baseline").lower() in {"baseline", "default"}:
        return {"allowed": False, "reason": "escalate_requires_parameter_variant"}
    return {"allowed": True, "reason": "accepted"}


class OpenAICompatPolicyProvider:
    """Generic policy provider over an existing OpenAI-compatible backend."""

    def __init__(self, backend: Any) -> None:
        self.backend = backend

    def __call__(self, payload: dict[str, Any]) -> dict[str, Any]:
        system = (
            "You are the ChaosAtlas project-agnostic experiment policy controller. "
            "Choose exactly one allowed next action using only the supplied candidates, evidence, "
            "budget, and knowledge cards. Return compact JSON. You may select existing candidate IDs, "
            "propose a falsifiable hypothesis, or stop when no mandatory work remains. Never invent "
            "candidate IDs, commands, runtime verdicts, RCA status, or knowledge promotion status."
        )
        user = json.dumps({
            "input": payload,
            "output_schema": {
                "action": "screen for baseline candidates | confirm for pending anomalies | escalate for parameter variants and parameter audits | stop",
                "candidate_id": "existing candidate ID, or null for stop",
                "hypothesis": {
                    "mechanism": "bounded falsifiable mechanism",
                    "expected_observations": ["observable evidence"],
                    "missing_evidence": ["evidence still needed"],
                    "next_actions": ["bounded action"],
                },
                "stop_reason": "required only for stop",
                "reason": "why this action has the highest information value",
                "confidence": 0.0,
                "expected_information_gain": 0.0,
            },
        }, indent=2, ensure_ascii=True)
        raw, metadata = self.backend.complete(
            system,
            user,
            "Return one JSON object matching output_schema.",
        )
        value = _decode_json_object(raw)
        if isinstance(metadata, dict):
            value["policy_metadata"] = {
                key: metadata[key]
                for key in (
                    "backend",
                    "model",
                    "endpoint",
                    "generation_time_ms",
                    "prompt_tokens",
                    "completion_tokens",
                    "total_tokens",
                    "finish_reason",
                )
                if key in metadata
            }
        return value
