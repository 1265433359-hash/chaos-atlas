"""Project-local, versioned metrics for evaluating the experiment policy."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "chaosatlas-policy-calibration-v1"


def _decision_key(decision: dict[str, Any]) -> str:
    payload = {
        "selected": list(decision.get("policy_selected_candidate_ids") or []),
        "stop_reason": decision.get("stop_reason"),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def new_calibration(project_id: str, round_id: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "round_id": round_id,
        "metrics": {
            "experiments": 0,
            "confirmed_weaknesses": 0,
            "protected_waste": 0,
            "method_invalid": 0,
            "environment_blocked": 0,
            "boundary_discoveries": 0,
            "stop_reasons": {},
        },
        "decision_keys": [],
        "history": [],
    }


def record_policy_outcome(
    calibration: dict[str, Any],
    decision: dict[str, Any],
    runtime_result: dict[str, Any],
) -> dict[str, Any]:
    metrics = calibration.setdefault("metrics", {})
    classification = str(runtime_result.get("classification") or "unsupported")
    metrics["experiments"] = int(metrics.get("experiments", 0)) + 1
    if classification == "confirmed_weakness":
        metrics["confirmed_weaknesses"] = int(metrics.get("confirmed_weaknesses", 0)) + 1
    elif classification == "protected":
        metrics["protected_waste"] = int(metrics.get("protected_waste", 0)) + 1
    elif classification == "method_invalid":
        metrics["method_invalid"] = int(metrics.get("method_invalid", 0)) + 1
    elif classification == "environment_blocked":
        metrics["environment_blocked"] = int(metrics.get("environment_blocked", 0)) + 1
    if runtime_result.get("boundary_discovered") is True:
        metrics["boundary_discoveries"] = int(metrics.get("boundary_discoveries", 0)) + 1
    stop_reason = decision.get("stop_reason")
    key = _decision_key(decision)
    seen = calibration.setdefault("decision_keys", [])
    if stop_reason and key not in seen:
        stop_reasons = metrics.setdefault("stop_reasons", {})
        stop_reasons[stop_reason] = int(stop_reasons.get(stop_reason, 0)) + 1
        seen.append(key)
    calibration.setdefault("history", []).append({
        "candidate_id": runtime_result.get("candidate_id"),
        "classification": classification,
        "stop_reason": stop_reason,
    })
    return calibration


def write_calibration(calibration: dict[str, Any], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(calibration, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    temporary.replace(path)

