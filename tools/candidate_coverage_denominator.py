"""Build the static native discovery space and its auditable denominator.

This module deliberately stops before execution.  It turns frozen topology and
deployment facts into bounded candidates; runtime observations and verdicts are
never copied into the output.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

try:
    from tools.causal_identity import canonical_causal_identity, causal_cluster_id
except ModuleNotFoundError:  # direct script invocation
    from causal_identity import canonical_causal_identity, causal_cluster_id


FORBIDDEN_KEYS = {
    "runtime_verdict",
    "runtime_observation",
    "post_run_rca",
    "oracle_label",
    "candidate_pool",
    "ce_verdict",
}


def find_forbidden_input_fields(value: Any, path: str = "$") -> list[str]:
    """Return paths that would contaminate a static discovery input."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_KEYS:
                found.append(f"{path}.{key}")
            found.extend(find_forbidden_input_fields(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(find_forbidden_input_fields(child, f"{path}[{index}]"))
    return found


def _common(bundle: dict[str, Any]) -> dict[str, Any]:
    value = bundle.get("common_input")
    return value if isinstance(value, dict) else bundle


def _business_ready(common: dict[str, Any]) -> bool:
    oracle = common.get("business_oracle")
    if not isinstance(oracle, dict):
        return False
    return bool(str(oracle.get("workflow") or "").strip()) and bool(str(oracle.get("success") or "").strip())


def _node_map(pool: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("node_id")): item
        for item in pool.get("deployment_nodes", [])
        if isinstance(item, dict) and str(item.get("node_id") or "").strip()
    }


def _selector_ready(node: dict[str, Any]) -> bool:
    deployment = node.get("deployment") or {}
    selector = deployment.get("selector")
    return isinstance(selector, dict) and bool(selector.get("matchLabels"))


def _static_deployment_view(node: dict[str, Any]) -> dict[str, Any]:
    """Copy only manifest-derived fields into the discovery input."""
    return {
        key: node[key]
        for key in (
            "node_id",
            "node_type",
            "project_id",
            "project_commit",
            "namespace",
            "deployment",
            "service",
            "availability_profile",
            "source_refs",
            "manifest_sha256",
        )
        if key in node
    }


def _candidate(
    *,
    candidate_id: str,
    target: str,
    target_kind: str,
    fault_family: str,
    applicability_plan: str,
    expected_steady_state: str,
    recovery_expectation: str,
    validation_plan: str,
    blocked_reasons: list[str],
    **extra: Any,
) -> dict[str, Any]:
    status = "blocked" if blocked_reasons else "eligible"
    result = {
        "candidate_id": candidate_id,
        "target": target,
        "target_kind": target_kind,
        "fault_family": fault_family,
        "parameters": {
            "mode": "one",
        } if fault_family == "pod_kill" else {
            "loss_percent": 50,
            "duration_s": 30,
        } if fault_family == "network_loss" else {
            "workers": 1,
            "load_percent": 50,
            "duration_s": 30,
        } if fault_family == "container_cpu_stress" else {},
        "applicability_plan": applicability_plan,
        "expected_steady_state": expected_steady_state,
        "recovery_expectation": recovery_expectation,
        "validation_plan": validation_plan,
        "status": status,
        "blocked_reasons": sorted(set(blocked_reasons)),
        "base_score": 10.0,
    }
    result.update(extra)
    identity = canonical_causal_identity(result)
    result["causal_identity"] = identity
    result["causal_cluster_id"] = causal_cluster_id(result)
    result["parameter_domain"] = identity["parameter_domain"]
    return result


def build_candidate_space(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Enumerate dependency, deployment and scenario candidates from static facts."""
    common = _common(bundle)
    topology = common.get("topology") if isinstance(common.get("topology"), dict) else {}
    pool = common.get("deployment_capability_pool")
    if not isinstance(pool, dict):
        pool = bundle.get("deployment_capability_pool") if isinstance(bundle.get("deployment_capability_pool"), dict) else {}
    business_block = [] if _business_ready(common) else ["business oracle is missing workflow/success contract"]
    nodes = {
        str(item.get("id")): item
        for item in topology.get("nodes", [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    candidates: list[dict[str, Any]] = []
    for edge in topology.get("edges", []):
        if not isinstance(edge, dict):
            continue
        source, target = str(edge.get("source") or ""), str(edge.get("target") or "")
        if not source or not target:
            continue
        reasons = list(business_block)
        if source not in nodes or target not in nodes:
            reasons.append("dependency selector/topology target is unresolved")
        if not nodes.get(source, {}).get("selector_resolved", True) or not nodes.get(target, {}).get("selector_resolved", True):
            reasons.append("dependency selector is unresolved")
        candidates.append(_candidate(
            candidate_id=f"dependency_edge:{source}->{target}",
            target=f"{source}->{target}",
            target_kind="dependency_edge",
            fault_family="network_loss",
            applicability_plan="resolve both namespace-local endpoints and confirm business traffic crosses the edge",
            expected_steady_state="business oracle remains successful within its declared deadline",
            recovery_expectation="traffic returns to baseline after fault removal",
            validation_plan="baseline, inject loss, observe independent business oracle, recover, cleanup",
            blocked_reasons=reasons,
            business_oracle=common.get("business_oracle"),
            call_chain=[{"source": source, "target": target, "relation": edge.get("relation") or edge.get("kind") or "dependency", "evidence_ref": "topology"}],
        ))

    # Native handoffs use workload targets with target_kind=service. Materialize
    # those admissible service candidates only when the topology contains the
    # matching service/workload pair; this keeps the denominator static while
    # making the policy registry compatible with validated handoffs.
    for workload_id, workload in nodes.items():
        if not workload_id.startswith("workload/"):
            continue
        service_id = "service/" + workload_id.split("/", 1)[1]
        service = nodes.get(service_id)
        if not isinstance(service, dict):
            continue
        reasons = list(business_block)
        if not workload.get("selector_resolved", True) or not service.get("selector_resolved", True):
            reasons.append("service/workload selector is unresolved")
        candidates.append(_candidate(
            candidate_id=f"service:{workload_id}",
            target=workload_id,
            target_kind="service",
            fault_family="network_loss",
            applicability_plan="resolve the service selector and workload endpoint, then confirm business traffic crosses the target",
            expected_steady_state="business oracle remains successful within its declared deadline",
            recovery_expectation="service traffic returns to baseline after fault removal",
            validation_plan="baseline, inject loss, observe independent business oracle, recover, cleanup",
            blocked_reasons=reasons,
            business_oracle=common.get("business_oracle"),
            call_chain=[{"source": service_id, "target": workload_id, "relation": "selects", "evidence_ref": "topology"}],
        ))

    deployment_candidates = [item for item in pool.get("candidates", []) if isinstance(item, dict)]
    deployment_nodes = _node_map(pool)
    eligible_deployments: list[str] = []
    for item in deployment_candidates:
        target = str(item.get("target") or "")
        node = deployment_nodes.get(target, {})
        reasons = list(business_block)
        if not item.get("compile_eligible"):
            reasons.append("deployment selector or manifest facts are not compile-eligible")
        if not node:
            reasons.append("deployment node is unresolved")
        elif not _selector_ready(node):
            reasons.append("deployment selector is unresolved")
        if not (node.get("recovery_contract") or (node.get("availability_profile") or {}).get("recovery_contract")):
            reasons.append("recovery contract is missing")
        if not reasons:
            eligible_deployments.append(target)
        candidates.append(_candidate(
            candidate_id=target,
            target=target,
            target_kind="deployment",
            fault_family=("pod_kill" if "pod_kill" in (item.get("fault_families") or []) else "container_cpu_stress"),
            applicability_plan="resolve Deployment selector, controller readiness and target Pod readiness before injection",
            expected_steady_state="deployment.availableReplicas >= 1 and business oracle remains within contract",
            recovery_expectation="replacement Pod identity changes, becomes Ready, and business probe stabilizes",
            validation_plan="baseline, inject, observe availableReplicas and business oracle, recover, cleanup",
            blocked_reasons=reasons,
            fault_families=list(item.get("fault_families") or []),
            deployment_node=_static_deployment_view(node),
            business_oracle=common.get("business_oracle"),
            recovery_contract=node.get("recovery_contract") or (node.get("availability_profile") or {}).get("recovery_contract"),
        ))

    scenario_reasons = list(business_block)
    if not eligible_deployments:
        scenario_reasons.append("no deployment has a resolvable recovery contract")
    scenario_targets = sorted(eligible_deployments)
    candidates.append(_candidate(
        candidate_id="scenario:availability-recovery",
        target="scenario:availability-recovery",
        target_kind="scenario",
        fault_family="pod_kill",
        applicability_plan="compile an ordered/concurrent namespace-local scenario over eligible deployment nodes",
        expected_steady_state="all selected deployment availability and business invariants hold",
        recovery_expectation="all selected replacements are Ready and business probe is stable before cleanup completes",
        validation_plan="baseline, inject ordered/concurrent faults, observe, recover, cleanup, washout",
        blocked_reasons=scenario_reasons,
        target_node_ids=scenario_targets,
        fault_families=["pod_kill", "network_loss", "container_cpu_stress"],
        business_oracle=common.get("business_oracle"),
        recovery_contract={"ready_required": True} if scenario_targets else None,
    ))
    return sorted(candidates, key=lambda item: (item["target_kind"], item["candidate_id"]))


def build_coverage_denominator(bundle: dict[str, Any], *, seed: int, snapshot_sha256: str = "") -> dict[str, Any]:
    common = _common(bundle)
    candidates = build_candidate_space(bundle)
    if not snapshot_sha256:
        snapshot_sha256 = hashlib.sha256(json.dumps(common, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    return {
        "schema_version": "chaosatlas-coverage-denominator-v1",
        "project_id": bundle.get("project_id") or common.get("project_id"),
        "project_commit": bundle.get("project_commit") or common.get("project_commit"),
        "namespace": bundle.get("namespace") or common.get("namespace"),
        "seed": seed,
        "snapshot_sha256": snapshot_sha256,
        "candidate_count": len(candidates),
        "eligible_count": sum(item["status"] == "eligible" for item in candidates),
        "blocked_count": sum(item["status"] == "blocked" for item in candidates),
        "evidence_status": "static_only",
        "runtime_results": [],
        "candidates": candidates,
    }
