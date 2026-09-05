"""Adaptive selection and coverage accounting for parameterized Dify tests."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
from typing import Any

from tools.adaptive_budget import adaptive_budget_snapshot
from tools.llm_policy import build_policy_input, guard_policy_decision, parse_policy_output

MIN_REPETITIONS = 3
BLOCKING_STATUSES = {
    "environment_blocked",
    "injection_not_confirmed",
    "business_not_reachable",
    "apply_failed",
    "runner_error",
    "method_invalid",
}
ANOMALY_RESULTS = {
    "availability_degraded",
    "functional_degraded",
    "data_integrity_risk",
    "server_error_observed",
    "client_timeout_observed",
    "response_contract_changed",
    "response_preserved_latency_degradation",
}
NEAR_BOUNDARY_RESULTS = {"response_preserved_latency_degradation"}
LEVEL_ORDER = {"baseline": 0, "default": 0, "low": 1, "medium": 2, "high": 3, "boundary": 4}
REUSABLE_EXPERIENCE_STATUSES = {"local_reusable", "cross_project_reusable"}


def _payload(root: Path, name: str) -> dict[str, Any]:
    path = Path(root) / name
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    value = value.get("payload", value) if isinstance(value, dict) else {}
    return value if isinstance(value, dict) else {}


def inspect_trial(row: dict[str, Any]) -> dict[str, Any]:
    """Read one summary row and its immutable artifacts into a small record."""

    root = Path(str(row.get("output") or ""))
    classification = _payload(root, "finding_report.json")
    if not classification:
        classification = _payload(root, "classify.json")
    result = str(classification.get("result") or classification.get("classification") or "")
    rca = _payload(root, "rca_report.json")
    attestation = classification.get("attestation") or {}
    valid = (
        row.get("status") == "live_completed"
        and row.get("cleanup_status") == "verified"
        and isinstance(attestation, dict)
        and attestation.get("valid") is True
    )
    status = str(row.get("status") or "")
    blocked = status in {"apply_failed", "runner_error", "method_invalid"} or row.get("retry_exhausted") is True or (
        status in {"environment_blocked", "injection_not_confirmed", "business_not_reachable"}
        and int(row.get("attempt") or 0) >= 3
    )
    labels = list(classification.get("labels") or [])
    details = classification.get("classification_details")
    if isinstance(details, dict):
        labels.extend(details.get("labels") or [])
    near_boundary = result in NEAR_BOUNDARY_RESULTS or "latency_degradation" in {str(item) for item in labels}
    return {
        "candidate_id": str(row.get("candidate_id") or ""),
        "output": str(root),
        "repetition": row.get("repetition"),
        "valid": valid,
        "blocked": blocked and not valid,
        "classification": result,
        "anomaly": valid and result in ANOMALY_RESULTS,
        "near_boundary": valid and near_boundary,
        "rca_status": str(rca.get("rca_status") or ""),
    }


def _level(candidate: dict[str, Any]) -> str:
    return str(candidate.get("parameter_level") or "baseline").strip().lower()


def _level_key(candidate: dict[str, Any]) -> tuple[int, str, str, str]:
    return (
        LEVEL_ORDER.get(_level(candidate), 99),
        str(candidate.get("target") or ""),
        str(candidate.get("fault_family") or ""),
        str(candidate.get("candidate_id") or ""),
    )


def _target_key(candidate: dict[str, Any]) -> str:
    """Use the deployment target as the fairness unit for baseline coverage."""

    return str(candidate.get("target") or candidate.get("service_target") or "")


def _experience_matches(candidate: dict[str, Any], knowledge_cards: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Return reusable cards scoped to the same target and fault family."""

    target = str(candidate.get("target") or candidate.get("service_target") or "")
    family = str(candidate.get("fault_family") or candidate.get("operation") or "")
    matches: list[dict[str, Any]] = []
    for card in knowledge_cards or []:
        if not isinstance(card, dict):
            continue
        status = card.get("status") or card.get("knowledge_status")
        if status not in REUSABLE_EXPERIENCE_STATUSES:
            continue
        node = card.get("test_node") if isinstance(card.get("test_node"), dict) else {}
        card_target = str(card.get("target") or node.get("target") or "")
        card_family = str(card.get("fault_family") or node.get("family") or node.get("operation") or "")
        if card_target == target and card_family == family:
            matches.append(card)
    return matches


