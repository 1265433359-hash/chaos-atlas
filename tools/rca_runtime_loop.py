"""Execute one safe RCA action and feed its result back into the RCA loop.

The default mode is offline ``dry_run``.  Live execution is dependency-injected
through a callable and requires an explicit gate, so this module never shells
out to kubectl, Docker, an external model or the network by itself.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import sys
from typing import Any, Callable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.compile_rca_regression import compile_regression_intents, project_knowledge_draft
from tools.evidence_collectors import (
    collect_file_evidence,
    collect_unavailable_evidence,
)
from tools.rca_loop import (
    NON_EVIDENT_OUTCOMES,
    _contains_sensitive_value,
    _path_errors,
    claim_level_for_status,
    evaluate_knowledge_promotion,
    evaluate_rca_transition,
    make_evidence,
    plan_next_action,
    score_action,
    sha256_json,
)
from tools.sock_shop_rca import actions_for_case
from tools.validate_rca_loop import validate_artifact


SCHEMA_VERSION = "chaosatlas-rca-runtime-loop-v1"
ATTESTATION_SCHEMA_VERSION = "chaosatlas-runtime-result-v1"
ActionExecutor = Callable[[dict[str, Any]], dict[str, Any]]
_RUNTIME_BOOL_FIELDS = (
    "discriminating_action",
    "high_severity_contradiction",
    "lifecycle_complete",
    "direct_evidence",
    "applicability_complete",
    "regression_complete",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_filename(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip("-")
    if not normalized or normalized in {".", ".."}:
        raise ValueError("action_id cannot produce a safe filename")
    return normalized


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable artifact {path}")
    text = json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True) + "\n"
    if _contains_sensitive_value(text):
        raise ValueError(f"refusing to write sensitive values into {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _strict_bool(value: Any, *, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


def _strict_int(value: Any, *, default: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return value


def _executor_metadata_errors(result: dict[str, Any]) -> list[str]:
    errors = [
        f"{field}_must_be_boolean"
        for field in _RUNTIME_BOOL_FIELDS
        if field in result and not isinstance(result[field], bool)
    ]
    for field in ("valid_reproductions", "valid_counterfactuals"):
        if field in result and (
            isinstance(result[field], bool) or not isinstance(result[field], int)
        ):
            errors.append(f"{field}_must_be_integer")
    return errors


def _valid_attestation(result: dict[str, Any]) -> bool:
    attestation = result.get("attestation")
    return (
        isinstance(attestation, dict)
        and attestation.get("schema_version") == ATTESTATION_SCHEMA_VERSION
        and attestation.get("valid") is True
        and attestation.get("comparison_eligible") is True
        and all(attestation.get(field) is True for field in (
            "baseline",
            "injection",
            "observation",
            "recovery",
            "cleanup",
            "independent_oracle",
        ))
    )


def _action_errors(
    action: dict[str, Any],
    available_preconditions: set[str],
) -> tuple[list[str], list[str]]:
    errors = list(score_action(action).get("errors", []))
    for field in ("target_scope", "stop_conditions"):
        if not action.get(field):
            errors.append(f"{field}_required")
    missing = sorted(set(action.get("preconditions") or []) - available_preconditions)
    if _path_errors(str(action.get("action_id") or "")):
        errors.append("unsafe_action_id")
    return sorted(set(errors)), missing


def collect_action_evidence(
    *,
    root: Path,
    requests: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Collect declared evidence requests without executing runtime actions."""

    collected: list[dict[str, Any]] = []
    for request in requests:
        if not isinstance(request, dict):
            raise ValueError("evidence requests must be objects")
        common = {
            "root": root,
            "source_ref": str(request.get("source_ref") or ""),
            "evidence_id": str(request.get("evidence_id") or ""),
            "kind": str(request.get("kind") or ""),
            "claim_scope": str(request.get("claim_scope") or ""),
        }
        if request.get("available") is False:
            evidence = collect_unavailable_evidence(
                **common,
                reason=str(request.get("unavailable_reason") or "collector_unavailable"),
                window=request.get("window"),
            )
        else:
            evidence = collect_file_evidence(
                **common,
                interpretation=str(request.get("interpretation") or ""),
                polarity=str(request.get("polarity") or "supports"),
                satisfies=request.get("satisfies") or [],
                window=request.get("window"),
            )
        if request.get("span") is not None:
            evidence["span"] = deepcopy(request["span"])
        collected.append(evidence)
    return collected


