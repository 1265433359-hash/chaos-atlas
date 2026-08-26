"""Build a bounded policy signal from a validated advisory hypothesis registry."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any


SCHEMA = "chaosatlas-registry-policy-input-v1"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _fallback(reason: str, *, registry: Any, quality_report: Any, candidate_space: Any, bonus_cap: Any) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA,
        "status": "fallback",
        "quality_status": quality_report.get("status") if isinstance(quality_report, dict) else None,
        "allowed_candidate_ids": [],
        "priority_bonus": {},
        "bonus_cap": bonus_cap,
        "fallback_reason": reason,
        "claim_scope": "advisory",
        "input_sha256": _hash({"registry": registry, "quality_report": quality_report, "candidate_space": candidate_space, "bonus_cap": bonus_cap}),
    }


def build_registry_policy_signal(
    registry: dict[str, Any],
    quality_report: dict[str, Any],
    candidate_space: dict[str, Any],
    *,
    bonus_cap: float = 0.25,
) -> dict[str, Any]:
    """Return a deterministic, runtime-only priority signal or a safe fallback."""
    if isinstance(bonus_cap, bool) or not isinstance(bonus_cap, (int, float)) or not math.isfinite(float(bonus_cap)) or not 0 < float(bonus_cap) <= 1:
        return _fallback("invalid_bonus_cap", registry=registry, quality_report=quality_report, candidate_space=candidate_space, bonus_cap=bonus_cap)
    if not isinstance(quality_report, dict) or quality_report.get("status") != "passed":
        return _fallback("quality_not_passed", registry=registry, quality_report=quality_report, candidate_space=candidate_space, bonus_cap=bonus_cap)
    if not isinstance(registry, dict) or registry.get("claim_scope") != "advisory":
        return _fallback("registry_not_advisory", registry=registry, quality_report=quality_report, candidate_space=candidate_space, bonus_cap=bonus_cap)
    candidates = candidate_space.get("candidates") if isinstance(candidate_space, dict) else None
    if not isinstance(candidates, list):
        return _fallback("candidate_space_invalid", registry=registry, quality_report=quality_report, candidate_space=candidate_space, bonus_cap=bonus_cap)
    candidate_ids = [str(item.get("candidate_id")) for item in candidates if isinstance(item, dict) and item.get("candidate_id")]
    if len(candidate_ids) != len(set(candidate_ids)):
        return _fallback("duplicate_candidate_id", registry=registry, quality_report=quality_report, candidate_space=candidate_space, bonus_cap=bonus_cap)
    candidate_set = set(candidate_ids)
    hypotheses = registry.get("hypotheses")
    if not isinstance(hypotheses, list):
        return _fallback("registry_hypotheses_invalid", registry=registry, quality_report=quality_report, candidate_space=candidate_space, bonus_cap=bonus_cap)
    rows: list[tuple[str, float]] = []
    seen: set[str] = set()
    for item in hypotheses:
        if not isinstance(item, dict) or item.get("kind") != "runtime" or item.get("execution_eligible") is not True:
            continue
        candidate_id = str(item.get("candidate_id") or "")
        if not candidate_id or candidate_id not in candidate_set:
            return _fallback("unknown_runtime_candidate", registry=registry, quality_report=quality_report, candidate_space=candidate_space, bonus_cap=bonus_cap)
        if candidate_id in seen:
            return _fallback("duplicate_runtime_candidate", registry=registry, quality_report=quality_report, candidate_space=candidate_space, bonus_cap=bonus_cap)
        seen.add(candidate_id)
        score = item.get("priority_score")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(float(score)) or float(score) < 0:
            return _fallback("invalid_runtime_priority", registry=registry, quality_report=quality_report, candidate_space=candidate_space, bonus_cap=bonus_cap)
        rows.append((candidate_id, float(score)))
    if not rows:
        return _fallback("no_runtime_entries", registry=registry, quality_report=quality_report, candidate_space=candidate_space, bonus_cap=bonus_cap)
    max_score = max(score for _, score in rows)
    rows.sort(key=lambda row: (-row[1], row[0]))
    bonuses = {
        candidate_id: round(float(bonus_cap) * (score / max_score), 12) if max_score > 0 else 0.0
        for candidate_id, score in rows
    }
    return {
        "schema_version": SCHEMA,
        "status": "ready",
        "quality_status": quality_report.get("status"),
        "allowed_candidate_ids": [candidate_id for candidate_id, _ in rows],
        "priority_bonus": bonuses,
        "bonus_cap": float(bonus_cap),
        "fallback_reason": None,
        "claim_scope": "advisory",
        "input_sha256": _hash({"registry": registry, "quality_report": quality_report, "candidate_space": candidate_space, "bonus_cap": float(bonus_cap)}),
    }