def _experience_signal(candidate: dict[str, Any], knowledge_cards: list[dict[str, Any]] | None) -> dict[str, Any]:
    matches = _experience_matches(candidate, knowledge_cards)
    weakness_cards = [
        card for card in matches
        if str(card.get("weakness_status") or "").lower() == "confirmed"
        and str(card.get("classification") or "").lower() not in {"protected", "availability_defended"}
        and int(card.get("valid_reproductions") or 0) >= MIN_REPETITIONS
    ]
    protection_cards = [
        card for card in matches
        if str(card.get("weakness_status") or "").lower() in {"protected", "defended"}
        or card.get("closed_boundary") is True
    ]
    if weakness_cards:
        disposition = "reusable_weakness"
    elif protection_cards:
        disposition = "reusable_protection"
    else:
        disposition = "none"
    return {
        "disposition": disposition,
        "card_ids": sorted(str(card.get("id")) for card in matches if card.get("id")),
        "valid_reproductions": max((int(card.get("valid_reproductions") or 0) for card in matches), default=0),
    }


def _candidate_states(
    candidates: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    knowledge_cards: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    inspected = [inspect_trial(row) for row in rows]
    by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in inspected:
        if item["candidate_id"]:
            by_id[item["candidate_id"]].append(item)
    states: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id") or "")
        trials = by_id.get(candidate_id, [])
        valid_trials = [item for item in trials if item["valid"]]
        blocked_trials = [item for item in trials if item["blocked"]]
        anomaly_trials = [item for item in valid_trials if item["anomaly"]]
        clean_trials = [item for item in valid_trials if not item["anomaly"]]
        rca_confirmed = sum(item["rca_status"] == "confirmed" for item in anomaly_trials)
        if len(anomaly_trials) >= MIN_REPETITIONS:
            status = "stable_weakness"
        elif anomaly_trials:
            status = "confirmation_pending"
        elif blocked_trials and not valid_trials:
            status = "environment_blocked"
        elif valid_trials:
            status = "screened_clean"
        else:
            status = "untested"
        experience = _experience_signal(candidate, knowledge_cards)
        states[candidate_id] = {
            "candidate_id": candidate_id,
            "causal_cluster_id": str(candidate.get("causal_cluster_id") or ""),
            "parameter_level": _level(candidate),
            "valid_trials": len(valid_trials),
            "blocked_trials": len(blocked_trials),
            "environment_blocked": bool(blocked_trials and not valid_trials),
            "anomaly_trials": len(anomaly_trials),
            "clean_trials": len(clean_trials),
            "near_boundary_trials": sum(item["near_boundary"] for item in valid_trials),
            "rca_confirmed_trials": rca_confirmed,
            "classifications": sorted({item["classification"] for item in valid_trials}),
            "status": status,
            "experience_disposition": experience["disposition"],
            "experience_card_ids": experience["card_ids"],
            "experience_valid_reproductions": experience["valid_reproductions"],
        }
    # A confirmed reusable weakness makes parameter exploration an audit, not
    # an automatic full ladder. One clean parameter audit can defer the other
    # variants; a parameter anomaly re-opens the remaining ladder.
    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        clusters[str(candidate.get("causal_cluster_id") or candidate.get("candidate_id"))].append(candidate)
    for members in clusters.values():
        member_states = [states[str(item.get("candidate_id") or "")] for item in members]
        baseline_state = next((item for item in member_states if item["parameter_level"] in {"baseline", "default"}), None)
        parameters = [item for item in member_states if item["parameter_level"] not in {"baseline", "default"}]
        if not baseline_state or not parameters:
            continue
        if baseline_state["experience_disposition"] != "reusable_weakness":
            continue
        if not (baseline_state["anomaly_trials"] or baseline_state["near_boundary_trials"]):
            continue
        has_parameter_anomaly = any(item["anomaly_trials"] > 0 for item in parameters)
        has_clean_audit = any(item["valid_trials"] > 0 and item["anomaly_trials"] == 0 for item in parameters)
        for state in parameters:
            if state["valid_trials"] > 0 or has_parameter_anomaly:
                continue
            state["experience_disposition"] = "deferred_by_experience" if has_clean_audit else "audit_required"
    return states


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def build_coverage_report(
    candidates: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    knowledge_cards: list[dict[str, Any]] | None = None,
    policy_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build base, parameter, stable-reproduction and cluster coverage."""

    states = _candidate_states(candidates, rows, knowledge_cards)
    baseline = [item for item in candidates if _level(item) in {"baseline", "default"}]
    parameterized = [item for item in candidates if _level(item) not in {"baseline", "default"}]
    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        clusters[str(candidate.get("causal_cluster_id") or candidate.get("candidate_id"))].append(candidate)

    cluster_states: dict[str, dict[str, Any]] = {}
    for cluster_id, members in sorted(clusters.items()):
        member_states = [states[str(item.get("candidate_id") or "")] for item in members]
        baseline_state = next((item for item in member_states if item["parameter_level"] in {"baseline", "default"}), None)
        if any(item["status"] == "stable_weakness" for item in member_states):
            status = "stable_weakness"
        elif any(item["status"] == "confirmation_pending" for item in member_states):
            status = "confirmation_pending"
        elif any(item["experience_disposition"] == "deferred_by_experience" for item in member_states):
            status = "experience_deferred"
        elif baseline_state and (baseline_state["anomaly_trials"] or baseline_state["near_boundary_trials"]):
            status = "escalation_pending"
        elif baseline_state and baseline_state["status"] == "environment_blocked":
            status = "environment_blocked"
        elif baseline_state and baseline_state["status"] == "screened_clean":
            status = "screened_clean"
        else:
            status = "untested"
        cluster_states[cluster_id] = {
            "causal_cluster_id": cluster_id,
            "target": str(members[0].get("target") or ""),
            "fault_family": str(members[0].get("fault_family") or ""),
            "baseline_candidate_id": baseline_state["candidate_id"] if baseline_state else None,
            "baseline_status": baseline_state["status"] if baseline_state else "missing",
            "baseline_valid_trials": baseline_state["valid_trials"] if baseline_state else 0,
            "parameter_candidate_ids": [
                item["candidate_id"]
                for item in sorted(member_states, key=lambda value: (LEVEL_ORDER.get(value["parameter_level"], 99), value["candidate_id"]))
                if item["parameter_level"] not in {"baseline", "default"}
            ],
            "parameter_covered": sum(
                item["valid_trials"] > 0
                for item in member_states
                if item["parameter_level"] not in {"baseline", "default"}
            ),
            "stable_candidate_ids": [
                item["candidate_id"] for item in member_states if item["status"] == "stable_weakness"
            ],
            "experience_deferred_candidate_ids": [
                item["candidate_id"] for item in member_states
                if item["experience_disposition"] == "deferred_by_experience"
            ],
            "candidate_ids": [str(item.get("candidate_id") or "") for item in sorted(members, key=_level_key)],
            "status": status,
            "final_state": status,
        }

    base_covered = sum(states[str(item.get("candidate_id") or "")]["valid_trials"] > 0 for item in baseline)
    parameter_covered = sum(states[str(item.get("candidate_id") or "")]["valid_trials"] > 0 for item in parameterized)
    stable = [item for item in candidates if states[str(item.get("candidate_id") or "")]["status"] == "stable_weakness"]
    anomaly_candidates = [item for item in candidates if states[str(item.get("candidate_id") or "")]["anomaly_trials"] > 0]
    budget_plan = adaptive_budget_snapshot(
        candidates,
        states,
        rows,
        stable_repetitions=MIN_REPETITIONS,
        parameter_audit=(policy_config or {}).get("parameter_audit"),
    )
    base_coverage = {
        "total": len(baseline),
        "covered": base_covered,
        "rate": _ratio(base_covered, len(baseline)),
    }
    parameter_coverage = {
        "total": len(parameterized),
        "covered": parameter_covered,
        "rate": _ratio(parameter_covered, len(parameterized)),
    }
    return {
        "schema_version": "chaosatlas-dify-coverage-report-v1",
        "candidate_total": len(candidates),
        "causal_cluster_total": len(clusters),
        "trial_total": len(rows),
        "valid_trial_total": sum(item["valid"] for item in (inspect_trial(row) for row in rows)),
        "base_coverage": base_coverage,
        "basic_coverage": dict(base_coverage),
        "parameter_coverage": parameter_coverage,
        "stable_reproduction_coverage": {
            "total": len(candidates),
            "stable": len(stable),
            "rate": _ratio(len(stable), len(candidates)),
            "anomalous_candidates": len(anomaly_candidates),
            "stable_among_anomalous": _ratio(len(stable), len(anomaly_candidates)),
        },
        "budget_plan": budget_plan,
        "experience_summary": {
            "reusable_card_count": len({card_id for state in states.values() for card_id in state["experience_card_ids"]}),
            "reusable_weakness_candidates": sum(state["experience_disposition"] == "reusable_weakness" for state in states.values()),
            "deferred_parameter_candidates": sum(state["experience_disposition"] == "deferred_by_experience" for state in states.values()),
            "rule": "experience may defer parameter variants after one clean audit; it never bypasses baseline or 3-of-3 anomaly confirmation",
        },
        "candidate_states": states,
        "causal_clusters": cluster_states,
    }


def _select_next_action_deterministic(
    candidates: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    *,
    max_unique_hypotheses: int | None,
    knowledge_cards: list[dict[str, Any]] | None = None,
    policy_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Select confirmation, escalation, or a new baseline candidate.

    Confirmation trials do not consume the unique-hypothesis budget. A clean
    baseline suppresses its higher-intensity siblings until new evidence makes
    them valuable.
    """

    if max_unique_hypotheses is not None and max_unique_hypotheses < 1:
        raise ValueError("max_unique_hypotheses must be positive when fixed")
    states = _candidate_states(candidates, rows, knowledge_cards)
    valid_or_started = {
        str(row.get("candidate_id") or "")
        for row in rows
        if str(row.get("candidate_id") or "")
        and row.get("status") == "live_completed"
        and row.get("cleanup_status") == "verified"
    }
    unique_used = len(valid_or_started)
    budget_snapshot = adaptive_budget_snapshot(
        candidates,
        states,
        rows,
        stable_repetitions=MIN_REPETITIONS,
        parameter_audit=(policy_config or {}).get("parameter_audit"),
    )
    effective_budget = max_unique_hypotheses if max_unique_hypotheses is not None else int(budget_snapshot["dynamic_unique_budget"])

    def decision(action: str | None, candidate: dict[str, Any] | None, reason: str | None = None) -> dict[str, Any]:
        return {
            "action": action,
            "stop_reason": reason,
            "candidate": candidate,
            "unique_hypotheses_used": unique_used,
            "unique_hypothesis_budget": effective_budget,
            "unique_hypotheses_remaining": max(0, effective_budget - unique_used),
            "budget_mode": "fixed" if max_unique_hypotheses is not None else "auto",
            "budget_snapshot": budget_snapshot,
            "decision_source": "deterministic",
        }

    pending = [
        item for item in candidates
        if states[str(item.get("candidate_id") or "")]["anomaly_trials"]
        and states[str(item.get("candidate_id") or "")]["anomaly_trials"] < MIN_REPETITIONS
    ]
    if pending:
        candidate = sorted(pending, key=_level_key)[0]
        return decision("confirm", candidate)

    by_cluster: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        by_cluster[str(candidate.get("causal_cluster_id") or candidate.get("candidate_id"))].append(candidate)
    escalations: list[dict[str, Any]] = []
    for members in by_cluster.values():
        baseline = next((item for item in members if _level(item) in {"baseline", "default"}), None)
        if not baseline:
            continue
        baseline_state = states[str(baseline.get("candidate_id") or "")]
        if not (baseline_state["anomaly_trials"] or baseline_state["near_boundary_trials"]):
            continue
        for candidate in members:
            state = states[str(candidate.get("candidate_id") or "")]
            if (
                _level(candidate) not in {"baseline", "default"}
                and state["valid_trials"] == 0
                and not state.get("environment_blocked")
                and state["experience_disposition"] != "deferred_by_experience"
            ):
                escalations.append(candidate)
    if escalations:
        if unique_used < effective_budget:
            return decision("escalate", sorted(escalations, key=_level_key)[0])

    baselines = [
        item for item in candidates
        if _level(item) in {"baseline", "default"}
        and states[str(item.get("candidate_id") or "")]["valid_trials"] == 0
        and not states[str(item.get("candidate_id") or "")].get("environment_blocked")
    ]
    if baselines and unique_used < effective_budget:
        # Rotate through the least-covered targets first. This preserves
        # service-wide baseline coverage when the candidate list is workload-major.
        coverage_by_target: dict[str, int] = defaultdict(int)
        for item in candidates:
            if _level(item) not in {"baseline", "default"}:
                continue
            state = states[str(item.get("candidate_id") or "")]
            if state["valid_trials"] > 0:
                coverage_by_target[_target_key(item)] += 1
        selected = sorted(
            baselines,
            key=lambda item: (coverage_by_target[_target_key(item)], _target_key(item), _level_key(item)),
        )[0]
        return decision("screen", selected)
    audit_ids = set(budget_snapshot.get("parameter_audit_ids") or [])
    audits = [
        item for item in candidates
        if str(item.get("candidate_id") or "") in audit_ids
    ]
    if audits and unique_used < effective_budget:
        selected = sorted(audits, key=_level_key)[0]
        result = decision("escalate", selected)
        result["selection_reason"] = "parameter_audit_floor"
        return result
    if unique_used >= effective_budget and max_unique_hypotheses is not None:
        return decision(None, None, "budget_exhausted")
    if any(state.get("environment_blocked") for state in states.values()):
        return decision(None, None, "environment_blocked")
    return decision(None, None, "low_expected_value")


def select_next_action(
    candidates: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    *,
    max_unique_hypotheses: int | None,
    policy_provider: Any | None = None,
    policy_mode: str = "guarded",
    knowledge_cards: list[dict[str, Any]] | None = None,
    project_context: dict[str, Any] | None = None,
    policy_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Select one action, optionally using an LLM as the policy decision-maker.

    The provider chooses among registered candidates. The mandatory baseline,
    confirmation, escalation, budget, and safety constraints remain a
    deterministic fail-closed guard. ``shadow`` records the LLM decision but
    executes the deterministic decision for comparison.
    """

    if policy_mode not in {"shadow", "guarded"}:
        raise ValueError("policy_mode must be shadow or guarded")
    fallback = _select_next_action_deterministic(
        candidates,
        rows,
        max_unique_hypotheses=max_unique_hypotheses,
        knowledge_cards=knowledge_cards,
        policy_config=policy_config,
    )
    if policy_provider is None:
        return fallback

    states = _candidate_states(candidates, rows, knowledge_cards)
    valid_or_started = {
        str(row.get("candidate_id") or "")
        for row in rows
        if str(row.get("candidate_id") or "")
        and row.get("status") == "live_completed"
        and row.get("cleanup_status") == "verified"
    }
    request = build_policy_input(
        candidates,
        states,
        rows,
        fallback["budget_snapshot"],
        knowledge_cards=knowledge_cards,
        project_context=project_context,
    )
    try:
        raw = policy_provider(request)
        parsed = parse_policy_output(
            raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=True),
            allowed_candidate_ids={str(item.get("candidate_id") or "") for item in candidates},
        )
        guard = guard_policy_decision(
            parsed,
            candidates,
            states,
            unique_used=len(valid_or_started),
            effective_budget=int(fallback["unique_hypothesis_budget"]),
            min_repetitions=MIN_REPETITIONS,
            anomaly_results=ANOMALY_RESULTS,
            near_boundary_results=NEAR_BOUNDARY_RESULTS,
            parameter_audit_ids=set(fallback["budget_snapshot"].get("parameter_audit_ids") or []),
        )
    except Exception as exc:
        result = dict(fallback)
        result.update({
            "policy_status": "fallback",
            "policy_error": type(exc).__name__,
            "decision_source": "deterministic_fallback",
        })
        return result

    if not guard.get("allowed"):
        result = dict(fallback)
        result.update({
            "policy_status": "rejected",
            "policy_guard": guard,
            "llm_decision": parsed,
            "decision_source": "deterministic_fallback",
        })
        return result

    if policy_mode == "shadow":
        result = dict(fallback)
        result.update({
            "policy_status": "shadow",
            "policy_guard": guard,
            "llm_decision": parsed,
            "llm_selected_action": parsed["action"],
            "llm_selected_candidate_id": parsed.get("candidate_id"),
            "decision_source": "deterministic_shadow",
        })
        return result

    result = dict(fallback)
    result.update({
        "policy_status": "accepted",
        "policy_guard": guard,
        "llm_decision": parsed,
        "decision_source": "llm",
        "action": None if parsed["action"] == "stop" else parsed["action"],
        "candidate": next(
            (item for item in candidates if str(item.get("candidate_id") or "") == parsed.get("candidate_id")),
            None,
        ),
        "stop_reason": parsed.get("stop_reason") if parsed["action"] == "stop" else None,
    })
    return result