def _result_path(output_root: Path, action_id: str) -> tuple[Path, str]:
    name = _safe_filename(action_id) + ".json"
    return output_root / "actions" / name, f"actions/{name}"


def _normalize_result_evidence(
    *,
    action: dict[str, Any],
    raw_result: dict[str, Any],
    action_ref: str,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    raw_evidence = raw_result.get("evidence", [])
    if not isinstance(raw_evidence, list):
        raise ValueError("executor result evidence must be a list")

    for index, item in enumerate(raw_evidence, start=1):
        if not isinstance(item, dict):
            raise ValueError("executor result evidence entries must be objects")
        source_ref = str(item.get("source_ref") or action_ref).replace("\\", "/")
        if _path_errors(source_ref):
            raise ValueError(f"unsafe evidence source_ref: {source_ref}")
        satisfies = item.get("satisfies", [])
        if not isinstance(satisfies, list) or not all(isinstance(value, str) for value in satisfies):
            raise ValueError("evidence satisfies must be a list of strings")
        evidence = make_evidence(
            evidence_id=str(item.get("evidence_id") or f"EV-{action['action_id']}-{index}"),
            kind=str(item.get("kind") or action["output_schema"]),
            polarity=str(item.get("polarity") or "neutral"),
            claim_scope=str(item.get("claim_scope") or action["target_scope"]),
            source_ref=source_ref,
            interpretation=str(item.get("interpretation") or "executor returned no interpretation"),
            sha256=item.get("sha256"),
            window=item.get("window") or {},
        )
        if item.get("collected_at"):
            evidence["collected_at"] = str(item["collected_at"])
        for field in ("hypothesis_id", "severity", "satisfies"):
            if field in item:
                evidence[field] = satisfies if field == "satisfies" else item[field]
        normalized.append(evidence)
    return normalized


def execute_selected_action(
    *,
    case: dict[str, Any],
    action: dict[str, Any],
    output_root: Path,
    available_preconditions: set[str],
    executor: ActionExecutor | None = None,
    dry_run: bool = True,
    allow_live: bool = False,
) -> dict[str, Any]:
    """Validate and execute one action, writing one immutable action result."""

    output_root = Path(output_root)
    action_id = str(action.get("action_id") or "")
    path, action_ref = _result_path(output_root, action_id)
    errors, missing = _action_errors(action, set(available_preconditions))
    base: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "action_id": action_id,
        "weakness_id": case.get("weakness_id"),
        "round_id": case.get("round_id"),
        "target_scope": action.get("target_scope"),
        "output_schema": action.get("output_schema"),
        "preconditions": list(action.get("preconditions") or []),
        "cleanup": list(action.get("cleanup") or []),
        "action_ref": action_ref,
        "collected_at": _now(),
    }

    if errors or missing:
        result = {
            **base,
            "status": "blocked",
            "reason": "invalid_action_contract" if errors else "missing_preconditions",
            "errors": errors,
            "missing_preconditions": missing,
            "evidence": [],
        }
        _write_json(path, result)
        return result

    if not dry_run and not allow_live:
        result = {
            **base,
            "status": "blocked",
            "reason": "live_execution_gate_required",
            "errors": [],
            "missing_preconditions": [],
            "evidence": [],
        }
        _write_json(path, result)
        return result

    if dry_run:
        raw_result = {
            "status": "dry_run",
            "evidence": [
                {
                    "evidence_id": f"EV-{action_id}-UNAVAILABLE",
                    "kind": "dry_run",
                    "polarity": "unavailable",
                    "claim_scope": action["target_scope"],
                    "source_ref": action_ref,
                    "interpretation": (
                        "dry-run validated the action contract but did not execute "
                        "the action; runtime evidence is unavailable"
                    ),
                    "satisfies": [],
                }
            ],
        }
    else:
        if executor is None:
            result = {
                **base,
                "status": "blocked",
                "reason": "live_executor_required",
                "errors": [],
                "missing_preconditions": [],
                "evidence": [],
            }
            _write_json(path, result)
            return result
        try:
            raw_result = executor(deepcopy(action))
        except Exception as error:
            result = {
                **base,
                "status": "blocked",
                "reason": "executor_failed",
                "errors": [type(error).__name__ + ": " + str(error)],
                "missing_preconditions": [],
                "evidence": [],
            }
            _write_json(path, result)
            return result
        if not isinstance(raw_result, dict):
            result = {
                **base,
                "status": "blocked",
                "reason": "executor_result_must_be_object",
                "errors": [],
                "missing_preconditions": [],
                "evidence": [],
            }
            _write_json(path, result)
            return result
        if _contains_sensitive_value(json.dumps(raw_result, ensure_ascii=True)):
            raise ValueError("executor result contains sensitive values")
        metadata_errors = _executor_metadata_errors(raw_result)
        if metadata_errors:
            result = {
                **base,
                "status": "blocked",
                "reason": "invalid_executor_metadata",
                "errors": metadata_errors,
                "missing_preconditions": [],
                "evidence": [],
            }
            _write_json(path, result)
            return result

    evidence = _normalize_result_evidence(
        action=action,
        raw_result=raw_result,
        action_ref=action_ref,
    )
    result = {
        **base,
        "status": "dry_run" if dry_run else "executed",
        "reason": "contract_checked_without_live_execution" if dry_run else "executor_completed",
        "outcome_status": "dry_run" if dry_run else str(raw_result.get("outcome_status") or "observed"),
        "errors": [],
        "missing_preconditions": [],
        "discriminating_action": _strict_bool(raw_result.get("discriminating_action")),
        "high_severity_contradiction": _strict_bool(raw_result.get("high_severity_contradiction")),
        "valid_reproductions": _strict_int(raw_result.get("valid_reproductions")),
        "valid_counterfactuals": _strict_int(raw_result.get("valid_counterfactuals")),
        "lifecycle_complete": _strict_bool(raw_result.get("lifecycle_complete")),
        "direct_evidence": _strict_bool(raw_result.get("direct_evidence")),
        "applicability_complete": _strict_bool(raw_result.get("applicability_complete")),
        "regression_complete": _strict_bool(raw_result.get("regression_complete")),
        "attestation": raw_result.get("attestation"),
        "evidence": evidence,
    }
    _write_json(path, result)
    return result


