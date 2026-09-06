"""P5 experiment contracts.

This module is deliberately deterministic.  It turns capability discovery and
runtime records into auditable experiment artifacts, but it never executes a
fault or promotes an observation to an application issue by itself.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from chaosatlas.capabilities.contracts import canonical_catalog_ids
from tools.reproduction_policy import MIN_STABLE_REPRODUCTIONS


P5_SCHEMA = "chaosatlas-p5-experiment-package-v1"
_PLAN_STATUSES = {"ready", "blocked", "inapplicable", "unsupported", "canary_required", "supported"}
_VALID_CLAIM_SCOPES = {"planned", "synthetic_oracle_self_check", "real_runtime"}
_SENSITIVE = re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|authorization)\s*[:=]")


def _hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _strings(name: str, value: Any, *, required: bool = False) -> list[str]:
    if value is None and not required:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{name} must be a list[str]")
    return [item.strip() for item in value]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_experiment_plan(
    *,
    project_id: str,
    project_revision: str,
    capability_bootstrap: Mapping[str, Any],
    oracle_ref: Mapping[str, Any] | None = None,
    knowledge_snapshot_id: str | None = None,
) -> dict[str, Any]:
    """Create the complete 32+9 plan while preserving every denominator."""

    project_id = _text("project_id", project_id)
    project_revision = _text("project_revision", project_revision)
    if not isinstance(capability_bootstrap, Mapping):
        raise ValueError("capability_bootstrap must be an object")
    records = capability_bootstrap.get("project_capabilities")
    if not isinstance(records, list):
        raise ValueError("capability_bootstrap.project_capabilities must be a list")
    core_ids, extension_ids = canonical_catalog_ids()
    expected = set(core_ids) | set(extension_ids)
    seen: set[str] = set()
    capabilities: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, Mapping):
            raise ValueError("capability records must be objects")
        capability_id = _text("capability_id", record.get("fault_id"))
        if capability_id in seen:
            raise ValueError(f"duplicate capability: {capability_id}")
        seen.add(capability_id)
        if capability_id not in expected:
            raise ValueError(f"unknown capability: {capability_id}")
        status = str(record.get("capability_status") or "").strip()
        if status not in _PLAN_STATUSES:
            raise ValueError(f"unknown capability status: {status}")
        capabilities.append({
            "capability_id": capability_id,
            "catalog_scope": str(record.get("catalog_scope") or ("core" if capability_id in core_ids else "extension")),
            "status": status,
            "evidence_grade": record.get("evidence_grade"),
            "candidate_eligible": bool(record.get("candidate_eligible")),
            "target_record_count": int(record.get("target_record_count") or 0),
            "reason_codes": sorted(str(item) for item in (record.get("reason_codes") or [])),
            "evidence_refs": sorted(str(item) for item in (record.get("evidence_refs") or [])),
            "experiment_status": "not_scheduled" if status in {"blocked", "inapplicable", "unsupported"} else "pending_canary",
        })
    missing = sorted(expected - seen)
    if missing:
        raise ValueError(f"capability matrix is incomplete: {missing}")
    capabilities.sort(key=lambda item: (item["catalog_scope"], item["capability_id"]))
    status_counts = dict(sorted(Counter(item["status"] for item in capabilities).items()))
    plan = {
        "schema_version": P5_SCHEMA,
        "artifact": "experiment_plan",
        "project_id": project_id,
        "project_revision": project_revision,
        "created_at": _now(),
        "claim_scope": "planned",
        "catalog": {"core": len(core_ids), "extension": len(extension_ids), "total": len(expected)},
        "denominators": {
            "all_capabilities": len(capabilities),
            "core_capabilities": len(core_ids),
            "extension_capabilities": len(extension_ids),
            "runtime_candidates": sum(item["candidate_eligible"] for item in capabilities),
            "real_experiments": 0,
            "valid_reproductions": 0,
            "issue_drafts": 0,
        },
        "status_counts": status_counts,
        "capabilities": capabilities,
        "oracle_ref": deepcopy(dict(oracle_ref)) if isinstance(oracle_ref, Mapping) else None,
        "knowledge_snapshot_id": knowledge_snapshot_id,
        "execution_policy": {
            "faults_executed": False,
            "requires_approved_oracle": True,
            "min_stable_reproductions": MIN_STABLE_REPRODUCTIONS,
            "preserve_blocked_inapplicable_unsupported": True,
        },
    }
    plan["plan_sha256"] = _hash({key: value for key, value in plan.items() if key != "created_at"})
    return plan


def build_hypothesis_record(
    *,
    hypothesis_id: str,
    source_evidence_refs: Iterable[str],
    target_role: str,
    dependency_edge: str,
    fault_intent: str,
    approved_oracle_id: str,
    expected_mechanism: str,
    business_invariant: str,
    predicted_observation: str,
    alternative_explanations: Iterable[str],
    falsifying_observation: str,
    parameter_tier: str,
    discriminating_next_action: str,
    knowledge_snapshot_id: str,
    origin: str = "deterministic",
) -> dict[str, Any]:
    """Build the bounded, falsifiable hypothesis shape used by P4/P5."""

    if origin not in {"deterministic", "llm_advisory", "human"}:
        raise ValueError("origin must be deterministic, llm_advisory, or human")
    record = {
        "schema_version": "chaosatlas-experiment-hypothesis-v1",
        "hypothesis_id": _text("hypothesis_id", hypothesis_id),
        "source_evidence_refs": _strings("source_evidence_refs", list(source_evidence_refs), required=True),
        "target_role": _text("target_role", target_role),
        "dependency_edge": _text("dependency_edge", dependency_edge),
        "fault_intent": _text("fault_intent", fault_intent),
        "approved_oracle_id": _text("approved_oracle_id", approved_oracle_id),
        "expected_mechanism": _text("expected_mechanism", expected_mechanism),
        "business_invariant": _text("business_invariant", business_invariant),
        "predicted_observation": _text("predicted_observation", predicted_observation),
        "alternative_explanations": _strings("alternative_explanations", list(alternative_explanations), required=True),
        "falsifying_observation": _text("falsifying_observation", falsifying_observation),
        "parameter_tier": _text("parameter_tier", parameter_tier),
        "discriminating_next_action": _text("discriminating_next_action", discriminating_next_action),
        "knowledge_snapshot_id": _text("knowledge_snapshot_id", knowledge_snapshot_id),
        "origin": origin,
        "claim_scope": "advisory",
    }
    if any(_SENSITIVE.search(str(value)) for value in record.values()):
        raise ValueError("sensitive fields are not allowed in hypothesis records")
    record["hypothesis_sha256"] = _hash(record)
    return record


def evaluate_experiment_evidence(
    attempts: Iterable[Mapping[str, Any]],
    *,
    expected_causal_key: str | None = None,
    sensitive_review: str = "pending",
) -> dict[str, Any]:
    """Evaluate reproduction and Issue gates without changing runtime state."""

    rows = [dict(item) for item in attempts if isinstance(item, Mapping)]
    if sensitive_review not in {"pending", "passed", "failed"}:
        raise ValueError("sensitive_review must be pending, passed, or failed")
    baselines = [item for item in rows if item.get("role") == "baseline"]
    controls = [item for item in rows if item.get("role") == "control"]
    reproductions = [item for item in rows if item.get("role") == "reproduction"]
    attempt_ids = [str(item.get("attempt_id") or "") for item in rows if item.get("attempt_id")]
    unique_attempt_ids = len(attempt_ids) == len(set(attempt_ids))
    baseline_ids = {str(item.get("attempt_id") or "") for item in baselines}
    control_ids = {str(item.get("attempt_id") or "") for item in controls}
    valid_reproductions = [
        item for item in reproductions
        if item.get("claim_scope") == "real_runtime"
        and item.get("injection_confirmed") is True
        and item.get("anomaly_observed") is True
        and item.get("mechanism_status") == "pass"
        and item.get("recovery_status") == "pass"
        and item.get("cleanup_status") == "pass"
        and (expected_causal_key is None or item.get("causal_key") == expected_causal_key)
        and str(item.get("run_id") or "")
        and str(item.get("reset_id") or "")
        and str(item.get("baseline_ref") or "") in baseline_ids
        and str(item.get("control_ref") or "") in control_ids
    ]
    run_ids = [str(item.get("run_id") or "") for item in valid_reproductions]
    reset_ids = [str(item.get("reset_id") or "") for item in valid_reproductions]
    independent_identity = bool(valid_reproductions) and len(run_ids) == len(set(run_ids)) and len(reset_ids) == len(set(reset_ids))
    baseline_clean = bool(baselines) and all(item.get("anomaly_observed") is False and item.get("status") == "pass" for item in baselines)
    control_clean = bool(controls) and all(item.get("anomaly_observed") is False and item.get("status") == "pass" for item in controls)
    mechanism = bool(valid_reproductions) and all(item.get("mechanism_status") == "pass" for item in valid_reproductions)
    recovery_cleanup = bool(valid_reproductions) and all(
        item.get("recovery_status") == "pass" and item.get("cleanup_status") == "pass" for item in valid_reproductions
    )
    causal_scope = bool(expected_causal_key) and bool(valid_reproductions) and all(item.get("causal_key") == expected_causal_key for item in valid_reproductions)
    gates = {
        "three_independent_reproductions": len(valid_reproductions) >= MIN_STABLE_REPRODUCTIONS,
        "independent_reproduction_identity": independent_identity,
        "pairing_complete": unique_attempt_ids and all(
            str(item.get("baseline_ref") or "") in baseline_ids and str(item.get("control_ref") or "") in control_ids
            for item in valid_reproductions
        ),
        "baseline_clean": baseline_clean,
        "paired_control_clean": control_clean,
        "mechanism_evidence": mechanism,
        "recovery_and_cleanup": recovery_cleanup,
        "causal_scope_fixed": causal_scope,
        "sensitive_review": sensitive_review == "passed",
    }
    issue_eligible = all(gates.values())
    return {
        "schema_version": "chaosatlas-p5-evidence-evaluation-v1",
        "claim_scope": "real_runtime" if any(item.get("claim_scope") == "real_runtime" for item in rows) else "planned",
        "attempt_count": len(rows),
        "baseline_count": len(baselines),
        "control_count": len(controls),
        "reproduction_attempt_count": len(reproductions),
        "valid_reproduction_count": len(valid_reproductions),
        "gates": gates,
        "issue_eligible": issue_eligible,
        "status": "candidate_finding" if issue_eligible else "inconclusive",
        "rejected_reason_codes": sorted(key for key, value in gates.items() if not value),
        "valid_reproduction_ids": [str(item.get("attempt_id")) for item in valid_reproductions],
    }


def build_issue_draft(
    *,
    evaluation: Mapping[str, Any],
    project_id: str,
    project_revision: str,
    title: str,
    expected: str,
    actual: str,
    impact: str,
    reproduction_command: str,
    run_refs: Iterable[str],
    limitations: Iterable[str],
    attribution: str,
) -> dict[str, Any]:
    """Create a human-review-only draft; reject it unless every gate passed."""

    if not isinstance(evaluation, Mapping) or evaluation.get("issue_eligible") is not True:
        raise ValueError("Issue draft requires every P5 evidence gate to pass")
    fields = {
        "title": _text("title", title),
        "expected": _text("expected", expected),
        "actual": _text("actual", actual),
        "impact": _text("impact", impact),
        "reproduction_command": _text("reproduction_command", reproduction_command),
        "attribution": _text("attribution", attribution),
    }
    for name, value in fields.items():
        if _SENSITIVE.search(value):
            raise ValueError(f"sensitive value in {name}")
    refs = _strings("run_refs", list(run_refs), required=True)
    limitations_list = _strings("limitations", list(limitations), required=True)
    return {
        "schema_version": "chaosatlas-issue-draft-v1",
        "status": "pending_human_review",
        "claim_scope": "candidate_finding",
        "project_id": _text("project_id", project_id),
        "project_revision": _text("project_revision", project_revision),
        **fields,
        "run_refs": refs,
        "limitations": limitations_list,
        "evidence_evaluation": deepcopy(dict(evaluation)),
        "submission": {"performed": False, "requires_explicit_user_authorization": True},
    }


def build_knowledge_snapshot(*, snapshot_id: str, project_id: str, project_revision: str, cards: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Freeze the input view; cards are copied so later mutation cannot alter it."""

    normalized = [deepcopy(dict(card)) for card in cards if isinstance(card, Mapping)]
    snapshot = {
        "schema_version": "chaosatlas-knowledge-snapshot-v1",
        "snapshot_id": _text("snapshot_id", snapshot_id),
        "project_id": _text("project_id", project_id),
        "project_revision": _text("project_revision", project_revision),
        "created_at": _now(),
        "claim_scope": "advisory",
        "card_count": len(normalized),
        "cards": normalized,
    }
    snapshot["snapshot_sha256"] = _hash({key: value for key, value in snapshot.items() if key != "created_at"})
    return snapshot


