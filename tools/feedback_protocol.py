"""Independent outcome classification and guarded cross-project feedback.

The module is intentionally deterministic.  It turns runner/oracle evidence
into a reviewable card, then creates a new KB snapshot for later projects.  It
never mutates the current project's input and refuses same-round feedback.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Iterable


CLASSIFICATIONS = {
    "confirmed_weakness",
    "protected",
    "latent_risk",
    "unsupported",
    "environment_blocked",
    "method_invalid",
}
DEFENSE_CLAIM_TYPES = {
    "bounded_timeout",
    "retry",
    "fallback",
    "circuit_breaker",
    "redundancy",
    "graceful_degradation",
    "probe_restart_escape",
}
REQUIRED_WEAKNESS_EVIDENCE = ("baseline", "injection", "observation", "recovery", "cleanup", "independent_oracle")
REQUIRED_AVAILABILITY_EVIDENCE = REQUIRED_WEAKNESS_EVIDENCE
REQUIRED_DEFENSE_EVIDENCE = REQUIRED_WEAKNESS_EVIDENCE + ("observation_window", "mechanism_evidence")
FORBIDDEN_KB_FIELDS = {
    "target",
    "evidence",
    "oracle_label",
    "classification",
    "runtime_observation",
    "post_run_rca",
    "mutation_path",
    "candidate_mutation_path",
    "final_verdict",
    "runtime_verdict",
    "pod_uid",
    "pod_uids",
    "availableReplicas",
    "samples",
}
COMMON_KNOWLEDGE_KEYS = {
    "project_id", "project_commit", "source_tree_sha", "deployment_summary",
    "workload_summary", "runner_version", "oracle_version", "schema_version",
    "seed", "candidate_pool_sha256", "candidate_order", "candidate_budget_k",
}
FORBIDDEN_KB_MARKERS = {
    "oracle_label", "oracle_verdict", "runtime_observation", "post_run_rca",
    "mutation_path", "candidate_mutation_path", "final_verdict", "confirmed_weakness",
    "protected", "selected_by_", "prior_method", "issue_ledger",
}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _walk_strings(value: Any, path: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            yield child_path, str(key)
            yield from _walk_strings(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_strings(child, f"{path}[{index}]")
    elif isinstance(value, str):
        yield path, value


def validate_ablation_pair(kb_bundle: dict[str, Any], nokb_bundle: dict[str, Any]) -> dict[str, Any]:
    """Fail closed if KB/noKB differ outside the declared knowledge view."""
    errors: list[str] = []
    if kb_bundle.get("project_id") != nokb_bundle.get("project_id") or kb_bundle.get("seed") != nokb_bundle.get("seed"):
        errors.append("project_or_seed_mismatch")
    for field in ("common_input", "topology_evidence", "runtime_contract", "output_schema", "prompt_module_sha256", "source_evidence_sha256", "topology_evidence_sha256"):
        if _canonical(kb_bundle.get(field)) != _canonical(nokb_bundle.get(field)):
            errors.append(f"non_identical_shared_field:{field}")
    if not kb_bundle.get("knowledge_view"):
        errors.append("kb_knowledge_view_missing")
    if nokb_bundle.get("knowledge_view") is not None:
        errors.append("nokb_knowledge_view_present")
    # Result-class names such as ``protected`` are part of the shared runtime
    # contract and are therefore allowed. The noKB-specific check is the
    # absence of the knowledge view itself; prompt leakage is audited on the
    # rendered prompt separately.
    return {"valid": not errors, "errors": errors, "common_input_sha256": hashlib.sha256(_canonical(kb_bundle.get("common_input")).encode()).hexdigest()}


def validate_knowledge_card_boundary(card: dict[str, Any], common_input: dict[str, Any] | None = None) -> dict[str, Any]:
    """Audit a card before it can become cross-project knowledge."""
    errors: list[str] = []
    # Audit metadata/evidence is retained in the card; only the projected
    # abstraction is eligible for prompt exposure and must be leak-free.
    for path, value in _walk_strings(card.get("abstraction") or {}):
        lowered = value.lower()
        if any(marker.lower() in lowered for marker in FORBIDDEN_KB_MARKERS):
            errors.append(f"forbidden_marker:abstraction.{path}")
    if common_input:
        common_values = {str(v).lower() for _, v in _walk_strings(common_input)}
        abstraction = card.get("abstraction") or {}
        redundant = [path for path, value in _walk_strings(abstraction) if value.lower() in common_values]
        if redundant:
            errors.extend(f"abstraction_repeats_common:{path}" for path in redundant)
    if card.get("review", {}).get("status") != "human_reviewed":
        errors.append("human_review_required")
    if card.get("classification") not in {"confirmed_weakness", "protected"}:
        errors.append("classification_not_feedback_eligible")
    return {"valid": not errors, "errors": errors}


def validate_improvement_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    """Validate a deployment retest before it can influence knowledge."""

    errors: list[str] = []
    allowed_statuses = {"improvement_verified", "regression", "deployment_blocked", "not_run"}
    if evidence.get("schema_version") != "chaosatlas-improvement-evidence-v1":
        errors.append("schema_version_required")
    status = evidence.get("status")
    if status not in allowed_statuses:
        errors.append("unsupported_status")
    eligible = (
        status == "improvement_verified"
        and evidence.get("same_scenario_contract") is True
        and evidence.get("cleanup_verified") is True
    )
    if evidence.get("knowledge_update_allowed") is not eligible:
        errors.append("knowledge_update_gate_mismatch")
    if not eligible and evidence.get("defense_claim") is not None:
        errors.append("defense_claim_without_verified_improvement")
    return {"valid": not errors, "errors": errors}


def _truthy(evidence: dict[str, Any], key: str) -> bool:
    value = evidence.get(key)
    return value is True or (isinstance(value, dict) and value.get("status") in {"pass", "valid", "confirmed"})


def classify_outcome(result: dict[str, Any]) -> str:
    """Classify without allowing environment failures to look like defenses."""
    if result.get("method_invalid") or result.get("compiler_status") == "method_invalid":
        return "method_invalid"
    if result.get("environment_blocked") or result.get("runner_status") == "environment_blocked" or result.get("oracle_label") in {"environment_blocked", "platform_blocked"}:
        return "environment_blocked"
    if result.get("unsupported") or result.get("oracle_label") in {"unsupported", "unavailable", "contradictory_evidence"}:
        return "unsupported"
    evidence = result.get("evidence") or {}
    availability_label = result.get("availability_label") or result.get("oracle_label")
    evidence_complete = all(_truthy(evidence, key) for key in REQUIRED_AVAILABILITY_EVIDENCE)
    if availability_label in {"availability_degraded", "recovery_timeout", "probe_restart_escape", "no_readiness_false_recovery"} and evidence_complete and int(result.get("valid_reproductions", 0)) >= 2:
        return "confirmed_weakness"
    if result.get("oracle_label") == "weakness" and all(_truthy(evidence, key) for key in REQUIRED_WEAKNESS_EVIDENCE) and int(result.get("valid_reproductions", 0)) >= 2:
        return "confirmed_weakness"
    defense_claim_type = str(result.get("defense_claim_type") or "")
    defense_complete = (
        defense_claim_type in DEFENSE_CLAIM_TYPES
        and all(_truthy(evidence, key) for key in REQUIRED_DEFENSE_EVIDENCE)
    )
    if availability_label == "availability_defended" and defense_complete:
        return "protected"
    if result.get("oracle_label") == "protected" and defense_complete:
        return "protected"
    if result.get("static_risk") or result.get("oracle_label") == "unverifiable":
        return "latent_risk"
    return "unsupported"


def build_feedback_card(result: dict[str, Any], review_status: str = "pending") -> dict[str, Any]:
    project_id = str(result.get("project_id", ""))
    commit = str(result.get("project_commit", ""))
    signature = str(result.get("canonical_signature", ""))
    source_round_id = str(result.get("round_id", ""))
    if not project_id or not commit or not signature or not source_round_id:
        raise ValueError("project_id, project_commit, canonical_signature, and round_id are required")
    classification = classify_outcome(result)
    card_id = "FA-" + hashlib.sha256(f"{project_id}:{commit}:{signature}".encode("utf-8")).hexdigest()[:16]
    evidence = dict(result.get("evidence") or {})
    abstraction = dict(result.get("abstraction") or {})
    abstraction.setdefault("weakness_family", result.get("fault_family", "unknown"))
    abstraction.setdefault("target_role", result.get("target_kind", "unknown"))
    if classification == "protected" and str(result.get("defense_claim_type") or "") in DEFENSE_CLAIM_TYPES:
        abstraction.setdefault("defense_claim_type", str(result["defense_claim_type"]))
    return {
        "schema_version": "1.0",
        "card_id": card_id,
        "project_id": project_id,
        "project_commit": commit,
        "source_round_id": source_round_id,
        "canonical_signature": signature,
        "target": result.get("target"),
        "fault_family": result.get("fault_family"),
        "classification": classification,
        "evidence": evidence,
        "abstraction": abstraction,
        "review": {"status": review_status, "reviewer": result.get("reviewer"), "note": result.get("review_note", "")},
        "feedback_eligible": classification in {"confirmed_weakness", "protected"} and review_status == "human_reviewed",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def knowledge_projection(card: dict[str, Any]) -> dict[str, Any]:
    """Return the only portion of a reviewed card allowed into a later KB.

    Feedback cards remain the audit record and may contain runtime evidence.
    A knowledge snapshot receives only provenance and a reviewed abstraction;
    this prevents oracle outcomes and mutation details becoming an input leak.
    """
    abstraction = dict(card.get("abstraction") or {})
    forbidden = sorted(set(abstraction).intersection(FORBIDDEN_KB_FIELDS))
    if forbidden:
        raise ValueError(f"knowledge abstraction contains forbidden fields: {forbidden}")
    if not abstraction:
        raise ValueError("knowledge abstraction is required")
    return {
        "card_id": card.get("card_id"),
        "source_project_id": card.get("project_id"),
        "source_project_commit": card.get("project_commit"),
        "source_round_id": card.get("source_round_id"),
        "abstraction": abstraction,
    }


def build_next_kb(base: dict[str, Any], cards: Iterable[dict[str, Any]], current_project: str, target_projects: Iterable[str], round_id: str, project_order: Iterable[str] | None = None) -> dict[str, Any]:
    """Create a later-project snapshot with explicit round/order isolation.

    ``current_project`` is the project that will consume the new snapshot.
    Cards from the current or a later project are rejected.  The order is
    mandatory for adaptation experiments; without it, feedback cannot be
    proven to be prior-project evidence.
    """
    target_set = {str(item) for item in target_projects}
    order = {str(project): index for index, project in enumerate(project_order or [])}
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for card in cards:
        card_project = str(card.get("project_id", ""))
        if card.get("source_round_id") != round_id:
            rejected.append({"card_id": card.get("card_id"), "reason": "round_mismatch"})
            continue
        if card_project in target_set or card_project == current_project:
            rejected.append({"card_id": card.get("card_id"), "reason": "same_project_feedback_forbidden"})
            continue
        if current_project not in order or card_project not in order:
            rejected.append({"card_id": card.get("card_id"), "reason": "project_order_required"})
            continue
        if order[card_project] >= order[current_project]:
            rejected.append({"card_id": card.get("card_id"), "reason": "future_project_feedback_forbidden"})
            continue
        if not card.get("feedback_eligible"):
            rejected.append({"card_id": card.get("card_id"), "reason": "human_review_required"})
            continue
        boundary = validate_knowledge_card_boundary(card)
        if not boundary["valid"]:
            rejected.append({"card_id": card.get("card_id"), "reason": "knowledge_boundary_failed", "errors": boundary["errors"]})
            continue
        # Keep the audit card outside the KB. Only its abstract, reviewed
        # knowledge projection can affect a later project's prompt.
        try:
            accepted.append(knowledge_projection(card))
        except ValueError as exc:
            rejected.append({"card_id": card.get("card_id"), "reason": str(exc)})
    previous_cards = list(base.get("cards", []))
    seen = {item.get("card_id") for item in previous_cards}
    merged = previous_cards + [item for item in accepted if item.get("card_id") not in seen]
    payload = {"schema_version": "1.0", "kb_version": f"{base.get('kb_version', 'v1')}-after-{round_id}", "round_id": round_id, "cards": merged}
    payload["provenance"] = {"current_project": current_project, "target_projects": sorted(target_set), "accepted_card_ids": [c.get("card_id") for c in accepted], "rejected": rejected, "same_round_leakage": any(item["reason"] in {"same_project_feedback_forbidden", "future_project_feedback_forbidden"} for item in rejected)}
    payload["snapshot_sha256"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()
    return payload
