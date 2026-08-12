"""Deterministic topology extraction for Kubernetes and Compose YAML.

This module deliberately extracts deployment facts only.  It does not infer
application call graphs or reliability verdicts.  The resulting graph is a
method-neutral input for the open-discovery experiment and keeps source values
out of the bundle unless they are names or structural attributes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import yaml


WORKLOAD_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "ReplicaSet"}
SERVICE_KINDS = {"Service", "Ingress", "HTTPRoute", "Gateway"}


def _name(doc: dict[str, Any]) -> str:
    metadata = doc.get("metadata") or {}
    return str(metadata.get("name") or "").strip()


def _namespace(doc: dict[str, Any]) -> str:
    metadata = doc.get("metadata") or {}
    return str(metadata.get("namespace") or "default").strip() or "default"


def _ref(kind: str, name: str, namespace: str = "default") -> str:
    return f"{namespace}/{kind.lower()}/{name}"


def _labels(doc: dict[str, Any]) -> dict[str, str]:
    labels = (doc.get("metadata") or {}).get("labels") or {}
    return {str(k): str(v) for k, v in labels.items()}


def _workload_template(doc: dict[str, Any]) -> dict[str, Any]:
    spec = doc.get("spec") or {}
    if doc.get("kind") == "CronJob":
        spec = (spec.get("jobTemplate") or {}).get("spec") or {}
    return spec.get("template") or {}


def _pod_template_labels(doc: dict[str, Any]) -> dict[str, str]:
    """Return labels applied to Pods, not labels on the workload object."""
    labels = (_workload_template(doc).get("metadata") or {}).get("labels") or {}
    return {str(k): str(v) for k, v in labels.items()}


def _container_names(template: dict[str, Any]) -> list[str]:
    spec = template.get("spec") or {}
    return [str(c.get("name")) for c in spec.get("containers", []) if c.get("name")]


def _probe_summary(container: dict[str, Any], field: str) -> dict[str, Any] | None:
    probe = container.get(field)
    if not isinstance(probe, dict):
        return None
    return {
        "timeout_seconds": probe.get("timeoutSeconds"),
        "period_seconds": probe.get("periodSeconds"),
        "failure_threshold": probe.get("failureThreshold"),
        "success_threshold": probe.get("successThreshold"),
        "initial_delay_seconds": probe.get("initialDelaySeconds"),
    }


def _selector_matches(labels: dict[str, Any], selector: dict[str, Any], *, empty_matches_all: bool) -> bool:
    match_labels = selector.get("matchLabels") or {}
    match_expressions = selector.get("matchExpressions") or []
    if not match_labels and not match_expressions:
        return empty_matches_all
    if not all(str(labels.get(key)) == str(value) for key, value in match_labels.items()):
        return False
    for expression in match_expressions:
        key = expression.get("key")
        operator = expression.get("operator")
        values = {str(value) for value in expression.get("values", [])}
        actual = labels.get(key)
        if operator == "Exists" and key not in labels:
            return False
        if operator == "DoesNotExist" and key in labels:
            return False
        if operator == "In" and str(actual) not in values:
            return False
        if operator == "NotIn" and key in labels and str(actual) in values:
            return False
        if operator not in {"Exists", "DoesNotExist", "In", "NotIn"}:
            return False
    return True


def _defenses_for_workload(doc: dict[str, Any], pdbs: list[dict[str, Any]], policies: list[dict[str, Any]]) -> dict[str, Any]:
    template = _workload_template(doc)
    pod_spec = template.get("spec") or {}
    workload_spec = doc.get("spec") or {}
    containers = pod_spec.get("containers") or []
    probes = {
        "readiness": sum(1 for c in containers if c.get("readinessProbe")),
        "liveness": sum(1 for c in containers if c.get("livenessProbe")),
        "startup": sum(1 for c in containers if c.get("startupProbe")),
        "details": {
            "readiness": [_probe_summary(c, "readinessProbe") for c in containers if _probe_summary(c, "readinessProbe")],
            "liveness": [_probe_summary(c, "livenessProbe") for c in containers if _probe_summary(c, "livenessProbe")],
            "startup": [_probe_summary(c, "startupProbe") for c in containers if _probe_summary(c, "startupProbe")],
        },
    }
    limits = sum(1 for c in containers if (c.get("resources") or {}).get("limits"))
    replicas = workload_spec.get("replicas")
    labels = (template.get("metadata") or {}).get("labels") or {}
    namespace = _namespace(doc)
    pdb_selectors = [((p.get("spec") or {}).get("selector") or {}) for p in pdbs if ((p.get("metadata") or {}).get("namespace") or "default") == namespace]
    has_pdb = any(
        _selector_matches(labels, selector, empty_matches_all=False)
        for selector in pdb_selectors
    )
    has_policy = any(
        ((p.get("metadata") or {}).get("namespace") or "default") == namespace
        and _selector_matches(labels, ((p.get("spec") or {}).get("podSelector") or {}), empty_matches_all=True)
        for p in policies
    )
    return {
        "replicas": replicas if isinstance(replicas, int) else None,
        "container_count": len(containers),
        "container_names": _container_names(template),
        "probes": probes,
        "resource_limits_count": limits,
        "pod_disruption_budget": bool(has_pdb),
        "network_policy": bool(has_policy),
        "service_account": pod_spec.get("serviceAccountName"),
        "restart_policy": pod_spec.get("restartPolicy"),
    }


def _parse_kubernetes(docs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    defenses: list[dict[str, Any]] = []
    workloads = [d for d in docs if d.get("kind") in WORKLOAD_KINDS and _name(d)]
    services = [d for d in docs if d.get("kind") in SERVICE_KINDS and _name(d)]
    pdbs = [d for d in docs if d.get("kind") in {"PodDisruptionBudget", "PDB"} and _name(d)]
    policies = [d for d in docs if d.get("kind") == "NetworkPolicy" and _name(d)]

    for doc in docs:
        kind, name = str(doc.get("kind") or ""), _name(doc)
        if not kind or not name:
            continue
        namespace = _namespace(doc)
        ref = _ref(kind, name, namespace)
        node: dict[str, Any] = {"id": ref, "kind": kind, "name": name, "namespace": namespace, "labels": _labels(doc)}
        if kind in WORKLOAD_KINDS:
            node["role"] = "workload"
            node["pod_labels"] = _pod_template_labels(doc)
            defenses.append({"target": ref, "attributes": _defenses_for_workload(doc, pdbs, policies)})
        elif kind == "Service":
            node["role"] = "routing"
        elif kind in {"Ingress", "HTTPRoute", "Gateway"}:
            node["role"] = "entrypoint"
        else:
            node["role"] = "configuration"
        nodes.append(node)

    workload_index = [(d, _ref(str(d.get("kind")), _name(d), _namespace(d)), _labels(_workload_template(d))) for d in workloads]
    for service in services:
        selector = ((service.get("spec") or {}).get("selector") or {}) if service.get("kind") == "Service" else {}
        source = _ref(str(service.get("kind")), _name(service), _namespace(service))
        for workload, target, labels in workload_index:
            if selector and all(str(labels.get(k)) == str(v) for k, v in selector.items()) and _namespace(workload) == _namespace(service):
                edges.append({"source": source, "target": target, "kind": "selector_routes", "evidence": "service.spec.selector"})
        if selector:
            defenses.append({"target": source, "attributes": {"selector": selector, "session_affinity": (service.get("spec") or {}).get("sessionAffinity")}})

    for ingress in [d for d in docs if d.get("kind") == "Ingress" and _name(d)]:
        source = _ref("Ingress", _name(ingress), _namespace(ingress))
        rules = (ingress.get("spec") or {}).get("rules") or []
        for rule in rules:
            for path in ((rule.get("http") or {}).get("paths") or []):
                backend = path.get("backend") or {}
                service_name = (backend.get("service") or {}).get("name") or backend.get("serviceName")
                if service_name:
                    target = _ref("Service", str(service_name), _namespace(ingress))
                    edges.append({"source": source, "target": target, "kind": "http_routes", "evidence": "ingress.spec.rules"})

    for doc in docs:
        if doc.get("kind") not in WORKLOAD_KINDS:
            continue
        source = _ref(str(doc.get("kind")), _name(doc), _namespace(doc))
        template = _workload_template(doc)
        pod_spec = template.get("spec") or {}
        for container in pod_spec.get("containers", []) or []:
            for env_from in container.get("envFrom", []) or []:
                for key in ("configMapRef", "secretRef"):
                    if env_from.get(key, {}).get("name"):
                        target = _ref("ConfigMap" if key == "configMapRef" else "Secret", env_from[key]["name"], _namespace(doc))
                        edges.append({"source": source, "target": target, "kind": "configuration_ref", "evidence": f"container.envFrom.{key}"})
            for env in container.get("env", []) or []:
                for key in ("configMapKeyRef", "secretKeyRef"):
                    value = env.get("valueFrom", {}).get(key, {})
                    if value.get("name"):
                        target = _ref("ConfigMap" if key == "configMapKeyRef" else "Secret", value["name"], _namespace(doc))
                        edges.append({"source": source, "target": target, "kind": "configuration_ref", "evidence": f"container.env.valueFrom.{key}"})
    return nodes, edges, defenses


def _parse_compose(doc: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    defenses: list[dict[str, Any]] = []
    services = doc.get("services") or {}
    if not isinstance(services, dict):
        return nodes, edges, defenses
    for name, value in services.items():
        if not isinstance(value, dict):
            continue
        service = str(name)
        nodes.append({"id": f"compose/service/{service}", "kind": "ComposeService", "name": service, "namespace": "compose", "role": "workload", "labels": {}})
        health = value.get("healthcheck")
        deploy = value.get("deploy") if isinstance(value.get("deploy"), dict) else {}
        resources = deploy.get("resources") if isinstance(deploy.get("resources"), dict) else {}
        defenses.append({"target": f"compose/service/{service}", "attributes": {"healthcheck": bool(health), "replicas": (value.get("deploy") or {}).get("replicas") if isinstance(value.get("deploy"), dict) else None, "resource_limits": bool(resources.get("limits")), "restart": value.get("restart")}})
        depends = value.get("depends_on") or {}
        if isinstance(depends, list):
            depends = {item: {} for item in depends}
        if isinstance(depends, dict):
            for target in depends:
                edges.append({"source": f"compose/service/{service}", "target": f"compose/service/{target}", "kind": "depends_on", "evidence": "services.depends_on"})
    return nodes, edges, defenses


def parse_documents(documents: Iterable[dict[str, Any]], source_files: list[str] | None = None) -> dict[str, Any]:
    docs = [d for d in documents if isinstance(d, dict)]
    kube_docs = [d for d in docs if d.get("apiVersion") and d.get("kind")]
    compose_docs = [d for d in docs if isinstance(d.get("services"), dict)]
    nodes, edges, defenses = _parse_kubernetes(kube_docs)
    for doc in compose_docs:
        n, e, f = _parse_compose(doc)
        nodes.extend(n)
        edges.extend(e)
        defenses.extend(f)
    nodes.sort(key=lambda item: item["id"])
    edges.sort(key=lambda item: (item["source"], item["target"], item["kind"]))
    defenses.sort(key=lambda item: item["target"])
    canonical = {"nodes": nodes, "edges": edges, "defenses": defenses}
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return {
        "schema_version": "1.0",
        "kind": "chaosatlas_topology",
        "source_files": sorted(source_files or []),
        "document_count": len(docs),
        "supported_document_count": len(kube_docs) + len(compose_docs),
        "nodes": nodes,
        "edges": edges,
        "defenses": defenses,
        "graph_hash": hashlib.sha256(encoded).hexdigest(),
    }


def parse_paths(paths: Iterable[Path]) -> dict[str, Any]:
    documents: list[dict[str, Any]] = []
    sources: list[str] = []
    for root in paths:
        candidates = [root] if root.is_file() else sorted(root.rglob("*.y*ml"))
        for path in candidates:
            try:
                text = path.read_text(encoding="utf-8-sig")
                loaded = list(yaml.safe_load_all(text))
            except (OSError, UnicodeDecodeError, yaml.YAMLError):
                continue
            documents.extend(item for item in loaded if isinstance(item, dict))
            sources.append(str(path))
    return parse_documents(documents, sources)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", nargs="+", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = parse_paths(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"nodes": len(result["nodes"]), "edges": len(result["edges"]), "graph_hash": result["graph_hash"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