def summarize_cost(*, experiments: int = 0, valid_reproductions: int = 0, llm_calls: int = 0, llm_input_tokens: int = 0, llm_output_tokens: int = 0, wall_time_seconds: float = 0.0) -> dict[str, Any]:
    values = {"experiments": experiments, "valid_reproductions": valid_reproductions, "llm_calls": llm_calls, "llm_input_tokens": llm_input_tokens, "llm_output_tokens": llm_output_tokens, "wall_time_seconds": wall_time_seconds}
    for name, value in values.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ValueError(f"{name} must be a non-negative number")
    return {"schema_version": "chaosatlas-cost-summary-v1", **values, "llm_total_tokens": llm_input_tokens + llm_output_tokens}


def validate_canary_evidence(
    *,
    project_id: str,
    source_ref: str,
    batch_summary: Mapping[str, Any],
    isolation_lifecycle: Mapping[str, Any],
    baseline_result: Mapping[str, Any],
    execute_result: Mapping[str, Any],
    observe_result: Mapping[str, Any],
    cleanup_report: Mapping[str, Any],
    transaction_binding: Mapping[str, Any],
    sensitive_review: str,
) -> dict[str, Any]:
    """Fail closed when admitting a real unified-engine canary into P5 evidence."""

    if sensitive_review not in {"passed", "failed"}:
        raise ValueError("sensitive_review must be passed or failed")
    batch_results = batch_summary.get("results")
    batch_rows = batch_results if isinstance(batch_results, list) else []
    child = batch_rows[0] if len(batch_rows) == 1 and isinstance(batch_rows[0], Mapping) else {}
    execute_payload = execute_result.get("payload") if isinstance(execute_result.get("payload"), Mapping) else {}
    phases = execute_payload.get("phases") if isinstance(execute_payload.get("phases"), list) else []
    faults = [
        fault
        for phase in phases
        if isinstance(phase, Mapping)
        for fault in (phase.get("faults") if isinstance(phase.get("faults"), list) else [])
        if isinstance(fault, Mapping)
    ]
    baseline_payload = baseline_result.get("payload") if isinstance(baseline_result.get("payload"), Mapping) else {}
    baseline = baseline_payload.get("evidence") if isinstance(baseline_payload.get("evidence"), Mapping) else {}
    observe_payload = observe_result.get("payload") if isinstance(observe_result.get("payload"), Mapping) else {}
    observation = observe_payload.get("observation") if isinstance(observe_payload.get("observation"), Mapping) else {}
    oracle = execute_payload.get("oracle") if isinstance(execute_payload.get("oracle"), Mapping) else {}
    business_oracle = oracle.get("business") if isinstance(oracle.get("business"), Mapping) else {}

    fault_attestations = [item.get("attestation") for item in faults]
    gates = {
        "batch_completed": batch_summary.get("status") == "completed" and len(batch_rows) == 1 and child.get("status") == "live_completed",
        "isolated_environment_verified": isolation_lifecycle.get("status") == "verified" and isolation_lifecycle.get("prepare_state") == "ready",
        "environment_released": isolation_lifecycle.get("cleanup_state") == "released",
        "injection_confirmed": isolation_lifecycle.get("injection_performed") is True
        and child.get("injection_confirmed") is True
        and bool(faults)
        and all(
            item.get("injection_confirmed") is True
            and isinstance(item.get("injection_confirmation"), Mapping)
            and item["injection_confirmation"].get("confirmed") is True
            and bool(item["injection_confirmation"].get("mechanism"))
            for item in faults
        ),
        "runtime_attestation_valid": bool(fault_attestations) and all(
            isinstance(item, Mapping)
            and item.get("valid") is True
            and item.get("missing") == []
            and all(item.get(key) is True for key in ("baseline", "injection", "observation", "recovery", "cleanup", "independent_oracle", "comparison_eligible"))
            for item in fault_attestations
        ),
        "business_baseline_passed": baseline.get("claim_scope") == "real_business_transaction" and baseline.get("status") == "pass" and baseline.get("failed_assertions") == [],
        "business_observation_recorded": observation.get("claim_scope") == "real_business_transaction"
        and observation.get("status") in {"pass", "fail"}
        and isinstance(observation.get("failed_assertions"), list)
        and ((observation.get("status") == "pass") == (observation.get("failed_assertions") == [])),
        "business_recovery_passed": bool(faults) and all(
            isinstance(item.get("recovery"), Mapping)
            and item["recovery"].get("confirmed") is True
            and isinstance(item["recovery"].get("business_probe"), Mapping)
            and item["recovery"]["business_probe"].get("claim_scope") == "real_business_transaction"
            and item["recovery"]["business_probe"].get("status") == "pass"
            for item in faults
        ),
        "fault_cleanup_verified": cleanup_report.get("status") == "verified" and cleanup_report.get("residual_count") == 0 and cleanup_report.get("errors") == [] and cleanup_report.get("action_count") == cleanup_report.get("verified_action_count"),
        "business_cleanup_verified": bool(faults) and all(
            isinstance(item.get("cleanup"), Mapping)
            and item["cleanup"].get("verified") is True
            and isinstance(item["cleanup"].get("business"), Mapping)
            and item["cleanup"]["business"].get("cleanup_confirmed") is True
            and item["cleanup"]["business"].get("environment_released") is True
            for item in faults
        ),
        "frozen_oracle_bound": transaction_binding.get("project_id") == project_id
        and transaction_binding.get("credential_values_persisted") is False
        and bool(transaction_binding.get("contract_sha256"))
        and transaction_binding.get("contract_sha256") == business_oracle.get("approved_contract_sha256"),
        "sensitive_review": sensitive_review == "passed",
    }
    valid = all(gates.values())
    confirmed_findings = int(batch_summary.get("confirmed_finding_count") or 0)
    anomaly_observed = observation.get("status") == "fail" or confirmed_findings > 0
    return {
        "schema_version": "chaosatlas-p5-canary-evidence-v1",
        "project_id": _text("project_id", project_id),
        "source_ref": _text("source_ref", source_ref),
        "claim_scope": "real_runtime" if valid else "unverified",
        "fault_id": isolation_lifecycle.get("fault_id"),
        "run_id": child.get("run_id"),
        "oracle_id": transaction_binding.get("oracle_id"),
        "contract_sha256": transaction_binding.get("contract_sha256"),
        "mechanisms": sorted({str((item.get("injection_confirmation") or {}).get("mechanism")) for item in faults if isinstance(item.get("injection_confirmation"), Mapping)}),
        "gates": gates,
        "evidence_valid": valid,
        "anomaly_observed": anomaly_observed,
        "confirmed_finding_count": confirmed_findings,
        "status": ("valid_candidate_anomaly" if anomaly_observed else "valid_no_impact") if valid else "rejected",
        "rejected_reason_codes": sorted(key for key, value in gates.items() if not value),
    }


