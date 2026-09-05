"""Pure capability assessment and candidate generation for extension faults."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from tools.dependency_fault_capability import assess_dependency_capability, generate_dependency_candidates
from tools.extension_fault_catalog import ExtensionSpec, extension_catalog, get_extension_spec


def _facts(node: dict[str, Any]) -> dict[str, Any]:
    value = node.get("extensions")
    if not isinstance(value, dict):
        value = node.get("extension_facts")
    return value if isinstance(value, dict) else {}


def _capabilities(facts: dict[str, Any]) -> dict[str, Any]:
    value = facts.get("capabilities")
    return value if isinstance(value, dict) else {}


def _paths(facts: dict[str, Any]) -> list[str]:
    values = facts.get("writable_paths") or facts.get("io_paths") or []
    return sorted({str(item).strip() for item in values if str(item).strip()})


def _status(status: str, reason: str, *, requirements: list[str] | None = None, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "reason": reason,
        "requirements": list(requirements or []),
        "evidence": deepcopy(evidence or {}),
    }


def assess_extension_capability(
    extension_id: str,
    node: dict[str, Any],
    parameters: dict[str, Any] | None = None,
    *,
    edge: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assess one candidate without contacting Kubernetes."""
    spec = get_extension_spec(extension_id)
    facts = _facts(node)
    capabilities = _capabilities(facts)
    params = parameters if isinstance(parameters, dict) else {}
    missing = [name for name in spec.required_parameters if name not in params]
    if missing:
        return _status("inapplicable", "candidate is missing required extension parameters", requirements=missing)

    evidence = {
        "resource_scope": facts.get("resource_scope"),
        "capabilities": {key: capabilities.get(key) for key in spec.required_capabilities},
    }
    if extension_id in {"extension.dependency_delay", "extension.dependency_unreachable"}:
        resolved_edge = edge if isinstance(edge, dict) else node.get("dependency_edge")
        return assess_dependency_capability(
            extension_id,
            resolved_edge if isinstance(resolved_edge, dict) else {},
            networkchaos_available=capabilities.get("networkchaos") is True,
        )
    if spec.extension_id in {"extension.io_delay", "extension.io_error"}:
        path = str(params.get("path") or "").strip()
        allowed = _paths(facts)
        if capabilities.get("iochaos") is not True:
            return _status("blocked", "IOChaos capability is not confirmed", requirements=["iochaos"], evidence=evidence)
        if not allowed:
            return _status("inapplicable", "no writable test path or test volume was discovered", requirements=["writable_path"], evidence=evidence)
        if path not in allowed:
            return _status("blocked", "IO target path is outside the discovered allow-list", requirements=["writable_path"], evidence={**evidence, "allowed_paths": allowed, "requested_path": path})
        if capabilities.get("disposable_target") is not True:
            return _status("blocked", "IO mutation requires a disposable target", requirements=["disposable_target"], evidence=evidence)
        return _status("supported", "writable disposable IO target and IOChaos are available", evidence={**evidence, "allowed_paths": allowed, "requested_path": path})

    if spec.extension_id == "extension.time_offset":
        if capabilities.get("timechaos") is not True:
            return _status("blocked", "TimeChaos capability is not confirmed", requirements=["timechaos"], evidence=evidence)
        if capabilities.get("disposable_target") is not True:
            return _status("blocked", "time offset requires a disposable Pod target", requirements=["disposable_target"], evidence=evidence)
        return _status("supported", "Pod-level TimeChaos and disposable target are available", evidence=evidence)

    if spec.extension_id in {"extension.queue_backlog", "extension.connection_pool_exhaustion", "extension.runtime_pause"}:
        capability = spec.required_capabilities[0]
        if capabilities.get(capability) is not True:
            return _status("blocked", f"{capability} capability is not explicitly confirmed", requirements=[capability], evidence=evidence)
        if capabilities.get("disposable_target") is not True:
            return _status("blocked", "native runtime mutation requires a disposable target", requirements=["disposable_target"], evidence=evidence)
        if spec.extension_id == "extension.queue_backlog":
            queue_name = str(params.get("queue_name") or "").strip()
            if not queue_name or len(queue_name) > 128:
                return _status("inapplicable", "queue_name must identify a bounded test queue", requirements=["queue_name"], evidence=evidence)
        elif spec.extension_id == "extension.connection_pool_exhaustion":
            pool_name = str(params.get("pool_name") or "").strip()
            if not pool_name or len(pool_name) > 128:
                return _status("inapplicable", "pool_name must identify a bounded test pool", requirements=["pool_name"], evidence=evidence)
        else:
            process = str(params.get("target_process") or "").strip()
            if not process or len(process) > 128:
                return _status("inapplicable", "target_process must identify a bounded runtime process", requirements=["target_process"], evidence=evidence)
        return _status("supported", "native runtime agent and disposable target are available", evidence=evidence)

    runtime = facts.get("runtime") if isinstance(facts.get("runtime"), dict) else {}
    if runtime.get("jvm_present") is not True:
        return _status("inapplicable", "no JVM process was discovered for this workload", requirements=["jvm_present"], evidence={**evidence, "runtime": runtime})
    if capabilities.get("jvmchaos") is not True:
        return _status("blocked", "JVM fault agent capability is not confirmed", requirements=["jvmchaos"], evidence={**evidence, "runtime": runtime})
    if capabilities.get("disposable_target") is not True:
        return _status("blocked", "JVM mutation requires a disposable target", requirements=["disposable_target"], evidence={**evidence, "runtime": runtime})
    process = str(params.get("target_process") or "").strip()
    if not process or process == "unknown":
        return _status("inapplicable", "JVM target process is not identified", requirements=["target_process"], evidence={**evidence, "runtime": runtime})
    return _status("supported", "JVM process, agent capability and disposable target are available", evidence={**evidence, "runtime": runtime})


