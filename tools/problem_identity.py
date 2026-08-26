"""Derive deterministic problem identities from completed RCA artifacts.

Run identity and fault family identify an experiment.  Issue identity describes
the observed problem surface and intentionally ignores the particular fault
method so that multiple injections can support one issue.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

try:
    from tools.causal_identity import canonical_causal_identity, causal_cluster_id
except ModuleNotFoundError:  # direct script invocation
    from causal_identity import canonical_causal_identity, causal_cluster_id


_REQUIRED_ATTESTATION = ("baseline", "injection", "observation", "recovery", "cleanup", "independent_oracle", "valid")


def _payload(value: dict[str, Any]) -> dict[str, Any]:
    payload = value.get("payload")
    return payload if isinstance(payload, dict) else value


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _first_hypothesis(payload: dict[str, Any]) -> dict[str, Any]:
    values = payload.get("hypotheses")
    return values[0] if isinstance(values, list) and values and isinstance(values[0], dict) else {}


def _test_node(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("test_node")
    return value if isinstance(value, dict) else {}


def _identity_input(payload: dict[str, Any]) -> dict[str, Any]:
    hypothesis = _first_hypothesis(payload)
    node = _test_node(payload)
    symptom = payload.get("symptom") if isinstance(payload.get("symptom"), dict) else {}
    scope = hypothesis.get("scope") if isinstance(hypothesis.get("scope"), dict) else {}
    return {
        "project": str(payload.get("project_id") or "").strip().lower(),
        "target": str(node.get("target") or "").strip().lower(),
        "target_kind": str(node.get("target_kind") or "").strip().lower(),
        "oracle": str(symptom.get("oracle") or "").strip().lower(),
        "scope": str(scope.get("edge") or node.get("target") or "").strip().lower(),
        "recovery": str(symptom.get("recovery_expectation") or "").strip().lower(),
        "impact": str(payload.get("classification") or payload.get("result") or "availability").strip().lower(),
    }


def _problem_issue_id(identity: dict[str, str]) -> str:
    return "ISSUE-" + _hash(identity)[:16]


def derive_problem_identity(value: dict[str, Any]) -> dict[str, Any]:
    """Return strict lifecycle eligibility plus method/problem identities."""

    payload = _payload(value)
    node = _test_node(payload)
    identity = _identity_input(payload)
    candidate = {
        "source": payload.get("project_id"),
        "target": node.get("target"),
        "target_kind": node.get("target_kind"),
        "fault_family": node.get("family") or payload.get("fault_family"),
        "oracle": identity["oracle"],
        "recovery_contract": payload.get("recovery_contract") or identity["recovery"],
        "parameters": node.get("parameters") or {},
    }
    reasons: list[str] = []
    if str(payload.get("claim_scope") or value.get("claim_scope") or "") != "runtime":
        reasons.append("claim_scope")
    if str(payload.get("rca_status") or "") != "confirmed":
        reasons.append("rca_status")
    if str(payload.get("cleanup_status") or "verified") != "verified":
        reasons.append("cleanup")
    attestation = payload.get("attestation")
    if isinstance(attestation, dict):
        missing = [key for key in _REQUIRED_ATTESTATION if attestation.get(key) is not True]
        if missing:
            reasons.append("attestation:" + ",".join(missing))
    if str(payload.get("classification") or payload.get("result") or "") in {"environment_blocked", "method_invalid", "unsupported", "response_observed"}:
        reasons.append("classification")
    return {
        "eligible": not reasons,
        "reasons": sorted(set(reasons)),
        "project_id": identity["project"],
        "target": identity["target"],
        "fault_family": str(node.get("family") or payload.get("fault_family") or "").strip().lower(),
        "weakness_id": str(payload.get("weakness_id") or ""),
        "causal_identity": canonical_causal_identity(candidate),
        "causal_cluster_id": causal_cluster_id(candidate),
        "issue_identity": deepcopy(identity),
        "issue_id": _problem_issue_id(identity),
    }