def build_p5_report(*, plans: Iterable[Mapping[str, Any]], evaluations: Iterable[Mapping[str, Any]] = (), issue_drafts: Iterable[Mapping[str, Any]] = (), costs: Mapping[str, Any] | None = None, real_evidence: bool = False, canary_evidence: Iterable[Mapping[str, Any]] = ()) -> dict[str, Any]:
    plan_rows = [dict(item) for item in plans if isinstance(item, Mapping)]
    eval_rows = [dict(item) for item in evaluations if isinstance(item, Mapping)]
    drafts = [dict(item) for item in issue_drafts if isinstance(item, Mapping)]
    canaries = [dict(item) for item in canary_evidence if isinstance(item, Mapping)]
    valid_canaries = [item for item in canaries if item.get("evidence_valid") is True and item.get("claim_scope") == "real_runtime"]
    if real_evidence and not valid_canaries:
        raise ValueError("real_evidence requires at least one validated real canary")
    status_counts: Counter[str] = Counter()
    for plan in plan_rows:
        for key, value in (plan.get("status_counts") or {}).items():
            status_counts[str(key)] += int(value)
    report = {
        "schema_version": "chaosatlas-p5-report-v1",
        "created_at": _now(),
        "claim_scope": "real_runtime" if real_evidence else "planned",
        "evidence_status": "real_evidence" if real_evidence else "implementation_and_read_only_only",
        "project_count": len(plan_rows),
        "capability_denominator": sum(int((item.get("denominators") or {}).get("all_capabilities") or 0) for item in plan_rows),
        "status_counts": dict(sorted(status_counts.items())),
        "evaluation_count": len(eval_rows),
        "canary_count": len(canaries),
        "validated_real_canary_count": len(valid_canaries),
        "issue_draft_count": len(drafts),
        "eligible_issue_draft_count": sum(item.get("status") == "pending_human_review" for item in drafts),
        "gates": {
            "real_fault_execution": bool(real_evidence and valid_canaries),
            "issue_drafts_require_all_gates": True,
            "blocked_inapplicable_unsupported_preserved": True,
        },
        "plans": [{"project_id": item.get("project_id"), "plan_sha256": item.get("plan_sha256"), "status_counts": item.get("status_counts")} for item in plan_rows],
        "canaries": [{"project_id": item.get("project_id"), "source_ref": item.get("source_ref"), "status": item.get("status"), "evidence_valid": item.get("evidence_valid")} for item in canaries],
        "cost": deepcopy(dict(costs)) if isinstance(costs, Mapping) else summarize_cost(),
    }
    report["report_sha256"] = _hash({key: value for key, value in report.items() if key != "created_at"})
    return report


