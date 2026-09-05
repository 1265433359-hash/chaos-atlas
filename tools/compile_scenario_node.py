"""Compile a validated scenario node into canonical Chaos Mesh manifests."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

try:
    from tools.deployment_capability import scenario_signature, validate_scenario_node
except ModuleNotFoundError:
    from deployment_capability import scenario_signature, validate_scenario_node
try:
    from tools.extension_fault_catalog import is_extension_fault
    from tools.extension_fault_compiler import compile_extension_fault
except ModuleNotFoundError:
    from extension_fault_catalog import is_extension_fault
    from extension_fault_compiler import compile_extension_fault


SUPPORTED = {
    "pod_kill",
    "backend_pod_kill",
    "container_kill",
    "stress_cpu",
    "stress_memory",
    "network_loss",
    "network_partition",
    "network_delay",
    "network_bandwidth",
    "network_duplicate",
    "network_corrupt",
    "dns_failure",
    "dns_delay",
    "http_delay",
    "http_abort",
    "http_status_error",
    "http_response_corrupt",
    "dependency_error",
    "connection_reset",
    "http_rate_limit",
    "business_dependency_unreachable",
    "replica_reduction",
    "config_reload",
    "config_drift",
    "env_misconfiguration",
    "secret_rotation",
    "rollout_pause",
    "image_pull_failure",
    "pod_unschedulable",
    "api_server_delay",
    "disk_pressure",
    "file_descriptor_exhaustion",
    "process_exhaustion",
}


def _name(value: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")[:50] or "phase"


def _duration(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 3600:
        raise ValueError("duration_s must be an integer in [1, 3600]")
    return f"{value}s"


def _manifest(scenario: dict[str, Any], phase: dict[str, Any], fault: dict[str, Any], index: int) -> dict[str, Any]:
    kind = str(fault.get("kind"))
    if is_extension_fault(kind):
        return compile_extension_fault(scenario, phase, fault, index)
    if kind not in SUPPORTED:
        raise ValueError(f"unsupported fault kind: {kind}")
    node = next(item for item in scenario["deployment_nodes"] if item.get("node_id") == fault.get("target_node_id"))
    namespace = str(node["namespace"])
    selector = deepcopy(fault.get("selector"))
    if not isinstance(selector, dict) or not selector:
        raise ValueError("fault selector is required")
    base = {
        "selector": {
            "namespaces": [namespace],
            "labelSelectors": {str(key): str(value) for key, value in sorted(selector.items())},
        },
    }
    parameters = fault.get("parameters") or {}
    if kind in {"pod_kill", "backend_pod_kill"}:
        if parameters != {"mode": "one"}: raise ValueError("pod_kill parameters must be {'mode': 'one'}")
        api_kind, spec = "PodChaos", {**base, "action": "pod-kill", "mode": "one", "duration": _duration(phase["duration_s"])}
    elif kind == "container_kill":
        if set(parameters) != {"container"} or not str(parameters.get("container")): raise ValueError("container_kill requires container")
        api_kind, spec = "PodChaos", {**base, "action": "container-kill", "containerNames": [str(parameters["container"])], "mode": "one", "duration": _duration(phase["duration_s"])}
    elif kind == "stress_cpu":
        if set(parameters) != {"workers", "load_percent"}: raise ValueError("stress_cpu requires workers and load_percent")
        api_kind, spec = "StressChaos", {**base, "mode": "one", "stressors": {"cpu": {"workers": int(parameters["workers"]), "load": int(parameters["load_percent"])}}, "duration": _duration(phase["duration_s"])}
    elif kind == "stress_memory":
        if set(parameters) != {"size_mb"}: raise ValueError("stress_memory requires size_mb")
        api_kind, spec = "StressChaos", {**base, "mode": "one", "stressors": {"memory": {"workers": 1, "size": f"{int(parameters['size_mb'])}MB"}}, "duration": _duration(phase["duration_s"])}
    elif kind == "network_loss":
        if set(parameters) != {"loss_percent"}: raise ValueError("network_loss requires loss_percent")
        api_kind, spec = "NetworkChaos", {**base, "action": "loss", "mode": "one", "loss": {"loss": str(int(parameters["loss_percent"])), "correlation": "100"}, "duration": _duration(phase["duration_s"]), "direction": "to"}
    elif kind == "network_delay":
        if set(parameters) != {"latency_ms", "jitter_ms", "correlation"}: raise ValueError("network_delay requires latency_ms, jitter_ms and correlation")
        latency = int(parameters["latency_ms"])
        jitter = int(parameters["jitter_ms"])
        correlation = int(parameters["correlation"])
        if latency < 1 or jitter < 0 or not 0 <= correlation <= 100:
            raise ValueError("network_delay parameters are out of range")
        api_kind, spec = "NetworkChaos", {**base, "action": "delay", "mode": "one", "delay": {"latency": f"{latency}ms", "jitter": f"{jitter}ms", "correlation": str(correlation)}, "duration": _duration(phase["duration_s"]), "direction": "to"}
    elif kind == "network_bandwidth":
        if set(parameters) != {"rate", "limit", "buffer"}: raise ValueError("network_bandwidth requires rate, limit and buffer")
        rate = str(parameters["rate"]).strip().lower()
        if not re.fullmatch(r"[1-9][0-9]*(?:kbps|mbps|gbps)", rate): raise ValueError("network_bandwidth rate must use kbps, mbps or gbps")
        limit = int(parameters["limit"])
        buffer = int(parameters["buffer"])
        if not 1 <= limit <= 1_000_000 or not 1 <= buffer <= 1_000_000: raise ValueError("network_bandwidth limit and buffer must be in [1, 1000000]")
        api_kind, spec = "NetworkChaos", {**base, "action": "bandwidth", "mode": "one", "bandwidth": {"rate": rate, "limit": limit, "buffer": buffer}, "duration": _duration(phase["duration_s"]), "direction": "to"}
    elif kind in {"network_duplicate", "network_corrupt"}:
        expected = "duplicate_percent" if kind == "network_duplicate" else "corrupt_percent"
        if set(parameters) != {expected, "correlation"}: raise ValueError(f"{kind} requires {expected} and correlation")
        percent = int(parameters[expected])
        correlation = int(parameters["correlation"])
        if not 0 <= percent <= 100 or not 0 <= correlation <= 100: raise ValueError(f"{kind} percentages must be in [0, 100]")
        action = "duplicate" if kind == "network_duplicate" else "corrupt"
        api_kind, spec = "NetworkChaos", {**base, "action": action, "mode": "one", action: {action: str(percent), "correlation": str(correlation)}, "duration": _duration(phase["duration_s"]), "direction": "to"}
    elif kind == "dns_failure":
        if set(parameters) != {"hostname"} or not str(parameters.get("hostname") or "").strip():
            raise ValueError("dns_failure requires hostname")
        api_kind, spec = "DNSChaos", {**base, "action": "error", "mode": "one", "patterns": [str(parameters["hostname"]).strip()], "duration": _duration(phase["duration_s"])}
    elif kind == "dns_delay":
        if set(parameters) != {"hostname", "latency_ms"} or not str(parameters.get("hostname") or "").strip():
            raise ValueError("dns_delay requires hostname and latency_ms")
        latency = int(parameters["latency_ms"])
        if not 1 <= latency <= 300_000:
            raise ValueError("dns_delay latency_ms must be in [1, 300000]")
        api_kind, spec = "DNSChaos", {**base, "action": "delay", "mode": "one", "patterns": [str(parameters["hostname"]).strip()], "delay": {"latency": f"{latency}ms"}, "duration": _duration(phase["duration_s"])}
    elif kind in {"http_delay", "http_abort", "http_status_error", "http_response_corrupt", "dependency_error", "connection_reset"}:
        port = int(parameters.get("port", 0))
        path = str(parameters.get("path") or "").strip()
        if not 1 <= port <= 65535 or not path.startswith("/"):
            raise ValueError("HTTP fault requires port in [1, 65535] and an absolute path")
        http_base = {**base, "mode": "one", "target": "Request", "port": port, "path": path}
        if kind == "http_delay":
            if set(parameters) != {"latency_ms", "port", "path"}: raise ValueError("http_delay requires latency_ms, port and path")
            latency = int(parameters["latency_ms"])
            if not 1 <= latency <= 300_000: raise ValueError("http_delay latency_ms must be in [1, 300000]")
            api_kind, spec = "HTTPChaos", {**http_base, "delay": f"{latency}ms", "duration": _duration(phase["duration_s"])}
        elif kind == "http_abort":
            if set(parameters) != {"port", "path"}: raise ValueError("http_abort requires port and path")
            api_kind, spec = "HTTPChaos", {**http_base, "abort": True, "duration": _duration(phase["duration_s"])}
        elif kind == "http_status_error":
            if set(parameters) != {"port", "path", "status_code"}: raise ValueError("http_status_error requires port, path and status_code")
            status_code = int(parameters["status_code"])
            if not 400 <= status_code <= 599: raise ValueError("http_status_error status_code must be in [400, 599]")
            api_kind, spec = "HTTPChaos", {**http_base, "replace": {"code": status_code}, "duration": _duration(phase["duration_s"])}
        elif kind == "http_response_corrupt":
            if set(parameters) != {"port", "path", "body"}: raise ValueError("http_response_corrupt requires body, port and path")
            body = str(parameters.get("body") or "")
            if not body.strip() or len(body.encode("utf-8")) > 65536: raise ValueError("http_response_corrupt body must be non-empty and at most 65536 bytes")
            encoded_body = base64.b64encode(body.encode("utf-8")).decode("ascii")
            api_kind, spec = "HTTPChaos", {**http_base, "replace": {"body": encoded_body}, "duration": _duration(phase["duration_s"])}
        elif kind == "dependency_error":
            if set(parameters) != {"port", "path", "status_code"}: raise ValueError("dependency_error requires port, path and status_code")
            status_code = int(parameters["status_code"])
            if not 500 <= status_code <= 599: raise ValueError("dependency_error status_code must be in [500, 599]")
            api_kind, spec = "HTTPChaos", {**http_base, "replace": {"code": status_code}, "duration": _duration(phase["duration_s"])}
        else:
            if set(parameters) != {"port", "path"}: raise ValueError("connection_reset requires port and path")
            api_kind, spec = "HTTPChaos", {**http_base, "abort": True, "duration": _duration(phase["duration_s"])}
    elif kind in {"http_rate_limit", "business_dependency_unreachable"}:
        deployment_name = str(((node.get("deployment") or {}).get("name") or "")).strip()
        if not deployment_name:
            raise ValueError("native HTTP fault requires deployment name")
        if kind == "http_rate_limit":
            required = {"requests_per_window", "window_s", "status_code"}
            if set(parameters) not in (required, required | {"port", "path"}):
                raise ValueError("http_rate_limit requires requests_per_window, window_s and status_code")
            requests_per_window = parameters.get("requests_per_window")
            window_s = parameters.get("window_s")
            status_code = parameters.get("status_code")
            if isinstance(requests_per_window, bool) or not isinstance(requests_per_window, int) or not 1 <= requests_per_window <= 1000:
                raise ValueError("http_rate_limit requests_per_window must be in [1, 1000]")
            if isinstance(window_s, bool) or not isinstance(window_s, int) or not 1 <= window_s <= 60:
                raise ValueError("http_rate_limit window_s must be in [1, 60]")
            if status_code != 429:
                raise ValueError("http_rate_limit status_code must be 429")
        elif parameters and set(parameters) != {"port", "path"}:
            raise ValueError("business_dependency_unreachable accepts optional port and path")
        if parameters and "port" in parameters:
            route_port = parameters.get("port")
            route_path = str(parameters.get("path") or "")
            if isinstance(route_port, bool) or not isinstance(route_port, int) or not 1 <= route_port <= 65535 or not route_path.startswith("/"):
                raise ValueError("native HTTP route requires port in [1, 65535] and an absolute path")
        api_kind = "ChaosAtlasNativeHttpFault"
        spec = {
            "faultFamily": kind,
            "targetRef": {"apiVersion": "apps/v1", "kind": "Deployment", "name": deployment_name},
            "targetSelector": {str(key): str(value) for key, value in sorted(selector.items())},
            "parameters": {str(key): value for key, value in sorted(parameters.items())},
        }
    elif kind in {"replica_reduction", "config_reload", "config_drift", "env_misconfiguration", "secret_rotation", "rollout_pause", "image_pull_failure", "pod_unschedulable"}:
        deployment_name = str(((node.get("deployment") or {}).get("name") or "")).strip()
        if not deployment_name:
            raise ValueError("Kubernetes API fault requires deployment name")
        target_kind = str(((node.get("deployment") or {}).get("workload_kind") or "Deployment"))
        if target_kind not in {"Deployment", "StatefulSet", "DaemonSet"}:
            raise ValueError("unsupported Kubernetes workload kind")
        target_name = deployment_name
        if kind == "replica_reduction":
            if set(parameters) != {"replicas"}:
                raise ValueError("replica_reduction requires replicas")
            replicas = parameters.get("replicas")
            if isinstance(replicas, bool) or not isinstance(replicas, int) or replicas < 0:
                raise ValueError("replica_reduction replicas must be a non-negative integer")
        elif kind == "config_reload":
            if set(parameters) != {"reload_token"} or not str(parameters.get("reload_token") or "").strip():
                raise ValueError("config_reload requires non-empty reload_token")
        elif kind == "config_drift":
            if set(parameters) != {"value"} or not str(parameters.get("value") or "").strip():
                raise ValueError("config_drift requires non-empty value")
        elif kind == "env_misconfiguration":
            if set(parameters) != {"name", "value"}:
                raise ValueError("env_misconfiguration requires name and value")
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(parameters.get("name") or "")):
                raise ValueError("env_misconfiguration name must be a valid environment variable")
            if not str(parameters.get("value") or "").strip():
                raise ValueError("env_misconfiguration value must be non-empty")
        elif kind == "secret_rotation":
            if set(parameters) != {"secret_name", "key", "value"}:
                raise ValueError("secret_rotation requires secret_name, key and value")
            if not all(str(parameters.get(key) or "").strip() for key in ("secret_name", "key", "value")):
                raise ValueError("secret_rotation parameters must be non-empty")
            target_kind = "Secret"
            target_name = str(parameters["secret_name"]).strip()
        elif kind == "rollout_pause":
            if set(parameters) != {"paused"} or not isinstance(parameters.get("paused"), bool):
                raise ValueError("rollout_pause requires boolean paused")
        elif kind == "image_pull_failure":
            if set(parameters) != {"image"} or not str(parameters.get("image") or "").strip():
                raise ValueError("image_pull_failure requires image")
            if len(str(parameters["image"])) > 255:
                raise ValueError("image_pull_failure image is too long")
        else:
            if set(parameters) != {"node_selector_key", "node_selector_value"}:
                raise ValueError("pod_unschedulable requires node_selector_key and node_selector_value")
            if not all(str(parameters.get(key) or "").strip() for key in ("node_selector_key", "node_selector_value")):
                raise ValueError("pod_unschedulable selector values must be non-empty")
        api_kind = "ChaosAtlasKubernetesFault"
        spec = {
            "faultFamily": kind,
            "targetRef": {"apiVersion": "v1" if target_kind == "Secret" else "apps/v1", "kind": target_kind, "name": target_name},
            "targetSelector": {str(key): str(value) for key, value in sorted(selector.items())},
            "parameters": {str(key): value for key, value in sorted(parameters.items())},
        }
    elif kind == "api_server_delay":
        if set(parameters) != {"latency_ms"}:
            raise ValueError("api_server_delay requires latency_ms")
        latency = parameters.get("latency_ms")
        if isinstance(latency, bool) or not isinstance(latency, int) or not 1 <= latency <= 300_000:
            raise ValueError("api_server_delay latency_ms must be in [1, 300000]")
        api_kind = "ChaosAtlasControlPlaneFault"
        spec = {
            "faultFamily": kind,
            "targetRef": {"apiVersion": "v1", "kind": "APIServer", "name": "kube-apiserver"},
            "targetSelector": {str(key): str(value) for key, value in sorted(selector.items())},
            "parameters": {"latency_ms": latency},
        }
    elif kind in {"disk_pressure", "file_descriptor_exhaustion", "process_exhaustion"}:
        deployment_name = str(((node.get("deployment") or {}).get("name") or "")).strip()
        if not deployment_name:
            raise ValueError("native resource fault requires deployment name")
        if kind == "disk_pressure":
            if set(parameters) != {"path", "size_mb"}:
                raise ValueError("disk_pressure requires path and size_mb")
            path = str(parameters.get("path") or "")
            size_mb = parameters.get("size_mb")
            if not path.startswith("/") or ".." in path.split("/") or isinstance(size_mb, bool) or not isinstance(size_mb, int) or not 1 <= size_mb <= 1024:
                raise ValueError("disk_pressure path must be safe and size_mb must be in [1, 1024]")
        else:
            if set(parameters) != {"count"}:
                raise ValueError(f"{kind} requires count")
            count = parameters.get("count")
            if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 10000:
                raise ValueError(f"{kind} count must be in [1, 10000]")
        api_kind = "ChaosAtlasNativeFault"
        spec = {
            "faultFamily": kind,
            "targetRef": {"apiVersion": "apps/v1", "kind": "Deployment", "name": deployment_name},
            "targetSelector": {str(key): str(value) for key, value in sorted(selector.items())},
            "parameters": {str(key): value for key, value in sorted(parameters.items())},
        }
    else:
        if parameters != {}: raise ValueError("network_partition parameters must be empty")
        api_kind, spec = "NetworkChaos", {**base, "action": "partition", "mode": "one", "duration": _duration(phase["duration_s"]), "direction": "to"}
    digest = hashlib.sha256(json.dumps({"phase": phase["phase_id"], "fault": fault}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:12]
    labels = {
        "chaosatlas.dev/scenario": str(scenario["scenario_id"]),
        "chaosatlas.dev/phase": str(phase["phase_id"]),
        "chaosatlas.dev/cleanup-owner": str(phase["cleanup_owner"]),
    }
    if kind in {"http_response_corrupt", "dependency_error", "connection_reset"}:
        labels["chaosatlas.dev/semantic-fault"] = kind
    return {"apiVersion": "chaos-mesh.org/v1alpha1", "kind": api_kind, "metadata": {"name": f"atlas-{_name(scenario['scenario_id'])}-{_name(str(phase['phase_id']))}-{index}-{digest}", "namespace": namespace, "labels": labels}, "spec": spec}


def compile_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    errors = validate_scenario_node(scenario)
    if errors:
        return {"status": "method_invalid", "errors": errors, "manifests": [], "phases": []}
    phases: list[dict[str, Any]] = []
    manifests: list[dict[str, Any]] = []
    try:
        for phase in scenario["phases"]:
            compiled = [_manifest(scenario, phase, fault, index) for index, fault in enumerate(phase["faults"])]
            phases.append({"phase_id": phase["phase_id"], "mode": phase["mode"], "target_node_ids": list(phase["target_node_ids"]), "cleanup_owner": phase["cleanup_owner"], "manifests": compiled})
            manifests.extend(compiled)
    except (KeyError, TypeError, ValueError) as exc:
        return {"status": "method_invalid", "errors": [str(exc)], "manifests": [], "phases": []}
    result = {"schema_version": 1, "status": "verified", "scenario_id": scenario["scenario_id"], "scenario_hash": scenario_signature(scenario), "phases": phases, "manifests": manifests}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    scenario = json.loads(args.scenario.read_text(encoding="utf-8"))
    result = compile_scenario(scenario)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "scenario.json").write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    (args.output / "scenario.yaml").write_text(yaml.safe_dump_all(result["manifests"], sort_keys=False), encoding="utf-8")
    print(json.dumps({"status": result["status"], "manifests": len(result["manifests"]), "output": str(args.output)}, ensure_ascii=True))
    return 0 if result["status"] == "verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
