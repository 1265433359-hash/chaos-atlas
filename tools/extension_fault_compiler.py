"""Compile provisional extension intents into auditable mutation manifests."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any

from tools.extension_capability import assess_extension_capability
from tools.extension_fault_catalog import get_extension_spec


def _name(value: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")[:50] or "extension"


def _duration(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 3600:
        raise ValueError("duration_s must be an integer in [1, 3600]")
    return f"{value}s"


def _selector(fault: dict[str, Any], node: dict[str, Any]) -> dict[str, str]:
    value = fault.get("selector")
    if not isinstance(value, dict) or not value:
        value = ((node.get("deployment") or {}).get("selector") or {})
    if not isinstance(value, dict) or not value:
        raise ValueError("extension selector is required")
    return {str(key): str(item) for key, item in sorted(value.items())}


def _label_selector(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        return {}
    return {str(key): str(item) for key, item in sorted(value.items()) if str(key).strip() and str(item).strip()}


def _signed_milliseconds(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, int) or value == 0 or abs(value) > 86_400_000:
        raise ValueError("offset_ms must be a non-zero integer in [-86400000, 86400000]")
    sign = "+" if value > 0 else "-"
    return f"{sign}{abs(value)}ms"


def compile_extension_fault(
    scenario: dict[str, Any],
    phase: dict[str, Any],
    fault: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    extension_id = str(fault.get("kind") or fault.get("extension_id") or "").strip()
    spec = get_extension_spec(extension_id)
    node = next((item for item in scenario.get("deployment_nodes") or [] if item.get("node_id") == fault.get("target_node_id")), None)
    if not isinstance(node, dict):
        raise ValueError("extension target node was not found")
    parameters = fault.get("parameters")
    if not isinstance(parameters, dict) or set(parameters) != set(spec.required_parameters):
        raise ValueError(f"{extension_id} parameters must be exactly {list(spec.required_parameters)}")
    assessment_node = deepcopy(node)
    if extension_id in {"extension.dependency_delay", "extension.dependency_unreachable"}:
        facts = assessment_node.get("extensions") if isinstance(assessment_node.get("extensions"), dict) else {}
        capabilities = facts.get("capabilities") if isinstance(facts.get("capabilities"), dict) else {}
        facts = deepcopy(facts)
        capabilities = deepcopy(capabilities)
        capabilities["networkchaos"] = True
        facts["capabilities"] = capabilities
        assessment_node["extensions"] = facts
    assessment = assess_extension_capability(
        extension_id,
        assessment_node,
        parameters,
        edge=fault.get("edge") if isinstance(fault.get("edge"), dict) else None,
    )
    if assessment["status"] != "supported":
        raise ValueError(f"extension capability is not supported: {assessment['reason']}")
    namespace = str(node.get("namespace") or "").strip()
    if not namespace:
        raise ValueError("extension target namespace is required")
    selector = _selector(fault, node)
    base = {"mode": "one", "selector": {"namespaces": [namespace], "labelSelectors": selector}}
    if extension_id in {"extension.dependency_delay", "extension.dependency_unreachable"}:
        edge = fault.get("edge")
        if not isinstance(edge, dict):
            raise ValueError("dependency extension requires a resolved edge")
        source_selector = _label_selector(edge.get("source_selector"))
        target_selector = _label_selector(edge.get("target_selector"))
        if source_selector != selector or not target_selector:
            raise ValueError("dependency edge selectors must match the source and have a target")
        target = {"mode": "one", "selector": {"namespaces": [namespace], "labelSelectors": target_selector}}
        if extension_id == "extension.dependency_delay":
            latency = parameters.get("latency_ms")
            jitter = parameters.get("jitter_ms")
            correlation = parameters.get("correlation")
            if any(isinstance(value, bool) or not isinstance(value, int) for value in (latency, jitter, correlation)):
                raise ValueError("dependency delay parameters must be integers")
            if not 1 <= latency <= 300_000 or not 0 <= jitter <= 300_000 or not 0 <= correlation <= 100:
                raise ValueError("dependency delay parameters are out of range")
            spec_body = {
                **base,
                "action": "delay",
                "direction": "to",
                "target": target,
                "delay": {"latency": f"{latency}ms", "jitter": f"{jitter}ms", "correlation": str(correlation)},
                "duration": _duration(parameters["duration_s"]),
            }
        else:
            loss = parameters.get("loss_percent")
            correlation = parameters.get("correlation")
            if any(isinstance(value, bool) or not isinstance(value, int) for value in (loss, correlation)):
                raise ValueError("dependency unreachable parameters must be integers")
            if not 1 <= loss <= 100 or not 0 <= correlation <= 100:
                raise ValueError("dependency unreachable parameters are out of range")
            spec_body = {
                **base,
                "action": "loss",
                "direction": "to",
                "target": target,
                "loss": {"loss": str(loss), "correlation": str(correlation)},
                "duration": _duration(parameters["duration_s"]),
            }
        api_kind = "NetworkChaos"
    elif extension_id in {"extension.io_delay", "extension.io_error"}:
        path = str(parameters["path"]).strip()
        latency = parameters.get("latency_ms")
        percent = parameters.get("percent")
        if not path.startswith("/") or ".." in path.split("/"):
            raise ValueError("IO path must be an absolute safe path")
        if isinstance(percent, bool) or not isinstance(percent, int) or not 1 <= percent <= 100:
            raise ValueError("IO percent must be in [1, 100]")
        if extension_id == "extension.io_delay":
            if isinstance(latency, bool) or not isinstance(latency, int) or not 1 <= latency <= 300_000:
                raise ValueError("latency_ms must be in [1, 300000]")
            spec_body = {**base, "action": "latency", "volumePath": path, "path": path, "delay": f"{latency}ms", "percent": percent, "duration": _duration(parameters["duration_s"])}
        else:
            errno = parameters.get("errno")
            if isinstance(errno, bool) or not isinstance(errno, int) or not 1 <= errno <= 255:
                raise ValueError("errno must be in [1, 255]")
            spec_body = {**base, "action": "fault", "volumePath": path, "path": path, "errno": errno, "percent": percent, "duration": _duration(parameters["duration_s"])}
        api_kind = "IOChaos"
    elif extension_id == "extension.time_offset":
        spec_body = {**base, "timeOffset": _signed_milliseconds(parameters["offset_ms"]), "clockIds": ["CLOCK_REALTIME"], "duration": _duration(parameters["duration_s"])}
        api_kind = "TimeChaos"
    elif extension_id == "extension.jvm_gc_pause":
        pause = parameters.get("pause_ms")
        if isinstance(pause, bool) or not isinstance(pause, int) or not 1 <= pause <= 300_000:
            raise ValueError("pause_ms must be in [1, 300000]")
        process = str(parameters["target_process"]).strip()
        if not process or len(process) > 128 or not re.fullmatch(r"[A-Za-z0-9_.:/-]+", process):
            raise ValueError("target_process contains unsafe characters")
        runtime = ((node.get("extensions") or {}).get("runtime") or {}) if isinstance(node.get("extensions"), dict) else {}
        pid = runtime.get("pid_hint")
        if isinstance(pid, bool) or not isinstance(pid, int) or pid < 1:
            raise ValueError("jvm_gc_pause requires a positive runtime.pid_hint")
        api_kind = "JVMChaos"
        spec_body = {**base, "action": "latency", "pid": pid, "latency": pause, "duration": _duration(parameters["duration_s"])}
    elif extension_id in {"extension.queue_backlog", "extension.connection_pool_exhaustion", "extension.runtime_pause"}:
        _duration(parameters["duration_s"])
        if extension_id == "extension.queue_backlog":
            queue_name = str(parameters["queue_name"]).strip()
            depth = parameters["depth"]
            if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", queue_name):
                raise ValueError("queue_name contains unsafe characters")
            if isinstance(depth, bool) or not isinstance(depth, int) or not 1 <= depth <= 1_000_000:
                raise ValueError("queue depth must be in [1, 1000000]")
        elif extension_id == "extension.connection_pool_exhaustion":
            pool_name = str(parameters["pool_name"]).strip()
            connections = parameters["connections"]
            if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", pool_name):
                raise ValueError("pool_name contains unsafe characters")
            if isinstance(connections, bool) or not isinstance(connections, int) or not 1 <= connections <= 10_000:
                raise ValueError("connections must be in [1, 10000]")
        else:
            process = str(parameters["target_process"]).strip()
            pause = parameters["pause_ms"]
            if not process or not re.fullmatch(r"[A-Za-z0-9_.:/-]+", process):
                raise ValueError("target_process contains unsafe characters")
            if isinstance(pause, bool) or not isinstance(pause, int) or not 1 <= pause <= 300_000:
                raise ValueError("pause_ms must be in [1, 300000]")
        api_kind = "ChaosAtlasNativeExtension"
        spec_body = {
            "faultFamily": extension_id,
            "targetRef": {"apiVersion": "apps/v1", "kind": "Deployment", "name": str(((node.get("deployment") or {}).get("name") or "")).strip()},
            "targetSelector": {str(key): str(value) for key, value in sorted(selector.items())},
            "parameters": {str(key): value for key, value in sorted(parameters.items())},
        }
    digest = hashlib.sha256(json.dumps({"phase": phase.get("phase_id"), "fault": fault}, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:12]
    labels = {
        "chaosatlas.dev/scenario": str(scenario.get("scenario_id") or ""),
        "chaosatlas.dev/phase": str(phase.get("phase_id") or ""),
        "chaosatlas.dev/cleanup-owner": str(phase.get("cleanup_owner") or "chaosatlas"),
        "chaosatlas.dev/extension": extension_id.replace(".", "-"),
    }
    return {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": api_kind,
        "metadata": {"name": f"atlas-{_name(str(scenario.get('scenario_id') or 'scenario'))}-{_name(str(phase.get('phase_id') or 'phase'))}-{index}-{digest}", "namespace": namespace, "labels": labels},
        "spec": spec_body,
        "chaosatlas_extension": {"extension_id": extension_id, "category": spec.category, "backend": spec.backend, "assessment": assessment},
    }
