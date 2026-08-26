"""Frozen candidate and evidence contracts for the NGINX ingress fixture.

The catalog is intentionally separate from the live adapter.  A contract may
be documented before its executor is safe and complete; ``execution_eligible``
is the hard boundary that prevents a pending method from entering live runs.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

try:
    from tools.fault_executor_registry import get_fault_executor
except ModuleNotFoundError:  # direct script invocation
    from fault_executor_registry import get_fault_executor


SCHEMA_VERSION = "chaosatlas-nginx-candidate-contracts-v1"
_COMMON_EVIDENCE = ["baseline_oracle", "injection_confirmation", "observation", "recovery", "cleanup"]


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _contract(
    family: str,
    *,
    target_kind: str,
    target_role: str,
    parameters: dict[str, Any],
    preconditions: list[str],
    required_evidence: list[str],
    execution_eligible: bool = True,
    status: str = "ready",
) -> dict[str, Any]:
    return {
        "family": family,
        "target_kind": target_kind,
        "target_role": target_role,
        "parameters": deepcopy(parameters),
        "preconditions": sorted(set(preconditions)),
        "required_evidence": sorted(set(required_evidence)),
        "recovery_contract": {
            "ready_required": True,
            "business_probe_required": True,
            "cleanup_required": True,
            "recovery_mode": "container_restart" if family == "container_kill" else "pod_replacement",
            "replacement_identity_required": family != "container_kill",
        },
        "execution_eligible": execution_eligible,
        "status": status,
    }


def _contracts() -> list[dict[str, Any]]:
    return [
        _contract("pod_kill", target_kind="deployment", target_role="controller", parameters={"mode": {"type": "enum", "values": ["one"]}}, preconditions=["controller Deployment is Ready", "independent HTTP Oracle baseline passes"], required_evidence=_COMMON_EVIDENCE + ["pod_identity", "mechanism_evidence"]),
        _contract("container_kill", target_kind="deployment", target_role="controller", parameters={"container": {"type": "deployment_container"}}, preconditions=["controller container is identified", "independent HTTP Oracle baseline passes"], required_evidence=_COMMON_EVIDENCE + ["container_restart", "mechanism_evidence"]),
        _contract("stress_cpu", target_kind="deployment", target_role="controller", parameters={"workers": {"type": "integer", "min": 1, "max": 1}, "load_percent": {"type": "integer", "min": 1, "max": 80}}, preconditions=["controller resource budget is verified", "metrics or bounded runtime evidence is available"], required_evidence=_COMMON_EVIDENCE + ["resource_effect", "mechanism_evidence"]),
        _contract("stress_memory", target_kind="deployment", target_role="controller", parameters={"size_mb": {"type": "integer", "min": 1, "max": 64}}, preconditions=["controller memory limit is verified", "metrics or bounded runtime evidence is available"], required_evidence=_COMMON_EVIDENCE + ["resource_effect", "mechanism_evidence"]),
        _contract("network_loss", target_kind="dependency_edge", target_role="controller_to_backend", parameters={"loss_percent": {"type": "integer", "min": 1, "max": 100}}, preconditions=["Ingress-to-backend dependency edge is verified", "independent HTTP Oracle baseline passes"], required_evidence=_COMMON_EVIDENCE + ["dependency_edge", "network_effect", "mechanism_evidence"]),
        _contract("network_partition", target_kind="dependency_edge", target_role="controller_to_backend", parameters={}, preconditions=["Ingress-to-backend dependency edge is verified", "independent HTTP Oracle baseline passes"], required_evidence=_COMMON_EVIDENCE + ["dependency_edge", "network_effect", "mechanism_evidence"]),
        _contract("network_delay", target_kind="dependency_edge", target_role="controller_to_backend", parameters={"latency_ms": {"type": "integer", "min": 1, "max": 500}, "duration_s": {"type": "integer", "min": 1, "max": 60}}, preconditions=["Ingress-to-backend dependency edge is verified", "timeout and retry oracle contract is frozen"], required_evidence=_COMMON_EVIDENCE + ["dependency_edge", "latency_effect", "timeout_or_retry_behavior", "mechanism_evidence"], execution_eligible=False, status="pending_method_freeze"),
        _contract("backend_pod_kill", target_kind="deployment", target_role="fixture_backend", parameters={"mode": {"type": "enum", "values": ["one"]}}, preconditions=["fixture backend Deployment is Ready", "Ingress route and backend endpoint identity are verified"], required_evidence=_COMMON_EVIDENCE + ["backend_identity", "route_effect", "mechanism_evidence"], execution_eligible=False, status="pending_method_freeze"),
        _contract("config_reload", target_kind="config", target_role="controller_config", parameters={"config_ref": {"type": "allowlisted_configmap"}, "reload_mode": {"type": "enum", "values": ["reviewed"]}}, preconditions=["config object and diff are allow-listed", "rollback artifact is frozen", "independent HTTP Oracle baseline passes"], required_evidence=_COMMON_EVIDENCE + ["config_diff", "reload_confirmation", "route_continuity", "mechanism_evidence"], execution_eligible=False, status="pending_method_freeze"),
        _contract("replica_reduction", target_kind="deployment", target_role="controller", parameters={"replicas": {"type": "integer", "min": 0, "max": "observed_replicas_minus_one"}}, preconditions=["controller has at least two Ready replicas", "scale restore plan is verified", "independent HTTP Oracle baseline passes"], required_evidence=_COMMON_EVIDENCE + ["replica_transition", "endpoint_continuity", "mechanism_evidence"], execution_eligible=False, status="pending_method_freeze"),
    ]


def build_catalog(*, project_id: str, project_commit: str) -> dict[str, Any]:
    contracts = _contracts()
    for contract in contracts:
        executor = get_fault_executor(str(contract["family"]))
        contract["executor_status"] = executor["status"]
        contract["executor"] = executor["executor"]
        contract["live_execution_allowed"] = bool(contract["execution_eligible"] and executor["can_execute"])
    result = {
        "schema_version": SCHEMA_VERSION,
        "project_id": str(project_id),
        "project_commit": str(project_commit),
        "contracts": contracts,
        "execution_eligible_families": [item["family"] for item in contracts if item["execution_eligible"]],
        "pending_families": [item["family"] for item in contracts if not item["execution_eligible"]],
        "claim_scope": "advisory",
    }
    result["catalog_sha256"] = _hash(result)
    return result


def validate_catalog(catalog: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(catalog, dict) or catalog.get("schema_version") != SCHEMA_VERSION:
        return ["schema_version must be chaosatlas-nginx-candidate-contracts-v1"]
    contracts = catalog.get("contracts")
    if not isinstance(contracts, list) or not contracts:
        return ["contracts must be a non-empty list"]
    seen: set[str] = set()
    for index, item in enumerate(contracts):
        prefix = f"contracts[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        family = str(item.get("family") or "")
        if not family:
            errors.append(f"{prefix}.family is required")
        elif family in seen:
            errors.append(f"duplicate family: {family}")
        seen.add(family)
        if not isinstance(item.get("parameters"), dict):
            errors.append(f"{prefix}.parameters must be an object")
        if not isinstance(item.get("preconditions"), list) or not item.get("preconditions"):
            errors.append(f"{prefix}.preconditions is required")
        if not isinstance(item.get("required_evidence"), list) or not item.get("required_evidence"):
            errors.append(f"{prefix}.required_evidence is required")
        eligible = item.get("execution_eligible") is True
        status = str(item.get("status") or "")
        executor_status = str(item.get("executor_status") or "")
        live_allowed = item.get("live_execution_allowed") is True
        if not eligible and status != "pending_method_freeze":
            errors.append(f"{prefix} pending execution must use status pending_method_freeze")
        if eligible and status == "pending_method_freeze":
            errors.append(f"{prefix} pending_method_freeze cannot be execution eligible")
        if eligible and executor_status != "ready":
            errors.append(f"{prefix} execution-eligible family requires ready executor")
        if not eligible and executor_status == "ready":
            errors.append(f"{prefix} pending family cannot expose ready executor")
        if live_allowed != (eligible and executor_status == "ready"):
            errors.append(f"{prefix} live_execution_allowed is inconsistent with executor status")
        recovery = item.get("recovery_contract")
        if not isinstance(recovery, dict) or not all(recovery.get(key) is True for key in ("ready_required", "business_probe_required", "cleanup_required")):
            errors.append(f"{prefix}.recovery_contract is incomplete")
    return errors
