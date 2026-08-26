"""Deterministic, read-only quality and policy-shadow evaluation for registries."""

from __future__ import annotations

import hashlib
import json
from typing import Any


REQUIRED_KINDS = ("architecture", "configuration", "dependency", "runtime", "defense")
REQUIRED_FIELDS = (
    "hypothesis_id",
    "kind",
    "target",
    "mechanism",
    "preconditions",
    "expected_observations",
    "falsifiers",
    "required_evidence",
    "priority_score",
    "execution_eligible",
    "claim_scope",
)
FORBIDDEN_FIELDS = {
    "weakness_status",
    "runtime_verdict",
    "rca_status",
    "knowledge_status",
    "final_verdict",
    "classification",
    "defense_status",
    "promotion_allowed",
}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _error(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _walk_keys(value: Any, path: str = "$") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_FIELDS:
                found.append((key, f"{path}.{key}"))
            found.extend(_walk_keys(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_walk_keys(child, f"{path}[{index}]"))
    return found


def _candidate_ids(candidate_space: dict[str, Any]) -> list[str]:
    return [
        str(item.get("candidate_id"))
        for item in candidate_space.get("candidates") or []
        if isinstance(item, dict) and item.get("candidate_id")
    ]


def _base_payload(registry: dict[str, Any], candidate_space: dict[str, Any], execution_budget: int) -> dict[str, Any]:
    return {
        "registry": registry,
        "candidate_space": candidate_space,
        "execution_budget": execution_budget,
    }


def evaluate_registry_quality(
    registry: dict[str, Any],
    candidate_space: dict[str, Any],
    *,
    execution_budget: int = 1,
) -> dict[str, Any]:
    """Validate advisory registry completeness without making runtime claims."""
    errors: list[dict[str, str]] = []
    hypotheses = registry.get("hypotheses") if isinstance(registry, dict) else None
    if not isinstance(hypotheses, list):
        hypotheses = []
        errors.append(_error("hypotheses_not_list", "$.hypotheses", "hypotheses must be a list"))
    candidate_ids = _candidate_ids(candidate_space if isinstance(candidate_space, dict) else {})
    candidate_set = set(candidate_ids)
    observed_kinds = sorted({str(item.get("kind")) for item in hypotheses if isinstance(item, dict) and item.get("kind")})
    missing_kinds = sorted(set(REQUIRED_KINDS) - set(observed_kinds))
    if missing_kinds:
        errors.append(_error("missing_hypothesis_kind", "$.hypotheses", ", ".join(missing_kinds)))

    ids: list[str] = []
    duplicate_ids: set[str] = set()
    missing_fields: list[str] = []
    non_advisory: list[str] = []
    non_runtime_executable: list[str] = []
    runtime_ids: list[str] = []
    forbidden: list[tuple[str, str]] = _walk_keys(registry)
    for index, item in enumerate(hypotheses):
        path = f"$.hypotheses[{index}]"
        if not isinstance(item, dict):
            errors.append(_error("hypothesis_not_object", path, "hypothesis must be an object"))
            continue
        hypothesis_id = str(item.get("hypothesis_id") or "")
        if hypothesis_id:
            if hypothesis_id in ids:
                duplicate_ids.add(hypothesis_id)
            ids.append(hypothesis_id)
        for field in REQUIRED_FIELDS:
            if field not in item:
                missing_fields.append(f"{path}.{field}")
        if item.get("claim_scope") != "advisory":
            non_advisory.append(path)
        kind = str(item.get("kind") or "")
        executable = item.get("execution_eligible") is True
        if kind == "runtime":
            candidate_id = str(item.get("candidate_id") or "")
            if candidate_id:
                runtime_ids.append(candidate_id)
                if candidate_id not in candidate_set:
                    errors.append(_error("unknown_runtime_candidate", f"{path}.candidate_id", candidate_id))
            else:
                errors.append(_error("runtime_candidate_missing", f"{path}.candidate_id", "runtime hypothesis requires candidate_id"))
        elif executable:
            non_runtime_executable.append(path)

    for field_path in missing_fields:
        errors.append(_error("missing_required_field", field_path, "required registry field is missing"))
    for hypothesis_id in sorted(duplicate_ids):
        errors.append(_error("duplicate_hypothesis_id", "$.hypotheses", hypothesis_id))
    for path in non_advisory:
        errors.append(_error("non_advisory_claim_scope", path, "registry entries must use claim_scope=advisory"))
    for path in non_runtime_executable:
        errors.append(_error("static_hypothesis_executable", path, "only runtime hypotheses may be execution eligible"))
    for key, path in forbidden:
        errors.append(_error("forbidden_conclusion_field", path, key))

    runtime_unique = sorted(set(runtime_ids))
    intersection = sorted(set(runtime_unique) & candidate_set)
    registry_only = sorted(set(runtime_unique) - candidate_set)
    candidate_only = sorted(candidate_set - set(runtime_unique))
    if candidate_only:
        errors.append(_error("candidate_without_runtime_hypothesis", "$.candidate_space.candidates", ", ".join(candidate_only)))
    eligible_count = sum(1 for item in hypotheses if isinstance(item, dict) and item.get("execution_eligible") is True)
    if isinstance(execution_budget, bool) or not isinstance(execution_budget, int) or execution_budget < 0:
        errors.append(_error("invalid_execution_budget", "$.execution_budget", "execution budget must be a non-negative integer"))
        execution_budget = 0
    checks = {
        "required_kinds": {"expected": list(REQUIRED_KINDS), "observed": observed_kinds, "missing": missing_kinds},
        "required_fields": {"missing": sorted(missing_fields), "complete": not missing_fields},
        "hypothesis_ids": {"count": len(ids), "unique": not duplicate_ids, "duplicate_ids": sorted(duplicate_ids)},
        "claim_scope": {"registry": registry.get("claim_scope"), "all_advisory": registry.get("claim_scope") == "advisory" and not non_advisory},
        "forbidden_fields": {"count": len(forbidden), "clear": not forbidden},
        "runtime_candidate_overlap": {
            "registry_runtime_ids": runtime_unique,
            "candidate_pool_ids": sorted(candidate_set),
            "intersection": intersection,
            "registry_only": registry_only,
            "candidate_only": candidate_only,
        },
        "execution_budget": {"execution_eligible_count": eligible_count, "execution_budget": execution_budget},
    }
    errors.sort(key=lambda item: (item["code"], item["path"], item["message"]))
    return {
        "schema_version": "chaosatlas-registry-quality-v1",
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "checks": checks,
        "hypothesis_count": len(hypotheses),
        "execution_eligible_count": eligible_count,
        "claim_scope": "advisory",
        "input_sha256": _hash(_base_payload(registry, candidate_space, execution_budget)),
    }


def build_registry_shadow(
    registry: dict[str, Any],
    candidate_space: dict[str, Any],
    *,
    legacy_order: list[str] | None = None,
    top_k: int = 1,
    execution_budget: int = 1,
) -> dict[str, Any]:
    """Compare legacy and registry runtime-only orderings without selecting live work."""
    quality = evaluate_registry_quality(registry, candidate_space, execution_budget=execution_budget)
    known = set(_candidate_ids(candidate_space))
    if legacy_order is None:
        legacy_order = _candidate_ids(candidate_space)
    legacy_ids = [str(item) for item in legacy_order if str(item) in known]
    hypotheses = registry.get("hypotheses") if isinstance(registry, dict) else []
    runtime = [
        item for item in hypotheses or []
        if isinstance(item, dict)
        and item.get("kind") == "runtime"
        and item.get("execution_eligible") is True
        and str(item.get("candidate_id") or "") in known
    ]
    runtime.sort(key=lambda item: (-int(item.get("priority_score") or 0), str(item.get("hypothesis_id") or "")))
    registry_ids: list[str] = []
    for item in runtime:
        candidate_id = str(item.get("candidate_id"))
        if candidate_id not in registry_ids:
            registry_ids.append(candidate_id)
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 0:
        top_k = 0
    legacy_selected = legacy_ids[:top_k]
    registry_selected = registry_ids[:top_k]
    common = [item for item in legacy_selected if item in registry_selected]
    legacy_only = [item for item in legacy_selected if item not in registry_selected]
    registry_only = [item for item in registry_selected if item not in legacy_selected]
    payload = {
        "schema_version": "chaosatlas-registry-policy-shadow-v1",
        "status": quality["status"],
        "quality_status": quality["status"],
        "quality_errors": quality["errors"],
        "legacy_candidate_ids": legacy_ids,
        "registry_candidate_ids": registry_ids,
        "legacy_selected_candidate_ids": legacy_selected,
        "registry_selected_candidate_ids": registry_selected,
        "common_candidate_ids": common,
        "legacy_only_candidate_ids": legacy_only,
        "registry_only_candidate_ids": registry_only,
        "selection_changed": legacy_selected != registry_selected,
        "top_k": top_k,
        "execution_budget": execution_budget,
        "runtime_hypothesis_count": len(runtime),
        "static_hypothesis_count": sum(1 for item in hypotheses or [] if isinstance(item, dict) and item.get("kind") != "runtime"),
        "mutation_executed": False,
        "policy_state_updated": False,
        "formal_knowledge_written": False,
        "claim_scope": "advisory",
    }
    payload["input_sha256"] = _hash({"registry": registry, "candidate_space": candidate_space, "legacy_order": legacy_ids, "top_k": top_k, "execution_budget": execution_budget})
    return payload
