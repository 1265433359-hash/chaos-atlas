"""Compile accepted ChaosAtlas hypotheses into bounded Chaos Mesh YAML.

This module is deliberately deterministic and side-effect free.  It consumes
the JSON emitted by ``open_discovery_compiler.py`` plus the topology IR, emits
YAML and provenance files, and never calls kubectl.  The existing runtime gate
must approve the generated YAML before the shared runner may apply it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

try:
    from tools.open_discovery_compiler import _signature
except ModuleNotFoundError:  # direct ``python tools/script.py`` invocation
    from open_discovery_compiler import _signature


GENERATOR_VERSION = "open_discovery_mutation_compiler_v1"
SUPPORTED_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "ReplicaSet"}
FAULT_FAMILIES = {"pod_kill", "network_delay", "network_loss", "container_cpu_stress"}


class MutationCompileError(ValueError):
    """A fail-closed mutation compilation error."""


@dataclass(frozen=True)
class ResolvedWorkload:
    target: str
    namespace: str
    kind: str
    name: str
    selector: dict[str, str]
    selector_source: str


def _string_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items() if str(key).strip() and item is not None}


def _nodes(topology: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(node.get("id")): node
        for node in topology.get("nodes", [])
        if isinstance(node, dict) and str(node.get("id", "")).strip()
    }


def _runtime_entry(runtime_map: dict[str, Any], target: str) -> dict[str, Any] | None:
    values = runtime_map.get("targets", runtime_map)
    entry = values.get(target) if isinstance(values, dict) else None
    return entry if isinstance(entry, dict) else None


def _mapped_workload(target: str, namespace: str, entry: dict[str, Any]) -> ResolvedWorkload:
    mapped_namespace = str(entry.get("namespace") or namespace)
    if mapped_namespace != namespace:
        raise MutationCompileError("runtime mapping namespace differs from project namespace")
    selector = _string_map(entry.get("selector") or entry.get("pod_labels"))
    if not selector:
        raise MutationCompileError("runtime mapping has an empty pod selector")
    workload = entry.get("workload") if isinstance(entry.get("workload"), dict) else entry
    kind = str(workload.get("kind") or "Deployment")
    name = str(workload.get("name") or "")
    if kind not in SUPPORTED_KINDS or not name:
        raise MutationCompileError("runtime mapping must identify a supported workload")
    return ResolvedWorkload(target, namespace, kind, name, selector, "runtime_mapping")


def _direct_workload(target: str, namespace: str, node: dict[str, Any]) -> ResolvedWorkload:
    kind = str(node.get("kind") or "")
    name = str(node.get("name") or "")
    if kind not in SUPPORTED_KINDS or not name:
        raise MutationCompileError("target is not a Kubernetes workload")
    selector = _string_map(node.get("pod_labels"))
    source = "topology.pod_labels"
    if not selector:
        # Older topology profiles only retained workload metadata labels.  Use
        # them only as an explicit compatibility fallback and record it so the
        # runtime gate can still verify the selector against live Pods.
        selector = _string_map(node.get("labels"))
        source = "topology.workload_labels_compatibility"
    if not selector:
        raise MutationCompileError("workload has no non-empty Pod selector")
    return ResolvedWorkload(target, namespace, kind, name, selector, source)


def _resolve_node(
    target: str,
    namespace: str,
    nodes: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
    runtime_map: dict[str, Any],
    seen: set[str] | None = None,
) -> ResolvedWorkload:
    seen = set(seen or ())
    if target in seen:
        raise MutationCompileError("target resolution cycle")
    seen.add(target)
    entry = _runtime_entry(runtime_map, target)
    if entry:
        return _mapped_workload(target, namespace, entry)
    node = nodes.get(target)
    if not node:
        raise MutationCompileError("target is absent from topology")
    if str(node.get("role")) == "configuration":
        raise MutationCompileError("configuration targets cannot receive runtime faults")
    if str(node.get("role")) == "workload":
        return _direct_workload(target, namespace, node)

    routed = [
        str(edge.get("target"))
        for edge in edges
        if str(edge.get("source")) == target
        and str(edge.get("kind")) in {"selector_routes", "http_routes"}
        and str(edge.get("target")) in nodes
        and str(nodes[str(edge.get("target"))].get("role")) == "workload"
    ]
    routed = sorted(set(routed))
    if len(routed) != 1:
        raise MutationCompileError("routing target must resolve to exactly one workload")
    return _resolve_node(routed[0], namespace, nodes, edges, runtime_map, seen)


def _resolve_edge(
    target: str,
    namespace: str,
    nodes: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
    runtime_map: dict[str, Any],
) -> tuple[ResolvedWorkload, ResolvedWorkload]:
    if "->" not in target:
        raise MutationCompileError("dependency_edge target must use source->target form")
    source, destination = target.split("->", 1)
    if source not in nodes or destination not in nodes:
        raise MutationCompileError("dependency edge endpoints are absent from topology")
    matching = [
        edge for edge in edges
        if str(edge.get("source")) == source and str(edge.get("target")) == destination
    ]
    if not matching:
        raise MutationCompileError("dependency edge is not backed by topology")
    return (
        _resolve_node(source, namespace, nodes, edges, runtime_map),
        _resolve_node(destination, namespace, nodes, edges, runtime_map),
    )


def _selector(namespace: str, workload: ResolvedWorkload) -> dict[str, Any]:
    return {"namespaces": [namespace], "labelSelectors": dict(sorted(workload.selector.items()))}


def _metadata(item: dict[str, Any], name: str) -> dict[str, Any]:
    project = re.sub(r"[^a-z0-9-]+", "-", str(item.get("project_id", "project")).lower()).strip("-") or "project"
    return {
        "name": name,
        "namespace": str(item["namespace"]),
        "labels": {
            "chaosatlas.dev/project": project[:63],
            "chaosatlas.dev/generator": GENERATOR_VERSION,
        },
    }


def _duration(seconds: Any) -> str:
    if isinstance(seconds, bool) or not isinstance(seconds, int) or not 1 <= seconds <= 60:
        raise MutationCompileError("duration_s must be an integer in [1, 60]")
    return f"{seconds}s"


def compile_mutation(
    item: dict[str, Any],
    topology: dict[str, Any],
    runtime_map: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    """Return provenance and YAML text for one accepted canonical intent."""
    runtime_map = runtime_map or {}
    required = ("project_id", "namespace", "target", "target_kind", "fault_family", "parameters", "canonical_signature")
    missing = [field for field in required if field not in item]
    if missing:
        raise MutationCompileError(f"missing canonical fields: {missing}")
    family = str(item["fault_family"])
    if family not in FAULT_FAMILIES:
        raise MutationCompileError("unsupported fault family")
    expected_signature = _signature(item)
    if str(item["canonical_signature"]) != expected_signature:
        raise MutationCompileError("canonical signature does not match mutation fields")
    namespace = str(item["namespace"])
    if not namespace or "/" in namespace or namespace in {"default", "kube-system"}:
        raise MutationCompileError("mutation namespace must be an isolated project namespace")
    nodes = _nodes(topology)
    edges = [edge for edge in topology.get("edges", []) if isinstance(edge, dict)]
    target = str(item["target"])
    target_kind = str(item["target_kind"])
    edge_endpoints: tuple[ResolvedWorkload, ResolvedWorkload] | None = None
    if target_kind == "dependency_edge":
        if family not in {"network_delay", "network_loss"}:
            raise MutationCompileError("dependency edges support only network faults")
        edge_endpoints = _resolve_edge(target, namespace, nodes, edges, runtime_map)
        source_workload, destination_workload = edge_endpoints
        selected = source_workload
    else:
        selected = _resolve_node(target, namespace, nodes, edges, runtime_map)
        destination_workload = None
    params = item["parameters"]
    if not isinstance(params, dict):
        raise MutationCompileError("parameters must be an object")
    expected_parameters = {
        "pod_kill": {"mode"},
        "network_delay": {"latency_ms", "duration_s"},
        "network_loss": {"loss_percent", "duration_s"},
        "container_cpu_stress": {"workers", "load_percent", "duration_s"},
    }[family]
    if set(params) != expected_parameters:
        raise MutationCompileError(f"parameters must contain exactly {sorted(expected_parameters)}")

    signature = expected_signature
    name = f"atlas-{re.sub(r'[^a-z0-9-]+', '-', str(item['project_id']).lower()).strip('-')}-{signature[:12]}"[:63].rstrip("-")
    metadata = _metadata(item, name)
    spec: dict[str, Any] = {"mode": "one", "selector": _selector(namespace, selected)}
    if family == "pod_kill":
        if params != {"mode": "one"}:
            raise MutationCompileError("pod_kill parameters must be exactly {'mode': 'one'}")
        if target_kind == "dependency_edge":
            raise MutationCompileError("pod_kill cannot target a dependency edge")
        document = {"apiVersion": "chaos-mesh.org/v1alpha1", "kind": "PodChaos", "metadata": metadata, "spec": {**spec, "action": "pod-kill", "duration": "30s"}}
    elif family in {"network_delay", "network_loss"}:
        duration = _duration(params.get("duration_s"))
        if family == "network_delay":
            latency = params.get("latency_ms")
            if isinstance(latency, bool) or not isinstance(latency, int) or not 1 <= latency <= 500:
                raise MutationCompileError("latency_ms must be an integer in [1, 500]")
            network = {"action": "delay", "delay": {"latency": f"{latency}ms", "correlation": "100", "jitter": "0ms"}, "duration": duration, "direction": "to"}
        else:
            loss = params.get("loss_percent")
            if isinstance(loss, bool) or not isinstance(loss, int) or not 1 <= loss <= 100:
                raise MutationCompileError("loss_percent must be an integer in [1, 100]")
            network = {"action": "loss", "loss": {"loss": str(loss), "correlation": "100"}, "duration": duration, "direction": "to"}
        if destination_workload is not None:
            network["target"] = {
                "mode": "all",
                "selector": _selector(namespace, destination_workload),
            }
        document = {"apiVersion": "chaos-mesh.org/v1alpha1", "kind": "NetworkChaos", "metadata": metadata, "spec": {**spec, **network}}
    else:
        if target_kind == "dependency_edge":
            raise MutationCompileError("container_cpu_stress cannot target a dependency edge")
        workers, load = params.get("workers"), params.get("load_percent")
        if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= 2:
            raise MutationCompileError("workers must be an integer in [1, 2]")
        if isinstance(load, bool) or not isinstance(load, int) or not 1 <= load <= 80:
            raise MutationCompileError("load_percent must be an integer in [1, 80]")
        document = {"apiVersion": "chaos-mesh.org/v1alpha1", "kind": "StressChaos", "metadata": metadata, "spec": {**spec, "stressors": {"cpu": {"workers": workers, "load": load}}, "duration": _duration(params.get("duration_s"))}}

    provenance = {
        "schema_version": "1.0",
        "generator": GENERATOR_VERSION,
        "project_id": item["project_id"],
        "project_commit": item.get("project_commit"),
        "topology_graph_hash": topology.get("graph_hash"),
        "canonical_signature": signature,
        "hypothesis_id": item.get("hypothesis_id"),
        "target": target,
        "target_kind": target_kind,
        "fault_family": family,
        "parameters": params,
        "namespace": namespace,
        "resolved_source": {"target": selected.target, "kind": selected.kind, "name": selected.name, "selector": selected.selector, "selector_source": selected.selector_source},
        "resolved_destination": ({"target": destination_workload.target, "kind": destination_workload.kind, "name": destination_workload.name, "selector": destination_workload.selector, "selector_source": destination_workload.selector_source} if destination_workload else None),
        "runtime_gate_required": True,
        "execution_ready": False,
    }
    return provenance, yaml.safe_dump(document, sort_keys=False)


def compile_payload(payload: dict[str, Any], topology: dict[str, Any], runtime_map: dict[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(payload, dict) and payload.get("status") not in (None, "valid"):
        return {
            "status": "method_invalid",
            "compiler": GENERATOR_VERSION,
            "generated_count": 0,
            "rejected_count": 1,
            "generated": [],
            "rejected": [{"reason": "upstream_compiler_not_valid", "upstream_status": payload.get("status")}],
        }
    accepted = payload.get("accepted") if isinstance(payload, dict) else None
    if not isinstance(accepted, list):
        accepted = [payload]
    results: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for index, item in enumerate(accepted):
        if not isinstance(item, dict):
            rejected.append({"index": index, "reason": "mutation intent must be an object"})
            continue
        try:
            provenance, yaml_text = compile_mutation(item, topology, runtime_map)
        except (MutationCompileError, KeyError, TypeError, ValueError) as exc:
            rejected.append({"index": index, "hypothesis_id": item.get("hypothesis_id"), "reason": str(exc)})
            continue
        results.append({"index": index, "hypothesis_id": item.get("hypothesis_id"), "canonical_signature": provenance["canonical_signature"], "kind": yaml.safe_load(yaml_text)["kind"], "yaml": yaml_text, "provenance": provenance})
    status = "valid" if results or (not accepted and not rejected) else "method_invalid"
    return {"status": status, "compiler": GENERATOR_VERSION, "generated_count": len(results), "rejected_count": len(rejected), "generated": results, "rejected": rejected}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True, help="open_discovery_compiler JSON or one canonical accepted item")
    parser.add_argument("--topology", type=Path, required=True)
    parser.add_argument("--runtime-map", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    topology = json.loads(args.topology.read_text(encoding="utf-8"))
    runtime_map = json.loads(args.runtime_map.read_text(encoding="utf-8")) if args.runtime_map else {}
    result = compile_payload(payload, topology, runtime_map)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for entry in result["generated"]:
        name = yaml.safe_load(entry["yaml"])["metadata"]["name"]
        yaml_path = args.output_dir / f"{name}.yaml"
        provenance_path = args.output_dir / f"{name}.provenance.json"
        yaml_path.write_text(entry["yaml"], encoding="utf-8")
        entry["provenance"]["yaml_path"] = str(yaml_path).replace("\\", "/")
        entry["provenance"]["yaml_sha256"] = hashlib.sha256(entry["yaml"].encode("utf-8")).hexdigest()
        provenance_path.write_text(json.dumps(entry["provenance"], indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        entry["yaml_path"] = str(yaml_path).replace("\\", "/")
        entry["provenance_path"] = str(provenance_path).replace("\\", "/")
    manifest = args.manifest or args.output_dir / "manifest.json"
    manifest.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "generated": result["generated_count"], "rejected": result["rejected_count"], "manifest": str(manifest)}, indent=2))
    return 0 if result["status"] == "valid" else 2


if __name__ == "__main__":
    raise SystemExit(main())
