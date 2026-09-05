"""Generic dependency-edge candidate generation for network-backed faults."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any


DEPENDENCY_EXTENSIONS = (
    "extension.dependency_delay",
    "extension.dependency_unreachable",
)


def _selector(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in sorted(value.items()) if str(key).strip() and str(item).strip()}


def normalize_declared_dependency_edges(
    declarations: Any,
    services: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve profile edge names against live Service selectors.

    The profile declares intent using stable Service names. Selectors are
    always taken from the live inventory so a stale label cannot silently
    redirect a mutation.
    """

    service_by_name = {
        str((item.get("metadata") or {}).get("name") or ""): item
        for item in services
        if isinstance(item, dict)
    }
    result: list[dict[str, Any]] = []
    for declaration in declarations if isinstance(declarations, list) else []:
        if not isinstance(declaration, dict):
            continue
        edge_id = str(declaration.get("id") or "").strip()
        source = str(declaration.get("source") or "").strip()
        target = str(declaration.get("target") or "").strip()
        source_service = service_by_name.get(source) or {}
        target_service = service_by_name.get(target) or {}
        source_selector = _selector((source_service.get("spec") or {}).get("selector"))
        target_selector = _selector((target_service.get("spec") or {}).get("selector"))
        if not edge_id or not source or not target or not source_selector or not target_selector:
            continue
        edge = {
            "id": edge_id,
            "source": source,
            "target": target,
            "source_kind": "service",
            "target_kind": "service",
            "source_selector": source_selector,
            "target_selector": target_selector,
            "target_port": declaration.get("target_port"),
            "oracle_id": str(declaration.get("oracle_id") or ""),
            "evidence": f"service/{source}->service/{target}",
        }
        result.append(edge)
    return sorted(result, key=lambda item: item["id"])


def assess_dependency_capability(
    extension_id: str,
    edge: dict[str, Any],
    *,
    networkchaos_available: bool,
) -> dict[str, Any]:
    """Assess one dependency edge without contacting the cluster."""

    if extension_id not in DEPENDENCY_EXTENSIONS:
        return {"status": "inapplicable", "reason": "unknown dependency extension"}
    source_selector = _selector(edge.get("source_selector"))
    target_selector = _selector(edge.get("target_selector"))
    if not source_selector or not target_selector:
        return {
            "status": "inapplicable",
            "reason": "dependency edge has no resolved source and target selectors",
        }
    if not networkchaos_available:
        return {
            "status": "blocked",
            "reason": "NetworkChaos capability is not confirmed",
            "requirements": ["networkchaos"],
        }
    return {
        "status": "supported",
        "reason": "resolved dependency edge and NetworkChaos are available",
        "requirements": [],
        "evidence": {
            "source": edge.get("source"),
            "target": edge.get("target"),
            "source_selector": source_selector,
            "target_selector": target_selector,
        },
    }


def generate_dependency_candidates(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    networkchaos_available: bool,
) -> dict[str, Any]:
    """Generate stable dependency-edge candidates for every matching source node."""

    service_to_node = {
        str((node.get("service") or {}).get("name") or ""): node
        for node in nodes
        if isinstance(node, dict)
    }
    candidates: list[dict[str, Any]] = []
    matrix: list[dict[str, Any]] = []
    defaults = {
        "extension.dependency_delay": {
            "latency_ms": 100,
            "jitter_ms": 0,
            "correlation": 100,
            "duration_s": 10,
        },
        "extension.dependency_unreachable": {
            "loss_percent": 100,
            "correlation": 100,
            "duration_s": 10,
        },
    }
    for edge in edges:
        source = str(edge.get("source") or "")
        node = service_to_node.get(source)
        for extension_id in DEPENDENCY_EXTENSIONS:
            assessment = assess_dependency_capability(
                extension_id,
                edge,
                networkchaos_available=networkchaos_available,
            )
            matrix.append({
                "extension_id": extension_id,
                "dependency_edge_id": edge.get("id"),
                "source": source,
                "target": edge.get("target"),
                **assessment,
            })
            if node is None or assessment.get("status") != "supported":
                continue
            parameters = deepcopy(defaults[extension_id])
            identity = {
                "node_id": node.get("node_id"),
                "extension_id": extension_id,
                "edge_id": edge.get("id"),
                "parameters": parameters,
            }
            digest = hashlib.sha256(
                json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
            ).hexdigest()[:12]
            candidates.append({
                "candidate_id": f"dependency:{node.get('node_id')}:{edge.get('id')}:{extension_id}:{digest}",
                "node_id": node.get("node_id"),
                "target": f"{source}->{edge.get('target')}",
                "target_kind": "dependency_edge",
                "namespace": node.get("namespace"),
                "selector": _selector(edge.get("source_selector")),
                "fault_family": extension_id,
                "extension_id": extension_id,
                "category": "dependency_network",
                "backend": "NetworkChaos",
                "resource_scope": "dependency_edge",
                "parameters": parameters,
                "edge": deepcopy(edge),
                "dependency_edge_id": edge.get("id"),
                "oracle_id": edge.get("oracle_id"),
                "risk_level": "high" if extension_id.endswith("unreachable") else "medium",
                "compile_eligible": True,
            })
    return {
        "schema_version": "chaosatlas-dependency-capability-matrix-v1",
        "candidate_count": len(candidates),
        "matrix": matrix,
        "candidates": candidates,
    }