class P5RunCoordinator:
    """Thin P5 adapter over the existing unified ``RunEngine``.

    The coordinator owns no executor and no second lifecycle.  It only applies
    the P5 approval gate, invokes the unified ``run`` entry point, and
    records blocked requests when a frozen Oracle is not available.
    """

    def __init__(self, engine: Any) -> None:
        if not hasattr(engine, "run"):
            raise TypeError("engine must expose run(request)")
        self.engine = engine

    def run(self, plan: Mapping[str, Any], requests: Iterable[Any], *, approved_oracle: bool = False) -> dict[str, Any]:
        if not isinstance(plan, Mapping) or plan.get("schema_version") != P5_SCHEMA:
            raise ValueError("a P5 experiment plan is required")
        results: list[dict[str, Any]] = []
        for request in requests:
            mode = str(getattr(request, "mode", "dry-run"))
            candidate_id = getattr(request, "candidate_id", None)
            if mode == "live" and (
                not approved_oracle
                or not isinstance(plan.get("oracle_ref"), Mapping)
                or plan["oracle_ref"].get("status") != "frozen"
                or getattr(request, "oracle_approval_dir", None) is None
            ):
                results.append({
                    "candidate_id": candidate_id,
                    "status": "blocked_oracle_approval",
                    "claim_scope": "planned",
                    "injection_performed": False,
                })
                continue
            outcome = self.engine.run(request)
            if isinstance(outcome, Mapping):
                row = dict(outcome)
                row.setdefault("claim_scope", "real_runtime" if row.get("injection_performed") is True else "planned")
                results.append(row)
            else:
                results.append({"candidate_id": candidate_id, "status": "method_invalid", "claim_scope": "planned"})
        return {
            "schema_version": "chaosatlas-p5-run-results-v1",
            "project_id": plan.get("project_id"),
            "claim_scope": "real_runtime" if any(item.get("claim_scope") == "real_runtime" for item in results) else "planned",
            "results": results,
            "executed_count": sum(item.get("injection_performed") is True for item in results),
            "blocked_count": sum(str(item.get("status", "")).startswith("blocked") for item in results),
        }
