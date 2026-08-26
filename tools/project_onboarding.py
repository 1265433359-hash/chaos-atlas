"""Phase-0 project onboarding and result-claim contract helpers.

This module is deliberately side-effect free. It validates a project profile,
normalizes its relative paths, and translates existing gate/classifier labels
into claims that are safe for downstream knowledge tooling.
"""

from __future__ import annotations

import copy
import argparse
import json
import re
from pathlib import Path
from typing import Any


PROFILE_SCHEMA_VERSION = "chaosatlas-project-profile-v1"
RESULTS = {
    "method_invalid",
    "environment_blocked",
    "target_not_found",
    "business_not_reachable",
    "injection_not_confirmed",
    "effect_unobserved",
    "response_preserved",
    "degraded",
    "weakness",
    "recovery_timeout",
    "defended",
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
_SAFE_NAMESPACES = {"default", "kube-system", "kube-public", "kube-node-lease"}
_GIT_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def _relative_path_errors(value: Any, field: str) -> list[str]:
    if not isinstance(value, str) or not value.strip():
        return [f"{field} must contain non-empty relative paths"]
    normalized = value.strip().replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        return [f"{field} must contain relative paths"]
    if any(part == ".." for part in normalized.split("/")):
        return [f"{field} must not contain parent path segments"]
    return []


def _normalize_paths(profile: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(profile)
    source = normalized.get("source") or {}
    for key in ("manifest_roots", "source_roots"):
        values = source.get(key) or []
        source[key] = [str(value).strip().replace("\\", "/") for value in values]
    normalized["source"] = source
    policy = normalized.get("namespace_policy") or {}
    policy["allowed_namespaces"] = [str(value).strip() for value in policy.get("allowed_namespaces") or []]
    normalized["namespace_policy"] = policy
    return normalized


def validate_project_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a side-effect-free project onboarding profile."""

    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(profile, dict):
        return {"valid": False, "profile": {}, "errors": ["profile must be an object"], "warnings": []}

    normalized = _normalize_paths(profile)
    if normalized.get("schema_version") != PROFILE_SCHEMA_VERSION:
        errors.append(f"schema_version must be {PROFILE_SCHEMA_VERSION}")
    if not str(normalized.get("project_id") or "").strip():
        errors.append("project_id is required")
    commit = str(normalized.get("project_commit") or "").strip()
    if not commit:
        errors.append("project_commit is required")
    elif normalized.get("revision_kind") == "git" and not _GIT_COMMIT_RE.fullmatch(commit):
        errors.append("project_commit must be a 40-character hexadecimal commit")
    elif normalized.get("revision_kind") not in {"git", "fixture", "digest"}:
        errors.append("revision_kind must be git, fixture or digest")

    policy = normalized.get("namespace_policy")
    if not isinstance(policy, dict):
        errors.append("namespace_policy is required")
        policy = {}
    namespaces = policy.get("allowed_namespaces")
    if not isinstance(namespaces, list) or not namespaces or any(not str(value).strip() for value in namespaces):
        errors.append("namespace_policy.allowed_namespaces must be a non-empty list")
    elif any(str(value).strip() in _SAFE_NAMESPACES for value in namespaces):
        errors.append("namespace_policy.allowed_namespaces cannot include default")
    if policy.get("isolation_required") is not True:
        errors.append("namespace_policy.isolation_required must be true")

    source = normalized.get("source")
    if not isinstance(source, dict):
        errors.append("source is required")
        source = {}
    for key in ("manifest_roots", "source_roots"):
        values = source.get(key)
        if not isinstance(values, list) or not values:
            errors.append(f"source.{key} must be a non-empty list")
            continue
        for value in values:
            errors.extend(_relative_path_errors(value, f"source.{key}"))

    oracles = normalized.get("business_oracles")
    if not isinstance(oracles, list) or not oracles:
        errors.append("business_oracles must contain at least one oracle")
    else:
        oracle_ids: set[str] = set()
        for oracle in oracles:
            if not isinstance(oracle, dict):
                errors.append("business_oracles entries must be objects")
                continue
            oracle_id = str(oracle.get("id") or "").strip()
            if not oracle_id or oracle_id in oracle_ids:
                errors.append("business_oracles ids must be non-empty and unique")
            oracle_ids.add(oracle_id)
            for key in ("kind", "entrypoint", "success_contract"):
                if not str(oracle.get(key) or "").strip():
                    errors.append(f"business_oracles.{key} is required")

    observability = normalized.get("observability")
    if not isinstance(observability, dict):
        errors.append("observability is required")
    else:
        for key in ("logs", "events"):
            if not isinstance(observability.get(key), dict):
                errors.append(f"observability.{key} is required")

    recovery = normalized.get("recovery")
    if not isinstance(recovery, dict):
        errors.append("recovery is required")
    else:
        deadline = recovery.get("deadline_s")
        if not isinstance(deadline, (int, float)) or deadline <= 0:
            errors.append("recovery.deadline_s must be positive")
        if recovery.get("require_business_probe") is not True:
            errors.append("recovery.require_business_probe must be true")
        if recovery.get("require_cleanup") is not True:
            errors.append("recovery.require_cleanup must be true")

    cleanup = normalized.get("cleanup")
    if not isinstance(cleanup, dict) or not str(cleanup.get("owner") or "").strip() or cleanup.get("must_be_empty") is not True:
        errors.append("cleanup must define owner and must_be_empty=true")
    improvement = normalized.get("improvement_policy")
    if improvement is not None:
        if not isinstance(improvement, dict):
            errors.append("improvement_policy must be an object")
        else:
            fresh_namespace = str(improvement.get("fresh_namespace") or "").strip()
            if not fresh_namespace:
                errors.append("improvement_policy.fresh_namespace is required")
            elif fresh_namespace in set(policy.get("allowed_namespaces") or []):
                errors.append("improvement_policy.fresh_namespace must be isolated")
            elif fresh_namespace in _SAFE_NAMESPACES or not re.fullmatch(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?", fresh_namespace):
                errors.append("improvement_policy.fresh_namespace is not a safe namespace")
            errors.extend(_relative_path_errors(improvement.get("manifest_source"), "improvement_policy.manifest_source"))
            if improvement.get("source_copy_required") is not True:
                errors.append("improvement_policy.source_copy_required must be true")
    sensitive = normalized.get("sensitive_data_policy")
    if not isinstance(sensitive, dict) or not isinstance(sensitive.get("redact_fields"), list):
        errors.append("sensitive_data_policy.redact_fields is required")

    return {"valid": not errors, "profile": normalized, "errors": sorted(set(errors)), "warnings": warnings}


def inspect_profile_inputs(profile: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    """Check that declared local inputs exist without contacting a cluster."""

    schema = validate_project_profile(profile)
    errors = list(schema["errors"])
    checked: list[dict[str, Any]] = []
    source = schema.get("profile", {}).get("source", {})
    for field in ("manifest_roots", "source_roots"):
        for relative in source.get(field, []):
            path = (workspace_root / relative).resolve()
            inside_root = path == workspace_root.resolve() or workspace_root.resolve() in path.parents
            exists = inside_root and path.exists()
            checked.append({"field": field, "path": relative, "exists": exists})
            if not inside_root:
                errors.append(f"{field} escapes workspace root: {relative}")
            elif not exists:
                errors.append(f"{field} does not exist: {relative}")
    return {
        "status": "ready_for_static_analysis" if not errors else "incomplete",
        "valid": not errors,
        "profile": schema.get("profile", {}),
        "checked_inputs": checked,
        "errors": sorted(set(errors)),
        "warnings": schema.get("warnings", []),
        "runtime": "not_checked",
    }


def _result_for_classification(classification: str, gate: dict[str, Any] | None = None) -> str:
    if classification in {"platform_or_preflight_blocked", "apply_failed", "runner_error"}:
        return "environment_blocked"
    if classification in {"not_applicable"}:
        checks = (gate or {}).get("checks") or {}
        return "target_not_found" if checks.get("selector_matches") is False else "business_not_reachable"
    if classification in {"invalid_not_injected", "injection_not_confirmed"}:
        return "injection_not_confirmed"
    if classification in {"response_observed"}:
        return "response_preserved"
    if classification in {"response_preserved_latency_degradation", "transport_or_observation_error"}:
        return "degraded" if classification.startswith("response_preserved") else "effect_unobserved"
    if classification in {"client_timeout_observed", "server_error_observed", "response_contract_changed"}:
        return "weakness"
    return "effect_unobserved"


def validate_result_contract(record: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    result = record.get("result")
    if result not in RESULTS:
        errors.append(f"unsupported result: {result}")
    if not str(record.get("claim_scope") or "").strip():
        errors.append("claim_scope is required")
    evidence = record.get("evidence_refs")
    if not isinstance(evidence, list):
        errors.append("evidence_refs must be a list")
        evidence = []
    next_evidence = record.get("next_evidence")
    if not isinstance(next_evidence, list):
        errors.append("next_evidence must be a list")
    if result == "defended":
        if record.get("injection_confirmed") is not True:
            errors.append("defended requires confirmed injection")
        if not evidence:
            errors.append("defended requires evidence_refs")
        if record.get("recovery_confirmed") is not True:
            errors.append("defended requires confirmed recovery")
        if record.get("cleanup_confirmed") is not True:
            errors.append("defended requires confirmed cleanup")
        if record.get("defense_claim_type") not in DEFENSE_CLAIM_TYPES:
            errors.append("defended requires a supported defense_claim_type")
        defense_evidence = record.get("defense_evidence")
        if not isinstance(defense_evidence, dict):
            errors.append("defended requires defense_evidence")
        else:
            for field in ("mechanism_evidence", "independent_oracle", "observation_window"):
                if defense_evidence.get(field) is not True:
                    errors.append(f"defended requires {field}")
    if result in {"response_preserved", "degraded"}:
        record = {**record, "defense_claim_allowed": False}
    return {"valid": not errors, **record, "errors": sorted(set(errors))}


def result_contract_from_classification(
    classification: str,
    *,
    claim_scope: str,
    evidence_refs: list[str] | None = None,
    injected: bool = False,
    recovered: bool = False,
    cleanup_confirmed: bool | None = None,
    defense_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = _result_for_classification(classification)
    defense = defense_evidence if isinstance(defense_evidence, dict) else {}
    defense_claim_type = str(defense.get("claim_type") or "").strip()
    defense_complete = (
        result in {"response_preserved", "degraded"}
        and defense_claim_type in DEFENSE_CLAIM_TYPES
        and bool(injected)
        and bool(recovered)
        and cleanup_confirmed is True
        and all(defense.get(field) is True for field in ("mechanism_evidence", "independent_oracle", "observation_window"))
    )
    if defense_complete:
        result = "defended"
    record = {
        "result": result,
        "claim_scope": claim_scope,
        "evidence_refs": list(evidence_refs or []),
        "next_evidence": [] if result == "defended" else ["collect_mechanism_and_independent_oracle_evidence"],
        "injection_confirmed": bool(injected),
        "recovery_confirmed": bool(recovered),
        "cleanup_confirmed": cleanup_confirmed is True,
        "defense_claim_allowed": defense_complete,
    }
    if defense_complete:
        record["defense_claim_type"] = defense_claim_type
        record["defense_evidence"] = dict(defense)
    return validate_result_contract(record)


def result_contract_from_gate(gate: dict[str, Any]) -> dict[str, Any]:
    decision = str(gate.get("decision") or "")
    if decision == "blocked":
        result = "environment_blocked"
    elif decision == "not_applicable":
        result = "target_not_found" if (gate.get("checks") or {}).get("selector_matches") is False else "business_not_reachable"
    elif decision == "ready_for_injection":
        result = "effect_unobserved"
    else:
        result = "method_invalid"
    record = {
        "result": result,
        "claim_scope": f"{gate.get('kind') or 'mutation'}:{gate.get('name') or 'unknown'}",
        "evidence_refs": [],
        "reason_codes": [str(value) for value in gate.get("errors") or []],
        "next_evidence": ["confirm_target_and_injection"] if decision != "ready_for_injection" else ["execute_with_runtime_oracle"],
        "injection_confirmed": False,
        "recovery_confirmed": False,
        "cleanup_confirmed": False,
        "defense_claim_allowed": False,
    }
    return validate_result_contract(record)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        profile = json.loads(args.profile.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"valid": False, "status": "incomplete", "errors": [str(exc)]}, ensure_ascii=True))
        return 1
    report = inspect_profile_inputs(profile, args.workspace_root)
    print(json.dumps(report, indent=2, ensure_ascii=True, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
