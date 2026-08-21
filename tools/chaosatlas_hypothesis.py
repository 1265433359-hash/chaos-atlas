"""Experience retrieval and advisory hypothesis boundaries."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any


FORBIDDEN_KEYS = {
    "weakness_status",
    "rca_status",
    "knowledge_status",
    "runtime_verdict",
    "final_verdict",
    "classification",
    "defense_status",
}
_HYPOTHESIS_FIELDS = {"candidate_id", "mechanism", "expected_observations", "missing_evidence", "next_actions"}


def _forbidden(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_KEYS:
                found.append(f"{path}.{key}")
            found.extend(_forbidden(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_forbidden(child, f"{path}[{index}]"))
    return found


def _strings(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{field} must be a list[str]")
    return [item.strip() for item in value]


def build_hypothesis_input(
    inventory: dict[str, Any],
    detection: dict[str, Any],
    candidate_space: dict[str, Any],
    cards: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the advisory input only after project mapping is complete."""
    if detection.get("status") != "verified":
        raise ValueError("server deployment detection must be verified before retrieval")
    if not isinstance(candidate_space.get("candidates"), list):
        raise ValueError("candidate space must contain candidates")
    return {
        "schema_version": "chaosatlas-hypothesis-input-v1",
        "project_id": inventory.get("project_id"),
        "inventory": deepcopy(inventory),
        "server_deployment_detection": deepcopy(detection),
        "candidate_space": deepcopy(candidate_space),
        "knowledge_view": deepcopy(cards),
        "claim_scope": "advisory",
    }


def rank_candidates(candidate_space: dict[str, Any], cards: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [deepcopy(item) for item in candidate_space.get("candidates") or [] if isinstance(item, dict)]
    if not candidates:
        return {"schema_version": "chaosatlas-ranked-candidates-v1", "candidate_count": 0, "candidate_ids": [], "candidates": []}
    reusable = [card for card in cards if isinstance(card, dict) and card.get("status") in {"local_reusable", "cross_project_reusable"}]
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    for item in candidates:
        family = str(item.get("fault_family") or "")
        score = 1 if item.get("static_prior") else 0
        for card in reusable:
            node = card.get("test_node") or {}
            if node.get("family") == family:
                score += 100
            if node.get("operation") == family:
                score += 25
        item["retrieval_score"] = score
        ranked.append((-score, str(item.get("candidate_id") or ""), item))
    ranked.sort(key=lambda value: (value[0], value[1]))
    ordered = [item for _, _, item in ranked]
    return {
        "schema_version": "chaosatlas-ranked-candidates-v1",
        "candidate_count": len(ordered),
        "candidate_ids": [str(item.get("candidate_id")) for item in ordered],
        "candidates": ordered,
        "claim_scope": "advisory",
    }


def parse_advisory_output(raw: str, *, allowed_candidate_ids: set[str]) -> dict[str, Any]:
    text = str(raw).strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("advisory output must be an object")
    forbidden = _forbidden(value)
    if forbidden:
        raise ValueError(f"forbidden advisory fields: {forbidden}")
    hypotheses = value.get("hypotheses")
    if not isinstance(hypotheses, list) or len(hypotheses) > 8:
        raise ValueError("hypotheses must be a list of at most 8")
    parsed: list[dict[str, Any]] = []
    for index, item in enumerate(hypotheses):
        if not isinstance(item, dict):
            raise ValueError(f"hypotheses[{index}] must be an object")
        unknown = set(item) - _HYPOTHESIS_FIELDS
        if unknown:
            raise ValueError(f"unsupported advisory fields: {sorted(unknown)}")
        candidate_id = item.get("candidate_id")
        if candidate_id not in allowed_candidate_ids:
            raise ValueError(f"unknown candidate_id: {candidate_id}")
        mechanism = item.get("mechanism")
        if not isinstance(mechanism, str) or not mechanism.strip():
            raise ValueError(f"hypotheses[{index}].mechanism is required")
        normalized = {
            "candidate_id": candidate_id,
            "mechanism": mechanism.strip(),
            "expected_observations": _strings(item.get("expected_observations", []), f"hypotheses[{index}].expected_observations"),
            "missing_evidence": _strings(item.get("missing_evidence", []), f"hypotheses[{index}].missing_evidence"),
            "next_actions": _strings(item.get("next_actions", []), f"hypotheses[{index}].next_actions"),
        }
        parsed.append(normalized)
    return {
        "schema_version": "chaosatlas-advisory-hypotheses-v1",
        "hypotheses": parsed,
        "global_missing_evidence": _strings(value.get("global_missing_evidence", []), "global_missing_evidence"),
        "claim_scope": "advisory",
    }


def build_deterministic_hypotheses(ranked: dict[str, Any]) -> dict[str, Any]:
    hypotheses: list[dict[str, Any]] = []
    for candidate in ranked.get("candidates") or []:
        family = str(candidate.get("fault_family") or "unknown")
        target = str(candidate.get("target") or "unknown")
        hypotheses.append({
            "candidate_id": candidate.get("candidate_id"),
            "mechanism": f"{family} may affect {target} availability or business behavior",
            "expected_observations": ["injection confirmation", "business oracle result", "recovery and cleanup evidence"],
            "missing_evidence": ["runtime evidence"],
            "next_actions": ["run bounded baseline and observation plan"],
        })
    return {"schema_version": "chaosatlas-deterministic-hypotheses-v1", "hypotheses": hypotheses, "claim_scope": "advisory"}
