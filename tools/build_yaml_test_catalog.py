from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "raw_yaml"
PROJECT_ROOT = ROOT / "train-ticket"
OUT_ROOT = ROOT / "artifacts" / "train-ticket"
PLACEHOLDER_RE = re.compile(r"\$\{[^}]+\}|\$\{\{[^}]+\}\}|<[^>]+>|placeholder|PLACEHOLDER")
JAVA_METHOD_RE = re.compile(r"\b(?:public|protected|private|static|final|synchronized|native|abstract|default)?\s*(?:[A-Za-z_$][\w$<>\[\],.? ]*)\s+([A-Za-z_$][\w$]*)\s*\([^;{}]*\)\s*(?:throws [^{]+)?\{")
PYTHON_FUNCTION_RE = re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(")
JS_FUNCTION_RE = re.compile(r"\b(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(|\b([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>")
GO_FUNCTION_RE = re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\(")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return str(value)


def read_yaml(path: Path) -> tuple[dict[str, Any] | None, str, str]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    try:
        value = yaml.safe_load(raw)
    except Exception as exc:  # Keep malformed samples in the inventory.
        error = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
        return None, "parse_error", error
    if not isinstance(value, dict):
        return None, "non_map", "top-level document is not a mapping"
    return value, "valid_map", ""


def risk_flags(raw: str, document: dict[str, Any] | None) -> list[str]:
    flags: set[str] = set()
    lower = raw.lower()
    if PLACEHOLDER_RE.search(raw):
        flags.add("placeholder")
    for token, flag in {
        "secretname": "secret_reference",
        "endpoint": "external_endpoint",
        "ec2instance": "cloud_instance",
        "awsregion": "cloud_region",
        "instance": "cloud_instance",
        "volumePath": "host_volume",
        "deviceNames": "host_device",
        "address": "machine_address",
        "remoteCluster": "remote_cluster",
    }.items():
        if token.lower() in lower:
            flags.add(flag)
    spec = (document or {}).get("spec") or {}
    selector = spec.get("selector") or {}
    if selector.get("namespaces") and "train-ticket" in selector.get("namespaces", []):
        flags.add("train_ticket_target")
    if spec.get("mode") == "all":
        flags.add("namespace_or_selector_blast_radius")
    if "scheduler" in spec or (document or {}).get("kind") in {"Workflow", "Schedule"}:
        flags.add("temporal_or_composite")
    return sorted(flags)


def shape_issues(document: dict[str, Any] | None) -> list[str]:
    if document is None:
        return []
    issues: list[str] = []
    if not isinstance(document.get("kind"), str):
        issues.append("kind_not_string")
    if not isinstance(document.get("apiVersion"), str):
        issues.append("api_version_not_string")
    metadata = document.get("metadata")
    if not isinstance(metadata, dict):
        issues.append("metadata_not_mapping")
        metadata = {}
    for field in ("name", "generateName", "namespace"):
        if field in metadata and metadata[field] is not None and not isinstance(metadata[field], str):
            issues.append(f"metadata_{field}_not_string")
    spec = document.get("spec")
    if spec is not None and not isinstance(spec, dict):
        issues.append("spec_not_mapping")
        return sorted(set(issues))
    spec = spec or {}
    selector = spec.get("selector")
    if selector is not None and not isinstance(selector, dict):
        issues.append("selector_not_mapping")
    elif isinstance(selector, dict):
        namespaces = selector.get("namespaces")
        if namespaces is not None and (not isinstance(namespaces, list) or any(not isinstance(item, str) for item in namespaces)):
            issues.append("selector_namespaces_not_string_list")
        labels = selector.get("labelSelectors")
        if labels is not None and (not isinstance(labels, dict) or any(not isinstance(value, str) for value in labels.values())):
            issues.append("selector_label_value_not_string")
    for field in ("mode", "action", "target", "duration", "direction"):
        if field in spec and spec[field] is not None and not isinstance(spec[field], str):
            if field == "target" and document.get("kind") == "NetworkChaos":
                continue
            issues.append(f"spec_{field}_not_string")
    return sorted(set(issues))


def primitive_nodes(document: dict[str, Any]) -> list[str]:
    kind = str(document.get("kind") or "Unknown")
    spec = document.get("spec") or {}
    nodes: list[str] = []
    if spec.get("selector"):
        nodes.append("selector")
    if kind == "HTTPChaos":
        if spec.get("abort") is True:
            nodes.append("http_abort")
        if spec.get("delay") is not None:
            nodes.append("http_delay")
        if spec.get("replace") is not None:
            nodes.append("http_replace_response")
        if len(nodes) == 1 and nodes[0] == "selector":
            nodes.append("http_fault_unspecified")
    elif kind == "NetworkChaos":
        action = spec.get("action") or "unspecified"
        nodes.append(f"network_{action}")
    elif kind == "StressChaos":
        stressors = spec.get("stressors") or {}
        for stressor in stressors:
            nodes.append(f"stress_{stressor}")
        if not stressors:
            nodes.append("stress_unspecified")
    elif kind == "PodChaos":
        nodes.append(f"pod_{spec.get('action') or 'unspecified'}")
    elif kind == "TimeChaos":
        nodes.append("time_offset")
    elif kind == "IOChaos":
        nodes.append(f"io_{spec.get('action') or 'unspecified'}")
    elif kind == "DNSChaos":
        nodes.append(f"dns_{spec.get('action') or 'unspecified'}")
    elif kind == "Workflow":
        templates = spec.get("templates") or []
        for template in templates:
            if isinstance(template, dict):
                template_type = template.get("templateType") or template.get("type") or "unknown"
                nodes.append(f"workflow_{str(template_type).lower()}")
    elif kind == "Schedule":
        nodes.append(f"schedule_{spec.get('type') or 'unknown'}")
    else:
        nodes.append(kind.lower())
    return sorted(set(nodes))


def selector_labels(document: dict[str, Any]) -> dict[str, str]:
    selector = ((document.get("spec") or {}).get("selector") or {})
    labels = selector.get("labelSelectors") or {}
    return {str(key): scalar(value) for key, value in labels.items()}


def load_project_targets() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    deployments: list[dict[str, Any]] = []
    services: list[dict[str, Any]] = []
    manifest_root = PROJECT_ROOT / "deployment"
    for path in manifest_root.rglob("*"):
        if path.suffix.lower() not in {".yaml", ".yml"}:
            continue
        try:
            documents = yaml.safe_load_all(path.read_text(encoding="utf-8", errors="replace"))
            for document in documents:
                if not isinstance(document, dict):
                    continue
                metadata = document.get("metadata") or {}
                kind = document.get("kind")
                if kind == "Deployment":
                    template = ((document.get("spec") or {}).get("template") or {})
                    labels = ((template.get("metadata") or {}).get("labels") or {})
                    deployments.append({
                        "name": scalar(metadata.get("name")),
                        "app": scalar(labels.get("app")),
                        "path": str(path.relative_to(ROOT)),
                    })
                elif kind == "Service":
                    services.append({
                        "name": scalar(metadata.get("name")),
                        "selector": {str(k): scalar(v) for k, v in ((document.get("spec") or {}).get("selector") or {}).items()},
                        "path": str(path.relative_to(ROOT)),
                    })
        except Exception:
            # Helm templates are rendered later; they are not static targets here.
            continue
    return deployments, services


def service_module_candidates(app: str) -> list[str]:
    if not app:
        return []
    candidates = []
    direct = PROJECT_ROOT / app
    if direct.is_dir():
        candidates.append(str(direct.relative_to(ROOT)))
    for path in PROJECT_ROOT.glob(f"{app}*"):
        if path.is_dir() and path.name != "node_modules":
            candidates.append(str(path.relative_to(ROOT)))
    return sorted(set(candidates))


def source_function_candidates(app: str) -> list[dict[str, Any]]:
    """Return bounded static candidates; these are not runtime reachability claims."""
    if not app:
        return []
    modules = [path for path in PROJECT_ROOT.glob(f"{app}*") if path.is_dir() and path.name != "node_modules"]
    candidates: list[dict[str, Any]] = []
    for module in modules:
        source_paths = [path for path in module.rglob("*") if path.is_file()]
        source_paths.sort(key=lambda path: (any(part.lower() in {"test", "tests"} for part in path.parts), str(path)))
        for path in source_paths:
            if not path.is_file() or path.suffix.lower() not in {".java", ".py", ".js", ".ts", ".go"}:
                continue
            if any(part in {"node_modules", "target", "build", ".git"} for part in path.parts):
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line_number, line in enumerate(lines, start=1):
                names: list[str] = []
                if path.suffix.lower() == ".java":
                    match = JAVA_METHOD_RE.search(line)
                    if match:
                        names.append(match.group(1))
                elif path.suffix.lower() == ".py":
                    match = PYTHON_FUNCTION_RE.search(line)
                    if match:
                        names.append(match.group(1))
                elif path.suffix.lower() in {".js", ".ts"}:
                    match = JS_FUNCTION_RE.search(line)
                    if match:
                        names.append(match.group(1) or match.group(2))
                elif path.suffix.lower() == ".go":
                    match = GO_FUNCTION_RE.search(line)
                    if match:
                        names.append(match.group(1))
                for name in names:
                    candidates.append({
                        "name": name,
                        "path": str(path.relative_to(ROOT)),
                        "line": line_number,
                        "role": "test" if any(part.lower() in {"test", "tests"} for part in path.parts) else "production",
                        "evidence": "static_source_candidate",
                    })
                    if len(candidates) >= 120:
                        return candidates
    return candidates


def build() -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    inventory: list[dict[str, Any]] = []
    node_counts: Counter[str] = Counter()
    node_docs: Counter[str] = Counter()
    node_kinds: defaultdict[str, Counter[str]] = defaultdict(Counter)
    node_examples: defaultdict[str, list[str]] = defaultdict(list)
    cooccurrence: Counter[tuple[str, str]] = Counter()
    train_ticket_docs: list[dict[str, Any]] = []

    for path in sorted(RAW_ROOT.rglob("*.yaml")):
        raw = path.read_text(encoding="utf-8", errors="replace")
        document, parse_status, parse_error = read_yaml(path)
        metadata = (document or {}).get("metadata") or {}
        spec = (document or {}).get("spec") or {}
        nodes = primitive_nodes(document) if document else []
        relative = str(path.relative_to(ROOT))
        inventory.append({
            "path": relative,
            "sha256": sha256(path),
            "kind": scalar((document or {}).get("kind")),
            "api_version": scalar((document or {}).get("apiVersion")),
            "namespace": scalar(metadata.get("namespace")),
            "name": scalar(metadata.get("name")),
            "parse_status": parse_status,
            "parse_error": parse_error,
            "spec_keys": sorted(str(key) for key in spec) if isinstance(spec, dict) else [],
            "test_nodes": nodes,
            "risk_flags": risk_flags(raw, document),
            "shape_issues": shape_issues(document),
            "placeholder_count": len(PLACEHOLDER_RE.findall(raw)),
        })
        for node in nodes:
            node_counts[node] += 1
            node_docs[node] += 1
            if document:
                node_kinds[node][str(document.get("kind") or "Unknown")] += 1
            if len(node_examples[node]) < 5:
                node_examples[node].append(relative)
        for left_index, left in enumerate(nodes):
            for right in nodes[left_index + 1:]:
                cooccurrence[tuple(sorted((left, right)))] += 1
        if document and metadata.get("namespace") == "train-ticket":
            train_ticket_docs.append({
                "path": relative,
                "kind": scalar(document.get("kind")),
                "name": scalar(metadata.get("name")),
                "nodes": nodes,
                "labels": selector_labels(document),
                "namespaces": ((spec.get("selector") or {}).get("namespaces") or []),
                "mode": scalar(spec.get("mode")),
                "duration": scalar(spec.get("duration")),
                "spec_keys": sorted(str(key) for key in spec) if isinstance(spec, dict) else [],
                "blast_radius_flag": spec.get("mode") == "all" or len((spec.get("selector") or {}).get("namespaces") or []) > 0,
            })

    deployments, services = load_project_targets()
    service_by_app = defaultdict(list)
    for service in services:
        app = service.get("selector", {}).get("app")
        if app:
            service_by_app[app].append(service)

    source_cache: dict[str, list[dict[str, Any]]] = {}

    slices: list[dict[str, Any]] = []
    for test in train_ticket_docs:
        labels = test["labels"]
        app = labels.get("app", "")
        matching_deployments = [item for item in deployments if app and item.get("app") == app]
        matching_services = service_by_app.get(app, [])
        source_cache.setdefault(app, source_function_candidates(app))
        function_candidates = source_cache[app]
        edges = []
        for node in test["nodes"]:
            edges.append({"from": node, "to": "selector", "type": "defines", "evidence": test["path"]})
            if app:
                edges.append({"from": "selector", "to": app, "type": "selects", "evidence": "labelSelectors.app"})
            for deployment in matching_deployments:
                edges.append({"from": app, "to": deployment["name"], "type": "targets", "evidence": deployment["path"]})
            for service in matching_services:
                edges.append({"from": app, "to": service["name"], "type": "routes_to", "evidence": service["path"]})
        slices.append({
            "test_id": test["name"],
            "source": test["path"],
            "kind": test["kind"],
            "test_nodes": test["nodes"],
            "selector": {"labels": labels, "namespaces": test["namespaces"], "mode": test["mode"]},
            "blast_radius_flag": test["blast_radius_flag"],
            "target_matches": matching_deployments,
            "service_matches": matching_services,
            "code_module_candidates": service_module_candidates(app),
            "function_candidates": function_candidates,
            "edges": edges,
            "evidence_status": {
                "selector_to_deployment": "static_manifest_match" if matching_deployments else "unverified",
                "deployment_to_function": "static_source_candidate" if function_candidates else "unverified",
                "function_to_runtime_trace": "pending_runtime_baseline",
                "observer_path": "candidate_prometheus_and_tracing_manifests",
            },
        })

    inventory_path = OUT_ROOT / "yaml_inventory.csv"
    fieldnames = [
        "path", "sha256", "kind", "api_version", "namespace", "name", "parse_status", "parse_error",
        "spec_keys", "test_nodes", "risk_flags", "shape_issues", "placeholder_count",
    ]
    with inventory_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in inventory:
            row = dict(row)
            for field in ("spec_keys", "test_nodes", "risk_flags", "shape_issues"):
                row[field] = json.dumps(row[field], ensure_ascii=False, sort_keys=True)
            writer.writerow(row)

    catalog = {
        "schema_version": "0.1",
        "source": {"root": "raw_yaml", "file_count": len(inventory)},
        "nodes": [
            {
                "node": node,
                "document_count": node_counts[node],
                "kind_counts": dict(node_kinds[node]),
                "examples": node_examples[node],
                "status": "candidate_pattern",
            }
            for node in sorted(node_counts, key=lambda key: (-node_counts[key], key))
        ],
        "cooccurrence": [
            {"left": left, "right": right, "document_count": count}
            for (left, right), count in sorted(cooccurrence.items(), key=lambda item: (-item[1], item[0]))
        ],
        "train_ticket": {
            "document_count": len(train_ticket_docs),
            "kind_counts": dict(Counter(item["kind"] for item in train_ticket_docs)),
            "node_counts": dict(Counter(node for item in train_ticket_docs for node in item["nodes"])),
            "samples": train_ticket_docs,
        },
    }
    (OUT_ROOT / "test_node_catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_ROOT / "train_ticket_test_slices.json").write_text(json.dumps({
        "schema_version": "0.1",
        "project": "FudanSELab/train-ticket",
        "commit": "313886e99befb94be6cd45f085c98e0019f59829",
        "scope": "static selector-to-deployment slice; source and runtime edges remain pending",
        "slice_count": len(slices),
        "slices": slices,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "yaml_files": len(inventory),
        "parse_status": dict(Counter(row["parse_status"] for row in inventory)),
        "shape_issue_files": sum(bool(row["shape_issues"]) for row in inventory),
        "shape_issues": dict(Counter(issue for row in inventory for issue in row["shape_issues"])),
        "train_ticket_files": len(train_ticket_docs),
        "train_ticket_kinds": dict(Counter(item["kind"] for item in train_ticket_docs)),
        "test_nodes": dict(node_counts),
        "output_files": [
            str((OUT_ROOT / "yaml_inventory.csv").relative_to(ROOT)),
            str((OUT_ROOT / "test_node_catalog.json").relative_to(ROOT)),
            str((OUT_ROOT / "train_ticket_test_slices.json").relative_to(ROOT)),
        ],
    }
    (OUT_ROOT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    build()
