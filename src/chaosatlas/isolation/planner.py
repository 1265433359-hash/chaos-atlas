"""Deterministic L1/L2/L3 isolation planning."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from chaosatlas.isolation.contracts import ISOLATION_LEVELS, canonical_hash, redact_sensitive, sensitive_paths, with_hash


def _safe_fragment(value: Any) -> str:
    result = re.sub(r"[^a-z0-9-]+", "-", str(value or "").lower()).strip("-")
    return result[:32] or "project"


class IsolationPlanner:
    """Turn capability and target facts into a side-effect-free plan."""

    def plan(
        self,
        *,
        profile: dict[str, Any],
        capability: dict[str, Any],
        target: dict[str, Any] | None = None,
        proposed_isolation: str | None = None,
    ) -> dict[str, Any]:
        requested = str(capability.get("required_isolation") or "")
        blockers: list[str] = []
        if requested not in ISOLATION_LEVELS:
            requested = "L3"
            blockers.append("invalid_required_isolation")
        proposed = str(proposed_isolation or requested)
        if proposed not in ISOLATION_LEVELS:
            blockers.append("invalid_proposed_isolation")
            proposed = requested
        mechanism_minimum = "L1"
        isolation_reasons = [f"capability_required:{requested}", f"proposed:{proposed}"]
        if capability.get("fault_id") == "api_server_delay":
            mechanism_minimum = "L3"
            isolation_reasons.append("control_plane_fault_requires_disposable_cluster")
        if capability.get("fault_id") == "stress_memory":
            limits = (((target or {}).get("deployment") or {}).get("resources") or {}).get("limits") or {}
            if not limits.get("memory"):
                mechanism_minimum = "L2"
                isolation_reasons.append("unbounded_memory_target_requires_ephemeral_target")
        effective = ISOLATION_LEVELS[max(
            ISOLATION_LEVELS.index(requested),
            ISOLATION_LEVELS.index(proposed),
            ISOLATION_LEVELS.index(mechanism_minimum),
        )]
        status = str(capability.get("capability_status") or "")
        if status in {"inapplicable", "unsupported"}:
            blockers.append(f"capability_{status}")

        isolation = profile.get("isolation") if isinstance(profile.get("isolation"), dict) else {}
        if isolation.get("synthetic_data_only") is not True:
            blockers.append("synthetic_data_only_declaration_required")
        config = isolation.get(effective.lower()) if isinstance(isolation.get(effective.lower()), dict) else {}
        provider = {"L1": "kubernetes-l1", "L2": "kubernetes-l2", "L3": "minikube-l3"}[effective]
        mode = str(config.get("mode") or {"L1": "adopted-test-replica", "L2": "ephemeral-target", "L3": "ephemeral-cluster"}[effective])
        namespaces = ((profile.get("namespace_policy") or {}).get("allowed_namespaces") or [])
        source_namespace = str(config.get("namespace") or (namespaces[0] if len(namespaces) == 1 else ""))
        if effective == "L1":
            if mode == "adopted-test-replica":
                if config.get("dedicated_test_replica") is not True or not source_namespace:
                    blockers.append("dedicated_test_replica_declaration_required")
                if source_namespace not in namespaces:
                    blockers.append("source_namespace_not_allowlisted")
                if not re.fullmatch(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?", source_namespace) or source_namespace == "default" or source_namespace.startswith("kube-"):
                    blockers.append("unsafe_source_namespace")
                if config.get("external_data_endpoints") not in (None, []):
                    blockers.append("external_data_endpoints_forbidden")
            elif mode == "ephemeral-app-clone":
                if not isinstance(config.get("blueprint"), dict):
                    blockers.append("l1_blueprint_required")
            else:
                blockers.append("unsupported_l1_mode")
        elif effective == "L2":
            extensions = (target or {}).get("extensions") if isinstance((target or {}).get("extensions"), dict) else {}
            container_blueprints = extensions.get("container_blueprints") if isinstance(extensions.get("container_blueprints"), list) else []
            if not isinstance(config.get("blueprint"), dict) and not container_blueprints:
                blockers.append("sandbox_blueprint_or_container_facts_required")
        else:
            if mode != "ephemeral-cluster":
                blockers.append("unsupported_l3_mode")

        project_id = str(profile.get("project_id") or "")
        if not project_id:
            blockers.append("project_id_required")
        exposed = sensitive_paths({"config": config, "target": target})
        blockers.extend(f"sensitive_material_detected:{path}" for path in exposed)
        safe_config = redact_sensitive(config)
        safe_target = redact_sensitive(target)
        identity = {
            "project_id": project_id,
            "project_revision": str(profile.get("project_commit") or ""),
            "capability_id": str(capability.get("fault_id") or ""),
            "target_id": capability.get("target_id"),
            "requested_isolation": requested,
            "proposed_isolation": proposed,
            "mechanism_minimum_isolation": mechanism_minimum,
            "effective_isolation": effective,
            "provider": provider,
            "mode": mode,
            "source_namespace": source_namespace,
            "config": safe_config,
            "target_sha256": canonical_hash(safe_target or {}),
            "parent_lease_id": (profile.get("runtime_contract") or {}).get("parent_isolation_lease_id"),
        }
        plan = {
            "schema_version": "chaosatlas-isolation-plan-v2",
            "plan_id": f"plan-{canonical_hash(identity)[:20]}",
            "project_id": project_id,
            "project_revision": str(profile.get("project_commit") or ""),
            "capability_id": str(capability.get("fault_id") or ""),
            "target_id": capability.get("target_id"),
            "requested_isolation": requested,
            "proposed_isolation": proposed,
            "mechanism_minimum_isolation": mechanism_minimum,
            "effective_isolation": effective,
            "isolation_reasons": isolation_reasons,
            "provider": provider,
            "mode": mode,
            "source_namespace": source_namespace or None,
            "target_namespace_or_profile": f"ca-{effective.lower()}-{_safe_fragment(project_id)}-<lease>",
            "resource_budget": deepcopy(config.get("resource_budget") or {"cpu": "2", "memory": "2Gi", "pods": 20}),
            "ready_timeout_s": int(config.get("ready_timeout_s") or 180),
            "expected_workloads": deepcopy(config.get("expected_workloads") or []),
            "blueprint": deepcopy(safe_config.get("blueprint")) if isinstance(safe_config.get("blueprint"), dict) else None,
            "target": deepcopy(safe_target),
            "kube_context": str(config.get("kube_context") or ((profile.get("runtime_contract") or {}).get("kube_context")) or "") or None,
            "parent_lease_id": (profile.get("runtime_contract") or {}).get("parent_isolation_lease_id"),
            "synthetic_data_only": True,
            "forbidden_source_kinds": ["Secret", "PersistentVolume", "PersistentVolumeClaim"],
            "required_checks": ["ownership", "ready", "cleanup", "absence", "sensitive_scan"],
            "status": "blocked" if blockers else "ready",
            "blockers": sorted(set(blockers)),
        }
        return with_hash(plan, "plan_sha256")
