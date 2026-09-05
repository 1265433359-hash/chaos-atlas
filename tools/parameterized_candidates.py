"""Expand one runtime candidate into a bounded parameter ladder.

Parameter variants are distinct hypotheses for execution and reporting, while
the causal cluster remains shared across the same target and fault family.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from tools.causal_identity import causal_cluster_id


def _safe_level(value: Any) -> str:
    text = str(value or "baseline").strip().lower()
    text = re.sub(r"[^a-z0-9._-]+", "-", text).strip("-")
    return text or "baseline"


def _substitute(value: Any, candidate: dict[str, Any]) -> Any:
    if isinstance(value, str):
        replacements = {
            "{target}": str(candidate.get("target") or ""),
            "{service_target}": str(candidate.get("service_target") or candidate.get("target") or ""),
        }
        for source, target in replacements.items():
            value = value.replace(source, target)
        return value
    if isinstance(value, list):
        return [_substitute(item, candidate) for item in value]
    if isinstance(value, dict):
        return {str(key): _substitute(item, candidate) for key, item in value.items()}
    return value


def expand_candidate(candidate: dict[str, Any], generation: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return deterministic candidate variants from a profile ladder.

    A ``baseline`` variant keeps the legacy candidate ID. Additional variants
    append their level to that ID. Invalid or duplicate ladder entries fail
    closed so they cannot silently create ambiguous runtime hypotheses.
    """

    base = deepcopy(candidate)
    family = str(base.get("fault_family") or "").strip()
    ladders = generation.get("parameter_ladders") if isinstance(generation, dict) else None
    entries = ladders.get(family) if isinstance(ladders, dict) else None
    if not isinstance(entries, list) or not entries:
        base.setdefault("parameter_level", "baseline")
        base["causal_cluster_id"] = causal_cluster_id(base)
        return [base]

    expanded: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    base_id = str(base.get("candidate_id") or "")
    if not base_id:
        raise ValueError("parameterized candidate requires candidate_id")
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"parameter ladder entry for {family} must be an object")
        level = _safe_level(entry.get("level"))
        parameters = entry.get("parameters")
        if not isinstance(parameters, dict):
            raise ValueError(f"parameter ladder entry for {family}:{level} requires parameters")
        variant = deepcopy(base)
        variant["parameter_level"] = level
        variant["parameters"] = _substitute(parameters, variant)
        variant_id = base_id if level in {"baseline", "default"} else f"{base_id}:{level}"
        if variant_id in seen_ids:
            raise ValueError(f"duplicate parameterized candidate id: {variant_id}")
        variant["candidate_id"] = variant_id
        variant["causal_cluster_id"] = causal_cluster_id(variant)
        seen_ids.add(variant_id)
        expanded.append(variant)
    return expanded


def expand_candidates(candidates: list[dict[str, Any]], generation: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Expand all candidates while preserving source and ladder order."""

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        for variant in expand_candidate(candidate, generation):
            candidate_id = str(variant.get("candidate_id") or "")
            if not candidate_id or candidate_id in seen:
                raise ValueError(f"duplicate candidate id after parameter expansion: {candidate_id}")
            seen.add(candidate_id)
            result.append(variant)
    return result
