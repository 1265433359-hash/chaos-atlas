"""Convert a validated discovery hypothesis into a pending RCA case.

The adapter carries static discovery intent into the RCA contract.  It never
asserts that the hypothesis is a weakness and never attaches runtime evidence.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from tools.rca_loop import build_weakness_id


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def _business_oracle(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("business_oracle is required")
    workflow = _text(value.get("workflow"), "business_oracle.workflow")
    success = _text(value.get("success"), "business_oracle.success")
    return {"workflow": workflow, "success": success}


def build_case_from_hypothesis(
    hypothesis: dict[str, Any],
    *,
    project_id: str,
    project_commit: str,
    round_id: str,
    business_oracle: dict[str, Any],
    namespace: str | None = None,
    source_ref: str | None = None,
) -> dict[str, Any]:
    """Build a pending RCA case from compiler-accepted hypothesis output."""
    if not isinstance(hypothesis, dict):
        raise ValueError("hypothesis must be an object")
    project_id = _text(project_id, "project_id")
    project_commit = _text(project_commit, "project_commit")
    round_id = _text(round_id, "round_id")
    if namespace is not None:
        namespace = _text(namespace, "namespace")
    target = _text(hypothesis.get("target"), "hypothesis.target")
    target_kind = _text(hypothesis.get("target_kind"), "hypothesis.target_kind")
    fault_family = _text(hypothesis.get("fault_family"), "hypothesis.fault_family")
    hypothesis_id = _text(hypothesis.get("hypothesis_id"), "hypothesis.hypothesis_id")
    claim = _text(hypothesis.get("hypothesis"), "hypothesis.hypothesis")
    expected_invariant = _text(hypothesis.get("expected_invariant"), "hypothesis.expected_invariant")
    expected_steady_state = _text(hypothesis.get("expected_steady_state"), "hypothesis.expected_steady_state")
    validation_plan = _text(hypothesis.get("validation_plan"), "hypothesis.validation_plan")
    recovery_expectation = _text(hypothesis.get("recovery_expectation"), "hypothesis.recovery_expectation")
    oracle = _business_oracle(business_oracle)
    source_ref = source_ref or f"discovery/hypotheses/{hypothesis_id}.json"
    if ":" in source_ref or source_ref.startswith(("/", "\\")) or ".." in source_ref.split("/"):
        raise ValueError("source_ref must be a safe relative path")

    weakness_id = build_weakness_id(project_id, target, fault_family, str(hypothesis.get("parameters") or "intent"))
    scope = {"edge": target, "target_kind": target_kind, "target": target}
    required_evidence = ["baseline_oracle", "injection_confirmation", "observation", "recovery", "cleanup", "mechanism_evidence"]
    rca_hypothesis = {
        "hypothesis_id": hypothesis_id,
        "weakness_id": weakness_id,
        "claim": claim,
        "mechanism_class": "discovery_hypothesis",
        "mechanism_level": "service_boundary",
        "scope": scope,
        "expected_observations": [expected_invariant, recovery_expectation],
        "falsifiers": ["independent business oracle remains within baseline after confirmed injection"],
        "required_evidence": required_evidence,
        "evidence_for": [],
        "evidence_against": [],
        "unsupported_claims": required_evidence,
        "status": "pending",
        "confidence": 0.0,
        "next_action": None,
    }
    return {
        "schema_version": "chaosatlas-weakness-case-v1",
        "case_family": f"native_{target_kind}_{fault_family}",
        "weakness_id": weakness_id,
        "project_id": project_id,
        "project_commit": project_commit,
        "round_id": round_id,
        **({"namespace": namespace} if namespace is not None else {}),
        "test_node": {
            "family": fault_family,
            "operation": fault_family,
            "target": target,
            "target_kind": target_kind,
            "target_role": target,
            "canonical_signature": hypothesis.get("canonical_signature"),
            "source_ref": source_ref,
            "parameters": deepcopy(hypothesis.get("parameters") or {}),
            **({"mutation_manifest": deepcopy(hypothesis["mutation_manifest"])} if isinstance(hypothesis.get("mutation_manifest"), dict) else {}),
        },
        "symptom": {
            "oracle": oracle["workflow"],
            "baseline_contract": oracle["success"],
            "injected_contract": expected_invariant,
            "expected_steady_state": expected_steady_state,
            "validation_plan": validation_plan,
            "recovery_expectation": recovery_expectation,
        },
        "weakness_status": "candidate",
        "rca_status": "pending",
        "knowledge_status": "none",
        "evidence_refs": [],
        "hypothesis_ids": [hypothesis_id],
        "next_actions": [],
        "hypotheses": [rca_hypothesis],
        "replicates": [],
        "rca_audit": [],
    }
