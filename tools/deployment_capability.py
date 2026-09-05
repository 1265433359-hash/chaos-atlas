"""Native deployment and scenario capability contracts.

The module is deliberately side-effect free.  It turns Kubernetes manifest
facts into stable, auditable nodes and validates scenario intent before any
runner or cluster interaction occurs.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any


SCHEMA_VERSION = 3
_HEX40 = re.compile(r"^[0-9a-fA-F]{40}$")
_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
_SAFE_NAME = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,61}[a-z0-9])?$")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _labels(value: Any) -> dict[str, str]:
    return {str(k): str(v) for k, v in _mapping(value).items() if str(k).strip() and v is not None}


def _path_is_safe(path: str) -> bool:
    value = str(path).replace("\\", "/")
    if not value or value.startswith("/") or re.match(r"^[A-Za-z]:/", value):
        return False
    return all(part not in {"", ".", ".."} for part in value.split("/"))


def _containers(pod_spec: dict[str, Any]) -> list[dict[str, Any]]:
    values = pod_spec.get("containers") or []
    return [item for item in values if isinstance(item, dict)]


def _probe(container_list: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    for container in container_list:
        if isinstance(container.get(key), dict):
            return deepcopy(container[key])
    return None


def _extension_facts(deployment: dict[str, Any], pod_spec: dict[str, Any], containers: list[dict[str, Any]]) -> dict[str, Any]:
    """Normalize optional extension facts while retaining no secret values."""
    declared = _mapping(deployment.get("extensions"))
    volumes = []
    for volume in pod_spec.get("volumes") or []:
        if not isinstance(volume, dict):
            continue
        name = str(volume.get("name") or "").strip()
        if not name:
            continue
        kind = next((key for key in ("persistentVolumeClaim", "emptyDir", "hostPath", "configMap", "secret") if isinstance(volume.get(key), dict)), "unknown")
        item: dict[str, Any] = {"name": name, "kind": kind}
        if kind == "persistentVolumeClaim":
            item["claim_name"] = str((volume.get(kind) or {}).get("claimName") or "")
        volumes.append(item)
    mounts = []
    for container in containers:
        container_name = str(container.get("name") or "")
        for mount in container.get("volumeMounts") or []:
            if not isinstance(mount, dict):
                continue
            path = str(mount.get("mountPath") or "").strip()
            volume_name = str(mount.get("name") or "").strip()
            if path and volume_name:
                mounts.append({"container": container_name, "container_path": path, "volume_name": volume_name, "read_only": bool(mount.get("readOnly"))})
    facts = {
        "resource_scope": str(declared.get("resource_scope") or "deployment"),
        "mounts": mounts,
        "volumes": volumes,
        "runtime": deepcopy(_mapping(declared.get("runtime"))),
        "time_sensitive_edges": list(declared.get("time_sensitive_edges") or []),
        "capabilities": deepcopy(_mapping(declared.get("capabilities"))),
        "writable_paths": [str(item) for item in (declared.get("writable_paths") or []) if str(item).strip()],
    }
    if declared:
        facts.update({key: deepcopy(value) for key, value in declared.items() if key not in facts})
    return facts


def build_deployment_node(
    *, project_id: str, project_commit: str, namespace: str,
    deployment: dict[str, Any], service: dict[str, Any] | None,
    source_refs: list[str], manifest_sha256: str,
) -> dict[str, Any]:
    """Build a normalized deployment node without contacting Kubernetes."""
    deployment = _mapping(deployment)
    metadata = _mapping(deployment.get("metadata"))
    spec = _mapping(deployment.get("spec"))
    template = _mapping(spec.get("template"))
    template_metadata = _mapping(template.get("metadata"))
    pod_spec = _mapping(template.get("spec"))
    selector = _mapping(spec.get("selector")).get("matchLabels")
    selector = _labels(selector or template_metadata.get("labels"))
    containers = _containers(pod_spec)
    resources = {
        "requests": deepcopy(_mapping(containers[0].get("resources")).get("requests") or {}) if containers else {},
        "limits": deepcopy(_mapping(containers[0].get("resources")).get("limits") or {}) if containers else {},
    }
    profile = _mapping(deployment.get("availability_profile"))
    node = {
        "schema_version": SCHEMA_VERSION,
        "node_type": "deployment_node",
        "project_id": str(project_id),
        "project_commit": str(project_commit),
        "namespace": str(namespace),
        "deployment": {
            "name": str(metadata.get("name") or ""),
            "workload_kind": str(deployment.get("workload_kind") or "Deployment"),
            "selector": selector,
            "desired_replicas": spec.get("replicas"),
            "containers": [str(item.get("name") or "") for item in containers],
            "resources": resources,
        },
        "service": None,
        "availability_profile": {
            "pdb": deepcopy(profile.get("pdb")),
            "hpa": deepcopy(profile.get("hpa")),
            "liveness_probe": _probe(containers, "livenessProbe") or deepcopy(profile.get("liveness_probe") or {}),
            "readiness_probe": _probe(containers, "readinessProbe") or deepcopy(profile.get("readiness_probe") or {}),
            "manifest_facts_status": str(profile.get("manifest_facts_status") or "verified"),
            "recovery_contract": deepcopy(profile.get("recovery_contract") or {}),
        },
        "extensions": _extension_facts(deployment, pod_spec, containers),
        "source_refs": [str(item) for item in (source_refs or [])],
        "manifest_sha256": str(manifest_sha256),
    }
    if service is not None:
        service_metadata = _mapping(service.get("metadata"))
        service_spec = _mapping(service.get("spec"))
        ports = service_spec.get("ports") or []
        port = ports[0] if ports and isinstance(ports[0], dict) else {}
        node["service"] = {
            "name": str(service_metadata.get("name") or ""),
            "port": port.get("port"),
            "target_port": port.get("targetPort"),
            "selector": _labels(service_spec.get("selector")),
        }
    node["node_id"] = "deployment:" + _hash({key: value for key, value in node.items() if key != "node_id"})[:24]
    return node


def validate_deployment_node(node: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(node, dict):
        return ["node must be an object"]
    if node.get("node_type") != "deployment_node":
        errors.append("node_type must be deployment_node")
    if node.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version must be 3")
    for key in ("project_id", "namespace", "project_commit", "manifest_sha256"):
        if not str(node.get(key) or "").strip():
            errors.append(f"missing {key}")
    if node.get("project_commit") and not _HEX40.fullmatch(str(node["project_commit"])):
        errors.append("project_commit must be a 40-hex commit")
    if node.get("manifest_sha256") and not _HEX64.fullmatch(str(node["manifest_sha256"])):
        errors.append("manifest_sha256 must be a 64-hex digest")
    namespace = str(node.get("namespace") or "")
    if namespace and (not _SAFE_NAME.fullmatch(namespace) or namespace in {"default", "kube-system"}):
        errors.append("namespace is not an isolated DNS name")
    deployment = _mapping(node.get("deployment"))
    if not str(deployment.get("name") or ""):
        errors.append("deployment.name is required")
    selector = _labels(deployment.get("selector"))
    if not selector:
        errors.append("deployment.selector is required")
    replicas = deployment.get("desired_replicas")
    if isinstance(replicas, bool) or not isinstance(replicas, int) or replicas < 0:
        errors.append("deployment.desired_replicas must be a non-negative integer")
    containers = deployment.get("containers")
    if not isinstance(containers, list) or not containers or not all(str(item).strip() for item in containers):
        errors.append("deployment.containers is required")
    refs = node.get("source_refs")
    if not isinstance(refs, list) or not refs:
        errors.append("source_refs is required")
    else:
        for ref in refs:
            if not _path_is_safe(str(ref)):
                errors.append(f"unsafe source_ref: {ref}")
    profile = _mapping(node.get("availability_profile"))
    if profile.get("manifest_facts_status") not in {"verified", "static_blocked", "unknown"}:
        errors.append("invalid manifest_facts_status")
    if node.get("node_id"):
        expected = "deployment:" + _hash({key: value for key, value in node.items() if key != "node_id"})[:24]
        if node["node_id"] != expected:
            errors.append("node_id does not match canonical content")
    return errors


def deployment_signature(node: dict[str, Any]) -> str:
    """Return a signature over content, excluding the derived node id."""
    value = {key: deepcopy(item) for key, item in node.items() if key != "node_id"}
    return _hash(value)


def build_scenario_node(
    *, scenario_id: str, deployment_nodes: list[dict[str, Any]],
    phases: list[dict[str, Any]], oracle: dict[str, Any],
    recovery: dict[str, Any], cleanup: dict[str, Any],
) -> dict[str, Any]:
    node = {
        "schema_version": SCHEMA_VERSION,
        "node_type": "scenario_node",
        "scenario_id": str(scenario_id),
        "deployment_nodes": deepcopy(deployment_nodes),
        "phases": deepcopy(phases),
        "oracle": deepcopy(oracle),
        "recovery": deepcopy(recovery),
        "cleanup": deepcopy(cleanup),
    }
    node["scenario_signature"] = scenario_signature(node)
    return node


def validate_scenario_node(scenario: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(scenario, dict):
        return ["scenario must be an object"]
    if scenario.get("node_type") != "scenario_node":
        errors.append("node_type must be scenario_node")
    if scenario.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version must be 3")
    if not str(scenario.get("scenario_id") or "").strip():
        errors.append("scenario_id is required")
    nodes = scenario.get("deployment_nodes")
    node_ids: set[str] = set()
    if not isinstance(nodes, list) or not nodes:
        errors.append("deployment_nodes is required")
    else:
        for index, node in enumerate(nodes):
            errors.extend(f"deployment_nodes[{index}]: {item}" for item in validate_deployment_node(node))
            if isinstance(node, dict) and node.get("node_id"):
                node_ids.add(str(node["node_id"]))
    phases = scenario.get("phases")
    if not isinstance(phases, list) or not phases:
        errors.append("phases is required")
    else:
        for index, phase in enumerate(phases):
            if not isinstance(phase, dict):
                errors.append(f"phases[{index}] must be an object")
                continue
            prefix = f"phases[{index}]"
            if not str(phase.get("phase_id") or "").strip(): errors.append(f"{prefix}.phase_id is required")
            if phase.get("mode") not in {"ordered", "concurrent"}: errors.append(f"{prefix}.mode is invalid")
            duration = phase.get("duration_s")
            if isinstance(duration, bool) or not isinstance(duration, int) or not 1 <= duration <= 3600: errors.append(f"{prefix}.duration_s is invalid")
            targets = phase.get("target_node_ids")
            if not isinstance(targets, list) or not targets: errors.append(f"{prefix}.target_node_ids is required")
            else:
                for target in targets:
                    if str(target) not in node_ids: errors.append(f"{prefix} unknown target_node_id: {target}")
            if not str(phase.get("inject_confirmation") or "").strip(): errors.append(f"{prefix}.inject_confirmation is required")
            if not str(phase.get("cleanup_owner") or "").strip(): errors.append(f"{prefix}.cleanup_owner is required")
            faults = phase.get("faults")
            if not isinstance(faults, list) or not faults: errors.append(f"{prefix}.faults is required")
            else:
                for fault_index, fault in enumerate(faults):
                    fp = f"{prefix}.faults[{fault_index}]"
                    if not isinstance(fault, dict): errors.append(f"{fp} must be an object"); continue
                    for key in ("kind", "action", "selector", "parameters", "target_node_id"):
                        if key not in fault: errors.append(f"{fp}.{key} is required")
                    if str(fault.get("target_node_id")) not in node_ids: errors.append(f"{fp} unknown target_node_id")
                    if not _labels(fault.get("selector")): errors.append(f"{fp}.selector is required")
                    if not isinstance(fault.get("parameters"), dict): errors.append(f"{fp}.parameters must be object")
            if phase.get("mode") == "concurrent" and len(faults or []) < 2 and not phase.get("allow_single_target"):
                errors.append(f"{prefix}.concurrent requires at least two faults or allow_single_target")
    if not isinstance(scenario.get("oracle"), dict) or not scenario.get("oracle"): errors.append("oracle is required")
    if not isinstance(scenario.get("recovery"), dict) or not scenario.get("recovery"): errors.append("recovery is required")
    if not isinstance(scenario.get("cleanup"), dict) or not scenario.get("cleanup"): errors.append("cleanup is required")
    if scenario.get("scenario_signature") and scenario["scenario_signature"] != scenario_signature(scenario):
        errors.append("scenario_signature does not match canonical content")
    return errors


def scenario_signature(scenario: dict[str, Any]) -> str:
    return _hash({key: deepcopy(value) for key, value in scenario.items() if key != "scenario_signature"})