def _required_evidence_complete(hypothesis: dict[str, Any], evidence: list[dict[str, Any]]) -> bool:
    satisfied = {
        item
        for ev in evidence
        for item in (ev.get("satisfies") or [])
        if ev.get("polarity") == "supports"
    }
    return set(hypothesis.get("required_evidence") or []).issubset(satisfied)


def _hypothesis_evidence(
    hypothesis: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    hid = hypothesis.get("hypothesis_id")
    edge = str((hypothesis.get("scope") or {}).get("edge") or "")
    selected = []
    for item in evidence:
        if item.get("hypothesis_id") == hid:
            if item.get("claim_scope") == edge:
                selected.append(item)
        elif not item.get("hypothesis_id") and item.get("claim_scope") == edge:
            selected.append(item)
    return selected


def _case_scopes(case: dict[str, Any], action_result: dict[str, Any]) -> set[str]:
    scopes = {
        str(case.get("test_node", {}).get("target_role") or ""),
        str(action_result.get("target_scope") or ""),
    }
    for hypothesis in case.get("hypotheses", []):
        scopes.add(str((hypothesis.get("scope") or {}).get("edge") or ""))
    return {scope for scope in scopes if scope}


def ingest_action_result(
    *,
    case: dict[str, Any],
    action_result: dict[str, Any],
) -> dict[str, Any]:
    """Append evidence and deterministically recompute RCA and knowledge state."""

    updated = deepcopy(case)
    result_status = action_result.get("status")
    outcome_status = action_result.get("outcome_status")
    discriminating_action = _strict_bool(action_result.get("discriminating_action"))
    high_severity_contradiction = _strict_bool(
        action_result.get("high_severity_contradiction")
    )
    if result_status == "dry_run":
        evidence = deepcopy(action_result.get("evidence") or [])
        existing_ids = {item.get("evidence_id") for item in updated.get("evidence_refs", [])}
        for item in evidence:
            if item.get("evidence_id") not in existing_ids:
                updated.setdefault("evidence_refs", []).append(item)
                existing_ids.add(item.get("evidence_id"))
        updated.setdefault("action_history", []).append(
            {
                "action_id": action_result.get("action_id"),
                "status": result_status,
                "action_ref": action_result.get("action_ref"),
                "evidence_ids": [item.get("evidence_id") for item in evidence],
            }
        )
        ignored = {"allowed": False, "reason": "dry_run_not_evidence"}
        updated.setdefault("rca_audit", []).append(
            {
                "action_id": action_result.get("action_id"),
                "ignored": True,
                "reason": ignored["reason"],
                "evidence_ids": [item.get("evidence_id") for item in evidence],
            }
        )
        updated["knowledge_promotion_audit"] = ignored
        return {
            "case": updated,
            "transition": {"allowed": False, "reason": ignored["reason"]},
            "promotion": ignored,
            "hypotheses": [],
        }

    if result_status != "executed" or outcome_status in NON_EVIDENT_OUTCOMES:
        updated.setdefault("action_history", []).append(
            {
                "action_id": action_result.get("action_id"),
                "status": result_status,
                "action_ref": action_result.get("action_ref"),
                "evidence_ids": [],
            }
        )
        ignored = {
            "allowed": False,
            "reason": (
                f"runtime_outcome_not_evidence:{outcome_status}"
                if outcome_status in NON_EVIDENT_OUTCOMES
                else "action_result_not_accepted"
            ),
        }
        updated.setdefault("rca_audit", []).append(
            {
                "action_id": action_result.get("action_id"),
                "ignored": True,
                "reason": ignored["reason"],
            }
        )
        updated["knowledge_promotion_audit"] = ignored
        return {
            "case": updated,
            "transition": {"allowed": False, "reason": "action_result_not_accepted"},
            "promotion": ignored,
            "hypotheses": [],
        }
    evidence = deepcopy(action_result.get("evidence") or [])
    scope_errors = [
        str(item.get("evidence_id"))
        for item in evidence
        if item.get("claim_scope") not in _case_scopes(updated, action_result)
    ]
    if scope_errors:
        updated.setdefault("action_history", []).append(
            {
                "action_id": action_result.get("action_id"),
                "status": result_status,
                "action_ref": action_result.get("action_ref"),
                "evidence_ids": [],
            }
        )
        ignored = {
            "allowed": False,
            "reason": "evidence_claim_scope_mismatch",
            "evidence_ids": scope_errors,
        }
        updated.setdefault("rca_audit", []).append(
            {
                "action_id": action_result.get("action_id"),
                "ignored": True,
                "reason": ignored["reason"],
                "evidence_ids": scope_errors,
            }
        )
        updated["knowledge_promotion_audit"] = ignored
        return {
            "case": updated,
            "transition": {"allowed": False, "reason": ignored["reason"]},
            "promotion": ignored,
            "hypotheses": [],
        }
    existing_ids = {item.get("evidence_id") for item in updated.get("evidence_refs", [])}
    for item in evidence:
        if item.get("evidence_id") not in existing_ids:
            updated.setdefault("evidence_refs", []).append(item)
            existing_ids.add(item.get("evidence_id"))

    hypotheses = updated.setdefault("hypotheses", [])
    hypothesis_audits: list[dict[str, Any]] = []
    for hypothesis in hypotheses:
        relevant = _hypothesis_evidence(hypothesis, evidence)
        all_relevant = _hypothesis_evidence(hypothesis, updated.get("evidence_refs", []))
        hypothesis.setdefault("evidence_for", [])
        hypothesis.setdefault("evidence_against", [])
        for item in relevant:
            evidence_id = item.get("evidence_id")
            if item.get("polarity") == "supports" and evidence_id not in hypothesis["evidence_for"]:
                hypothesis["evidence_for"].append(evidence_id)
            elif item.get("polarity") == "contradicts" and evidence_id not in hypothesis["evidence_against"]:
                hypothesis["evidence_against"].append(evidence_id)

        high_contradiction = high_severity_contradiction or any(
            item.get("polarity") == "contradicts" and item.get("severity", "high") == "high"
            for item in all_relevant
        )
        required_complete = _required_evidence_complete(hypothesis, all_relevant)
        supporting = len(hypothesis.get("evidence_for") or [])
        current = str(hypothesis.get("status") or "pending")
        if high_contradiction:
            target = "rejected"
        elif required_complete and discriminating_action:
            target = "confirmed"
        elif supporting:
            target = "bounded"
        else:
            target = current
        transition = evaluate_rca_transition(
            current=current,
            target=target,
            boundary_confirmed=bool(updated.get("symptom")),
            supporting_evidence=supporting,
            required_evidence_complete=required_complete,
            discriminating_action=discriminating_action,
            high_severity_contradiction=high_contradiction,
        )
        if transition.get("allowed") and transition.get("next_status"):
            hypothesis["status"] = transition["next_status"]
        hypothesis["confidence"] = round(
            (
                min(
                    supporting / max(1, supporting + len(hypothesis.get("evidence_against") or [])),
                    len(
                        {
                            item
                            for ev in all_relevant
                            for item in (ev.get("satisfies") or [])
                            if ev.get("polarity") == "supports"
                        }
                        & set(hypothesis.get("required_evidence") or [])
                    )
                    / max(1, len(hypothesis.get("required_evidence") or [])),
                )
                if hypothesis.get("required_evidence")
                else 0.0
            ),
            3,
        )
        hypothesis["claim_level"] = claim_level_for_status(
            str(hypothesis.get("status") or "pending"),
            str(hypothesis.get("mechanism_level") or ""),
        )
        hypothesis["unsupported_claims"] = [
            claim
            for claim in hypothesis.get("required_evidence", [])
            if claim not in {
                item
                for ev in all_relevant
                for item in (ev.get("satisfies") or [])
                if ev.get("polarity") == "supports"
            }
        ]
        if hypothesis["status"] in {"confirmed", "rejected"}:
            hypothesis["next_action"] = None
        hypothesis_audits.append(
            {
                "hypothesis_id": hypothesis.get("hypothesis_id"),
                "transition": transition,
                "required_evidence_complete": required_complete,
                "high_severity_contradiction": high_contradiction,
            }
        )

    statuses = [str(hypothesis.get("status")) for hypothesis in hypotheses]
    contradiction = high_severity_contradiction or any(
        hypothesis.get("evidence_against") for hypothesis in hypotheses
    )
    if contradiction and high_severity_contradiction:
        target_rca = "rejected"
    elif statuses and all(status == "confirmed" for status in statuses):
        target_rca = "confirmed"
    elif statuses and all(status == "rejected" for status in statuses):
        target_rca = "rejected"
    else:
        target_rca = "bounded"
    supports = sum(1 for item in evidence if item.get("polarity") == "supports")
    rca_transition = evaluate_rca_transition(
        current=str(updated.get("rca_status") or "pending"),
        target=target_rca,
        boundary_confirmed=bool(updated.get("symptom")),
        supporting_evidence=supports,
        required_evidence_complete=target_rca == "confirmed",
        discriminating_action=discriminating_action,
        high_severity_contradiction=high_severity_contradiction,
    )
    if rca_transition.get("allowed") and rca_transition.get("next_status"):
        updated["rca_status"] = rca_transition["next_status"]

    promotion_eligible = (
        result_status == "executed"
        and _valid_attestation(action_result)
        and bool(evidence)
    )
    direct_evidence = promotion_eligible and any(
        item.get("polarity") == "supports"
        and item.get("kind") in {"source_span", "manifest", "config", "config_facts"}
        for item in evidence
    )
    promotion = evaluate_knowledge_promotion(
        current=str(updated.get("knowledge_status") or "none"),
        weakness_status=str(updated.get("weakness_status") or "candidate"),
        rca_status=str(updated.get("rca_status") or "pending"),
        valid_reproductions=(
            _strict_int(action_result.get("valid_reproductions"))
            if promotion_eligible
            else 0
        ),
        valid_counterfactuals=(
            _strict_int(action_result.get("valid_counterfactuals"))
            if promotion_eligible
            else 0
        ),
        lifecycle_complete=promotion_eligible and _strict_bool(action_result.get("lifecycle_complete")),
        direct_evidence=direct_evidence,
        applicability_complete=promotion_eligible and _strict_bool(action_result.get("applicability_complete")),
        regression_complete=promotion_eligible and _strict_bool(action_result.get("regression_complete")),
        contradiction=contradiction,
    )
    if promotion.get("allowed") and promotion.get("next_status"):
        updated["knowledge_status"] = promotion["next_status"]

    updated.setdefault("action_history", []).append(
        {
            "action_id": action_result.get("action_id"),
            "status": action_result.get("status"),
            "action_ref": action_result.get("action_ref"),
            "evidence_ids": [item.get("evidence_id") for item in evidence],
        }
    )
    updated.setdefault("rca_audit", []).append(
        {
            "action_id": action_result.get("action_id"),
            "transition": rca_transition,
            "hypotheses": hypothesis_audits,
        }
    )
    updated["knowledge_promotion_audit"] = promotion
    return {
        "case": updated,
        "transition": rca_transition,
        "promotion": promotion,
        "hypotheses": hypothesis_audits,
    }


def _next_round_id(round_id: str) -> str:
    match = re.match(r"^(.*?)-r(\d+)$", str(round_id))
    if match:
        return f"{match.group(1)}-r{int(match.group(2)) + 1}"
    return f"{round_id}-next"


def _follow_up_plan(case: dict[str, Any], available_preconditions: set[str]) -> dict[str, Any]:
    completed = {
        str(item.get("action_id"))
        for item in case.get("action_history", [])
        if item.get("action_id") and item.get("status") in {"dry_run", "executed"}
    }
    actions = [
        action
        for action in actions_for_case(case, case.get("hypotheses", []))
        if str(action.get("action_id")) not in completed
    ]
    if case.get("knowledge_status") == "local_reusable":
        # Reusable knowledge must alter the next round's work. Prefer a
        # replay/counterfactual that tests the learned boundary; fall back to
        # ordinary evidence lookup only when no such action is currently safe.
        runtime_kinds = {
            "business_replay",
            "dependency_replay",
            "isolated_counterfactual",
            "boundary_probe",
        }
        reusable_actions = [
            action
            for action in actions
            if action.get("kind") in runtime_kinds
            and set(action.get("preconditions") or []).issubset(available_preconditions)
        ]
        if reusable_actions:
            actions = reusable_actions
    return plan_next_action(actions, available_preconditions=available_preconditions)


def advance_rca_loop(
    *,
    rca_root: Path,
    output_root: Path,
    available_preconditions: set[str],
    executor: ActionExecutor | None = None,
    dry_run: bool = True,
    allow_live: bool = False,
) -> dict[str, Any]:
    """Advance every case into a new immutable RCA round."""

    rca_root = Path(rca_root)
    output_root = Path(output_root)
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"output {output_root} already exists and is not empty")
    cases_root = rca_root / "cases"
    case_paths = sorted(cases_root.glob("*.json"))
    if not case_paths:
        raise ValueError(f"no cases found under {cases_root}")

    source_manifest = json.loads((rca_root / "manifest.json").read_text(encoding="utf-8"))
    round_id = _next_round_id(str(source_manifest.get("round_id") or "round-r1"))
    output_root.mkdir(parents=True, exist_ok=True)
    action_plans: list[dict[str, Any]] = []
    updated_cases: list[dict[str, Any]] = []

    for case_path in case_paths:
        case = json.loads(case_path.read_text(encoding="utf-8"))
        current_plan = _follow_up_plan(case, set(available_preconditions))
        action = current_plan.get("selected") or {}
        if not action:
            raise ValueError(
                f"case {case.get('weakness_id')} has no safe applicable action: "
                f"{current_plan.get('reason', 'planner returned no action')}"
            )
        case["round_id"] = round_id
        action_result = execute_selected_action(
            case=case,
            action=action,
            output_root=output_root,
            available_preconditions=available_preconditions,
            executor=executor,
            dry_run=dry_run,
            allow_live=allow_live,
        )
        ingested = ingest_action_result(case=case, action_result=action_result)
        updated = ingested["case"]
        updated["round_id"] = round_id
        follow_up = _follow_up_plan(updated, set(available_preconditions))
        updated["next_actions"] = [follow_up]
        for hypothesis in updated.get("hypotheses", []):
            if hypothesis.get("status") not in {"confirmed", "rejected"}:
                selected = follow_up.get("selected") or {}
                hypothesis["next_action"] = selected.get("action_id")
        updated_cases.append(updated)
        _write_json(output_root / "cases" / case_path.name, updated)
        for hypothesis in updated.get("hypotheses", []):
            _write_json(
                output_root / "hypotheses" / f"{hypothesis['hypothesis_id']}.json",
                hypothesis,
            )
        action_plans.append(
            {
                "weakness_id": updated.get("weakness_id"),
                "case_family": updated.get("case_family"),
                "plan": {
                    "status": follow_up.get("status"),
                    "selected": follow_up.get("selected"),
                    "rejected": follow_up.get("rejected", []),
                    "completed_action": action,
                    "result_ref": action_result.get("action_ref"),
                    "result_status": action_result.get("status"),
                    "transition": ingested["transition"],
                    "promotion": ingested["promotion"],
                },
            }
        )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "tool": "rca_runtime_loop",
        "project_id": source_manifest.get("project_id", "sock-shop"),
        "project_commit": source_manifest.get("project_commit"),
        "round_id": round_id,
        "parent_round_id": source_manifest.get("round_id"),
        "parent_manifest_sha256": sha256_json(source_manifest),
        "execution_mode": "dry_run" if dry_run else "live",
        "live_execution_allowed": bool(allow_live and not dry_run),
        "knowledge_base_updated": False,
        "case_statuses": [
            {
                "weakness_id": case.get("weakness_id"),
                "weakness_status": case.get("weakness_status"),
                "rca_status": case.get("rca_status"),
                "knowledge_status": case.get("knowledge_status"),
            }
            for case in updated_cases
        ],
    }
    _write_json(output_root / "manifest.json", manifest)
    _write_json(
        output_root / "action_plan.json",
            {
                "schema_version": SCHEMA_VERSION,
                "tool": "rca_runtime_loop",
                "round_id": round_id,
                "available_preconditions": sorted(available_preconditions),
                "case_plans": action_plans,
            },
        )

    # Carry forward immutable discovery inputs referenced by generated cases so
    # the new round remains self-contained for offline validation.
    discovery_root = rca_root / "discovery"
    if discovery_root.is_dir():
        for source_path in sorted(discovery_root.rglob("*")):
            if source_path.is_file():
                relative = source_path.relative_to(discovery_root)
                destination = output_root / "discovery" / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source_path, destination)

    drafts: list[dict[str, Any]] = []
    draft_root = output_root / "knowledge_drafts"
    for case in updated_cases:
        draft = project_knowledge_draft(
            case,
            case.get("hypotheses", []),
            case.get("next_actions", []),
        )
        drafts.append(draft)
        _write_json(draft_root / f"{draft['id']}.json", draft)
    _write_json(
        draft_root / "regression_intents.json",
        compile_regression_intents(drafts, snapshot={"cards": drafts}),
    )
    report = validate_artifact(output_root)
    _write_json(output_root / "validation_report.json", report)
    if not report["valid"]:
        raise ValueError("generated RCA round failed validation: " + "; ".join(report["errors"]))
    return {
        "status": "completed",
        "round_id": round_id,
        "manifest": manifest,
        "validation": report,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rca-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--live",
        action="store_true",
        help="reserved for a future runtime adapter; live execution is not available in this CLI",
    )
    args = parser.parse_args(argv)
    if args.live:
        parser.error("live execution requires an injected runtime executor through the Python API")
    result = advance_rca_loop(
        rca_root=args.rca_root,
        output_root=args.output,
        available_preconditions={
            "frozen_verdicts",
            "frozen_manifest",
            "captured_ready_samples",
            "captured_window",
        },
        dry_run=True,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "round_id": result["round_id"],
                "validation": result["validation"],
            },
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
