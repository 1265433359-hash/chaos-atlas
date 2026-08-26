"""Compile a validated scenario node into canonical Chaos Mesh manifests."""

from __future__ import annotations

import argparse
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


SUPPORTED = {
    "pod_kill",
    "container_kill",
    "stress_cpu",
    "stress_memory",
    "network_loss",
    "network_partition",
    "network_delay",
}


def _name(value: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")[:50] or "phase"


def _duration(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 3600:
        raise ValueError("duration_s must be an integer in [1, 3600]")
    return f"{value}s"


def _manifest(scenario: dict[str, Any], phase: dict[str, Any], fault: dict[str, Any], index: int) -> dict[str, Any]:
    kind = str(fault.get("kind"))
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
    if kind == "pod_kill":
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
    else:
        if parameters != {}: raise ValueError("network_partition parameters must be empty")
        api_kind, spec = "NetworkChaos", {**base, "action": "partition", "mode": "one", "duration": _duration(phase["duration_s"]), "direction": "to"}
    digest = hashlib.sha256(json.dumps({"phase": phase["phase_id"], "fault": fault}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:12]
    return {"apiVersion": "chaos-mesh.org/v1alpha1", "kind": api_kind, "metadata": {"name": f"atlas-{_name(scenario['scenario_id'])}-{_name(str(phase['phase_id']))}-{index}-{digest}", "namespace": namespace, "labels": {"chaosatlas.dev/scenario": str(scenario["scenario_id"]), "chaosatlas.dev/phase": str(phase["phase_id"]), "chaosatlas.dev/cleanup-owner": str(phase["cleanup_owner"])}}, "spec": spec}


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