def _candidate(spec: ExtensionSpec, node: dict[str, Any], parameters: dict[str, Any]) -> dict[str, Any]:
    deployment = node.get("deployment") if isinstance(node.get("deployment"), dict) else {}
    selector = deployment.get("selector") if isinstance(deployment.get("selector"), dict) else {}
    parameter_hash = hashlib.sha256(json.dumps(parameters, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()[:12]
    return {
        "candidate_id": f"extension:{node.get('node_id')}:{spec.extension_id}:{parameter_hash}",
        "node_id": node.get("node_id"),
        "target": deployment.get("name"),
        "target_kind": "deployment",
        "namespace": node.get("namespace"),
        "selector": deepcopy(selector),
        "fault_family": spec.extension_id,
        "extension_id": spec.extension_id,
        "category": spec.category,
        "backend": spec.backend,
        "resource_scope": spec.resource_scope,
        "parameters": deepcopy(parameters),
        "risk_level": spec.risk_level,
        "compile_eligible": True,
        "extension_facts": deepcopy(_facts(node)),
    }


def generate_extension_candidates(
    nodes: list[dict[str, Any]],
    dependencies: list[dict[str, Any]] | None = None,
    *,
    networkchaos_available: bool = False,
) -> dict[str, Any]:
    """Generate only candidates passing pure project-fact applicability gates."""
    candidates: list[dict[str, Any]] = []
    matrix: list[dict[str, Any]] = []
    for node in nodes:
        facts = _facts(node)
        paths = _paths(facts)
        runtime = facts.get("runtime") if isinstance(facts.get("runtime"), dict) else {}
        parameters_by_extension = {
            "extension.io_delay": {"path": paths[0] if paths else "", "latency_ms": 100, "percent": 25, "duration_s": 10},
            "extension.io_error": {"path": paths[0] if paths else "", "errno": 5, "percent": 10, "duration_s": 10},
            "extension.time_offset": {"offset_ms": 500, "duration_s": 10},
            "extension.dependency_delay": {"duration_s": 10},
            "extension.dependency_unreachable": {"duration_s": 10},
            "extension.jvm_gc_pause": {"target_process": str(runtime.get("process_name") or ""), "pause_ms": 100, "duration_s": 10},
            "extension.queue_backlog": {"queue_name": "chaosatlas-test-queue", "depth": 100, "duration_s": 10},
            "extension.connection_pool_exhaustion": {"pool_name": "chaosatlas-test-pool", "connections": 20, "duration_s": 10},
            "extension.runtime_pause": {"target_process": str(runtime.get("process_name") or "python"), "pause_ms": 100, "duration_s": 10},
        }
        for extension_id, spec_dict in extension_catalog().items():
            assessment = assess_extension_capability(extension_id, node, parameters_by_extension[extension_id])
            matrix.append({
                "node_id": node.get("node_id"),
                "extension_id": extension_id,
                "category": spec_dict["category"],
                **assessment,
            })
            if assessment["status"] == "supported":
                candidates.append(_candidate(get_extension_spec(extension_id), node, parameters_by_extension[extension_id]))
    dependency_space = generate_dependency_candidates(
        nodes,
        dependencies or [],
        networkchaos_available=networkchaos_available,
    )
    matrix.extend(dependency_space["matrix"])
    candidates.extend(dependency_space["candidates"])
    return {
        "schema_version": "chaosatlas-extension-capability-matrix-v1",
        "candidate_count": len(candidates),
        "matrix": matrix,
        "candidates": candidates,
    }
