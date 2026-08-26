"""Deterministic, read-only evidence planning for advisory hypotheses."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any

from tools.recovery_contract import valid_for_fault


ALLOWED_ACTION_KINDS = {
    "deployment_facts",
    "service_facts",
    "pod_state",
    "pod_events",
    "pod_logs",
    "business_baseline",
    "mechanism_evidence",
}

_ACTION_SPECS = (
    ("deployment_facts", 1, ["deployment_identity"]),
    ("service_facts", 1, ["service_selector"]),
    ("pod_state", 1, ["ready_pods"]),
    ("pod_events", 2, ["kubernetes_event_window"]),
    ("business_baseline", 2, ["business_oracle_baseline"]),
    ("pod_logs", 3, ["runtime_logs_window"]),
    ("mechanism_evidence", 4, ["mechanism_evidence"]),
)
_TEXT_TO_ACTION = (
    (re.compile(r"deploy|replica|selector|pdb|hpa|readiness|liveness|manifest", re.I), "deployment_facts"),
    (re.compile(r"service|route|port|oracle|business|http", re.I), "business_baseline"),
    (re.compile(r"pod|ready|restart|state|replacement|identity", re.I), "pod_state"),
    (re.compile(r"event", re.I), "pod_events"),
    (re.compile(r"log|error|stack|trace", re.I), "pod_logs"),
    (re.compile(r"mechanism|source|cause|evidence", re.I), "mechanism_evidence"),
)
_FORBIDDEN_TEXT = re.compile(r"(?:kubectl|\bshell\b|\bexec(?:ute)?\b|\bdelete\b|\bapply\b|\bpatch\b|\binject\b)", re.I)
_SIGNATURE_FIELDS = ("target", "target_kind", "fault_family", "operation")


def _hash(value: Any) -> str:
    serialized = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _base_result(
    *,
    inventory: dict[str, Any],
    candidate_space: dict[str, Any],
    hypotheses: dict[str, Any],
    candidate_budget: int,
    preferred_candidate_id: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": "chaosatlas-evidence-plan-v1",
        "claim_scope": "advisory",
        "project_id": inventory.get("project_id"),
        "project_commit": inventory.get("project_commit"),
        "input_sha256": _hash({
            "inventory": inventory,
            "candidate_space": candidate_space,
            "hypotheses": hypotheses,
            "candidate_budget": candidate_budget,
            "preferred_candidate_id": preferred_candidate_id,
        }),
        "status": "planned",
        "actions": [],
        "unmapped_advisory": [],
        "blocked_reasons": [],
        "selection": {
            "candidate_ids": [],
            "candidate_budget": candidate_budget,
            "tie_break": "cost asc, candidate_id asc, action_id asc",
        },
        "runtime_experiment": {
            "admissible": False,
            "candidate_ids": [],
            "blocked_reasons": [],
            "scenario_contract_ref": None,
        },
    }


def _block(result: dict[str, Any], reasons: list[str]) -> dict[str, Any]:
    unique = list(dict.fromkeys(str(item) for item in reasons if str(item).strip()))
    result["status"] = "blocked"
    result["blocked_reasons"] = unique
    result["runtime_experiment"] = {
        "admissible": False,
        "candidate_ids": [],
        "blocked_reasons": unique,
        "scenario_contract_ref": None,
    }
    result["selection"]["candidate_ids"] = []
    result["actions"] = []
    return result


def _advisory_items(hypotheses: dict[str, Any]) -> list[dict[str, Any]]:
    advisory = hypotheses.get("advisory")
    if not isinstance(advisory, dict):
        return []
    items = advisory.get("hypotheses")
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _action_kind(text: str) -> str | None:
    if not text or _FORBIDDEN_TEXT.search(text):
        return None
    for pattern, kind in _TEXT_TO_ACTION:
        if pattern.search(text):
            return kind
    return None


def _candidate_actions(candidate: dict[str, Any], advisory: dict[str, Any] | None) -> tuple[list[dict[str, Any]], list[str]]:
    candidate_id = str(candidate.get("candidate_id") or "")
    target = str(candidate.get("target") or "")
    service_target = str(candidate.get("service_target") or target)
    family = str(candidate.get("fault_family") or candidate.get("operation") or "unknown")
    advisory_reason = _text((advisory or {}).get("mechanism"))
    if _FORBIDDEN_TEXT.search(advisory_reason):
        advisory_reason = ""
    reason_suffix = f": {advisory_reason[:240]}" if advisory_reason else ""
    unmapped: list[str] = []
    for field in ("missing_evidence", "next_actions"):
        values = (advisory or {}).get(field, []) if advisory else []
        if not isinstance(values, list):
            continue
        for value in values:
            value_text = _text(value)
            if not value_text or _FORBIDDEN_TEXT.search(value_text):
                continue
            if _action_kind(value_text) is None:
                unmapped.append(value_text[:240])
    actions: list[dict[str, Any]] = []
    for action_kind, cost, required in _ACTION_SPECS:
        action_id = f"{candidate_id}:{action_kind}"
        action_target = service_target if action_kind == "service_facts" else target
        actions.append({
            "action_id": action_id,
            "action_kind": action_kind,
            "candidate_id": candidate_id,
            "target": action_target,
            "deployment_target": target,
            "target_kind": candidate.get("target_kind"),
            "fault_family": family,
            "reason": f"collect bounded {action_kind} for {family} on {target}{reason_suffix}",
            "read_only": True,
            "cost": cost,
            "required_evidence": list(required),
        })
    return actions, unmapped


def build_evidence_plan(
    inventory: dict[str, Any],
    candidate_space: dict[str, Any],
    hypotheses: dict[str, Any],
    *,
    candidate_budget: int,
    preferred_candidate_id: str | None = None,
) -> dict[str, Any]:
    """Build a stable evidence plan without executing or inferring a verdict."""

    result = _base_result(
        inventory=inventory,
        candidate_space=candidate_space,
        hypotheses=hypotheses,
        candidate_budget=candidate_budget,
        preferred_candidate_id=preferred_candidate_id,
    )
    if isinstance(candidate_budget, bool) or not isinstance(candidate_budget, int) or candidate_budget < 1:
        return _block(result, ["candidate budget must be a positive integer"])
    if inventory.get("status") not in {None, "verified"}:
        return _block(result, ["inventory is not verified"])
    if candidate_space.get("status") not in {None, "verified"}:
        return _block(result, ["candidate space is not verified"])
    candidates = [item for item in candidate_space.get("candidates") or [] if isinstance(item, dict)]
    by_id = {str(item.get("candidate_id")): item for item in candidates if item.get("candidate_id")}
    if len(by_id) != len(candidates):
        return _block(result, ["candidate registry contains missing or duplicate candidate IDs"])
    if not by_id:
        return _block(result, ["candidate registry is empty"])

    advertised_ids = hypotheses.get("candidate_ids")
    if not isinstance(advertised_ids, list):
        advertised_ids = list(by_id)
    advertised_ids = [str(item) for item in advertised_ids]
    unknown_ids = [item for item in advertised_ids if item not in by_id]
    if unknown_ids:
        return _block(result, [f"unknown candidate ID: {item}" for item in unknown_ids])

    advisory_by_id: dict[str, dict[str, Any]] = {}
    signature_errors: list[str] = []
    for item in _advisory_items(hypotheses):
        candidate_id = str(item.get("candidate_id") or "")
        if candidate_id not in by_id:
            signature_errors.append(f"unknown candidate ID: {candidate_id}")
            continue
        advisory_by_id[candidate_id] = item
        candidate = by_id[candidate_id]
        for field in _SIGNATURE_FIELDS:
            if field in item and item.get(field) != candidate.get(field):
                signature_errors.append(f"candidate signature mismatch for {candidate_id}: {field}")
    if signature_errors:
        return _block(result, signature_errors)

    ordered_ids = list(dict.fromkeys(advertised_ids))
    if preferred_candidate_id:
        preferred = str(preferred_candidate_id)
        if preferred not in by_id:
            return _block(result, [f"preferred candidate ID is unknown: {preferred}"])
        ordered_ids = [preferred] + [item for item in ordered_ids if item != preferred]
    selected_ids = ordered_ids[:candidate_budget]
    if not selected_ids:
        return _block(result, ["no candidate selected within budget"])
    for candidate_id in selected_ids:
        recovery = by_id[candidate_id].get("recovery_contract")
        if not valid_for_fault(recovery, str(by_id[candidate_id].get("fault_family") or "")):
            return _block(result, [f"missing or incomplete recovery contract: {candidate_id}"])

    actions: list[dict[str, Any]] = []
    unmapped: list[str] = []
    for candidate_id in selected_ids:
        candidate_actions, candidate_unmapped = _candidate_actions(by_id[candidate_id], advisory_by_id.get(candidate_id))
        actions.extend(candidate_actions)
        unmapped.extend(candidate_unmapped)
    actions.sort(key=lambda item: (not bool(item["read_only"]), int(item["cost"]), str(item["candidate_id"]), str(item["action_id"])))
    result["actions"] = actions
    result["unmapped_advisory"] = list(dict.fromkeys(unmapped))
    result["selection"]["candidate_ids"] = selected_ids
    result["runtime_experiment"] = {
        "admissible": True,
        "candidate_ids": selected_ids,
        "blocked_reasons": [],
        "scenario_contract_ref": f"candidate:{selected_ids[0]}",
    }
    return result
