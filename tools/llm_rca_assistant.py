"""Structured LLM assistance for RCA evidence interpretation.

The model proposes mechanisms and evidence actions only.  Deterministic RCA
transitions, runtime classification, and knowledge promotion remain outside
this module.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any

from tools.rca_loop import _contains_sensitive_value


FORBIDDEN_KEYS = {
    "rca_status",
    "knowledge_status",
    "weakness_status",
    "classification",
    "oracle_label",
    "runtime_verdict",
    "final_verdict",
    "kubectl_command",
    "shell_command",
    "execute",
    "mutation_path",
}


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


def build_evidence_pack(case: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """Whitelist case/evidence fields before they are exposed to an LLM."""
    if not isinstance(case, dict) or not isinstance(evidence, list):
        raise ValueError("case and evidence are required")
    pack = {
        "case": {
            "weakness_id": case.get("weakness_id"),
            "project_id": case.get("project_id"),
            "round_id": case.get("round_id"),
            "test_node": {
                key: (case.get("test_node") or {}).get(key)
                for key in ("target", "target_kind", "target_role", "family", "operation")
                if key in (case.get("test_node") or {})
            },
            "symptom": deepcopy(case.get("symptom") or {}),
            "hypotheses": [
                {
                    "hypothesis_id": item.get("hypothesis_id"),
                    "claim": item.get("claim"),
                    "scope": item.get("scope"),
                    "status": item.get("status"),
                }
                for item in case.get("hypotheses", [])
                if isinstance(item, dict)
            ],
        },
        "evidence": [
            {
                key: item.get(key)
                for key in ("evidence_id", "kind", "polarity", "claim_scope", "source_ref", "sha256", "window", "interpretation", "satisfies")
                if key in item
            }
            for item in evidence
            if isinstance(item, dict)
        ],
    }
    serialized = json.dumps(pack, ensure_ascii=True, sort_keys=True)
    if _contains_sensitive_value(serialized):
        raise ValueError("evidence pack contains sensitive values")
    return pack


def build_messages(case: dict[str, Any], evidence: list[dict[str, Any]]) -> tuple[str, str]:
    pack = build_evidence_pack(case, evidence)
    system = (
        "You are the ChaosAtlas RCA evidence assistant. Propose mechanism hypotheses and "
        "next evidence actions from the supplied evidence only. You must not decide RCA status, "
        "knowledge status, runtime verdict, defense classification, or execute any command. "
        "Unavailable evidence is not negative evidence. Return JSON only."
    )
    user = json.dumps(
        {
            # Keep the contract intentionally flat for downstream prompt
            # inspectors while retaining the named pack for auditability.
            "case": pack["case"],
            "evidence": pack["evidence"],
            "evidence_pack": pack,
            "output_schema": {
                "hypotheses": [{
                    "hypothesis_id": "existing hypothesis id",
                    "mechanism": "bounded mechanism explanation",
                    "supports": "list[evidence_id]",
                    "contradicts": "list[evidence_id]",
                    "missing_evidence": "list[str]",
                    "next_actions": "list[str]",
                }],
                "global_missing_evidence": "list[str]",
            },
        },
        indent=2,
        ensure_ascii=True,
    )
    return system, user


def parse_analysis_output(
    raw: str,
    *,
    allowed_hypothesis_ids: set[str],
    allowed_scopes: set[str],
    allowed_evidence_ids: set[str] | None = None,
) -> dict[str, Any]:
    text = str(raw).strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("RCA assistant output must be an object")
    forbidden = _forbidden(value)
    if forbidden:
        raise ValueError(f"forbidden RCA assistant fields: {forbidden}")
    hypotheses = value.get("hypotheses")
    if not isinstance(hypotheses, list) or len(hypotheses) > 8:
        raise ValueError("hypotheses must be a list of at most 8")
    for index, item in enumerate(hypotheses):
        if not isinstance(item, dict):
            raise ValueError(f"hypotheses[{index}] must be an object")
        hid = item.get("hypothesis_id")
        if hid not in allowed_hypothesis_ids:
            raise ValueError(f"unknown hypothesis_id: {hid}")
        if not isinstance(item.get("mechanism"), str) or not item["mechanism"].strip():
            raise ValueError(f"hypotheses[{index}].mechanism is required")
        supports = _strings(item.get("supports"), f"hypotheses[{index}].supports")
        contradicts = _strings(item.get("contradicts"), f"hypotheses[{index}].contradicts")
        _strings(item.get("missing_evidence"), f"hypotheses[{index}].missing_evidence")
        _strings(item.get("next_actions"), f"hypotheses[{index}].next_actions")
        if allowed_evidence_ids is not None and any(ref not in allowed_evidence_ids for ref in supports + contradicts):
            raise ValueError(f"hypotheses[{index}] references unknown evidence")
        item["supports"] = supports
        item["contradicts"] = contradicts
    value["global_missing_evidence"] = _strings(value.get("global_missing_evidence", []), "global_missing_evidence")
    return value


def analyze_with_backend(backend: Any, case: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    system, user = build_messages(case, evidence)
    raw, metadata = backend.complete(system, user, "")
    allowed_hypotheses = {str(item.get("hypothesis_id")) for item in case.get("hypotheses", []) if isinstance(item, dict)}
    allowed_scopes = {str((item.get("scope") or {}).get("edge")) for item in case.get("hypotheses", []) if isinstance(item, dict)}
    allowed_evidence = {str(item.get("evidence_id")) for item in evidence if isinstance(item, dict)}
    analysis = parse_analysis_output(raw, allowed_hypothesis_ids=allowed_hypotheses, allowed_scopes=allowed_scopes, allowed_evidence_ids=allowed_evidence)
    return {
        "schema_version": "chaosatlas-llm-rca-analysis-v1",
        "request_sha256": hashlib.sha256((system + "\n" + user).encode()).hexdigest(),
        "response_sha256": hashlib.sha256(str(raw).encode()).hexdigest(),
        "backend": metadata,
        "analysis": analysis,
    }
