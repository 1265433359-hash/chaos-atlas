from __future__ import annotations

import copy
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "raw_yaml"
PROJECT_ROOT = ROOT / "train-ticket"
ARTIFACT_ROOT = ROOT / "artifacts" / "train-ticket"

JAVA_METHOD_RE = re.compile(
    r"^\s*(?:public|protected|private|static|final|synchronized|native|abstract|default|\s)+"
    r"[A-Za-z_$][\w$<>\[\],.? ]*\s+([A-Za-z_$][\w$]*)\s*\([^;{}]*\)\s*(?:throws [^{]+)?\{"
)
PYTHON_FUNCTION_RE = re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(")
JS_FUNCTION_RE = re.compile(r"\b(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(|\b([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>")
GO_FUNCTION_RE = re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\(")
CALL_RE = re.compile(r"\b([A-Za-z_$][\w$]*)\s*\(")
CONTROL_WORDS = {
    "if", "for", "while", "switch", "catch", "try", "return", "new", "throw", "assert",
    "log", "println", "print", "super", "this", "else", "finally",
}
CONTROL_SIGNALS = {
    "if": "branch",
    "try": "try_block",
    "catch": "exception_handler",
    "throw": "exception_throw",
    "exception": "exception_path",
    "timeout": "timeout",
    "retry": "retry",
    "fallback": "fallback",
    "circuit": "circuit_breaker",
    "rollback": "rollback",
    "transaction": "transaction",
    "resttemplate": "http_client",
    "feign": "http_client",
    "webclient": "http_client",
    "grpc": "rpc_client",
}
DATA_SIGNALS = {
    "repository": "repository",
    "dao": "database_access",
    "mapper": "data_mapping",
    "mongo": "mongodb",
    "mysql": "mysql",
    "redis": "cache",
    "rabbit": "message_queue",
    "response": "response_data",
    "status": "business_status",
    "order": "order_data",
    "ticket": "ticket_data",
    "price": "price_data",
    "seat": "seat_data",
}


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def source_paths(module: Path) -> list[Path]:
    paths = []
    for path in module.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".java", ".py", ".js", ".ts", ".go"}:
            continue
        if any(part.lower() in {"node_modules", "target", "build", ".git"} for part in path.parts):
            continue
        paths.append(path)
    return sorted(paths, key=lambda path: (any(part.lower() in {"test", "tests"} for part in path.parts), str(path)))


def method_match(path: Path, line: str) -> str | None:
    suffix = path.suffix.lower()
    if suffix == ".java":
        match = JAVA_METHOD_RE.search(line)
        return match.group(1) if match else None
    if suffix == ".py":
        match = PYTHON_FUNCTION_RE.search(line)
        return match.group(1) if match else None
    if suffix in {".js", ".ts"}:
        match = JS_FUNCTION_RE.search(line)
        return (match.group(1) or match.group(2)) if match else None
    if suffix == ".go":
        match = GO_FUNCTION_RE.search(line)
        return match.group(1) if match else None
    return None


def body_end(lines: list[str], start: int) -> int:
    depth = 0
    seen_open = False
    for index in range(start, min(len(lines), start + 600)):
        depth += lines[index].count("{")
        depth -= lines[index].count("}")
        seen_open = seen_open or "{" in lines[index]
        if seen_open and depth <= 0:
            return index
    return min(len(lines) - 1, start + 80)


def signals(text: str, mapping: dict[str, str]) -> list[str]:
    lower = text.lower()
    return sorted({value for token, value in mapping.items() if token in lower})


def build_module_index(module: Path) -> dict[str, Any]:
    raw_methods: list[dict[str, Any]] = []
    for path in source_paths(module):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line_number, line in enumerate(lines):
            name = method_match(path, line)
            if not name:
                continue
            end_line = body_end(lines, line_number)
            body = "\n".join(lines[line_number:end_line + 1])
            raw_methods.append({
                "name": name,
                "path": relative(path),
                "line": line_number + 1,
                "end_line": end_line + 1,
                "role": "test" if any(part.lower() in {"test", "tests"} for part in path.parts) else "production",
                "control_signals": signals(body, CONTROL_SIGNALS),
                "data_signals": signals(body, DATA_SIGNALS),
                "body_text": body,
            })
    production = [item for item in raw_methods if item["role"] == "production"]
    known_names = {item["name"] for item in raw_methods}
    methods: list[dict[str, Any]] = []
    for item in raw_methods:
        calls = sorted({
            name for name in CALL_RE.findall(item.pop("body_text"))
            if name in known_names and name != item["name"] and name not in CONTROL_WORDS
        })
        item["calls"] = calls
        methods.append(item)
    return {
        "module": relative(module),
        "files": sorted({item["path"] for item in methods}),
        "methods": methods,
        "production_method_count": len(production),
        "test_method_count": len(raw_methods) - len(production),
    }


def test_family(nodes: list[str]) -> str:
    if any(node.startswith("http_") for node in nodes):
        return "http"
    if any(node.startswith("network_") for node in nodes):
        return "network"
    if any(node.startswith("stress_") for node in nodes):
        return "stress"
    if any(node.startswith("pod_") for node in nodes):
        return "pod"
    return "other"


def relevant_methods(index: dict[str, Any], family: str) -> list[dict[str, Any]]:
    methods = [item for item in index["methods"] if item["role"] == "production"]
    selected: list[dict[str, Any]] = []
    for item in methods:
        path_text = item["path"].lower()
        signal_text = " ".join(item["control_signals"] + item["data_signals"])
        reasons: list[str] = []
        if any(token in path_text for token in {"controller", "service", "client", "gateway", "handler", "filter"}):
            reasons.append("entry_or_dependency_module")
        if family in {"http", "network"} and any(token in signal_text for token in {"http_client", "rpc_client", "timeout", "retry", "fallback", "exception_handler", "circuit_breaker"}):
            reasons.append("resilience_signal")
        if family == "stress" and any(token in signal_text for token in {"timeout", "exception_handler", "transaction", "repository", "database_access", "message_queue"}):
            reasons.append("resource_or_backpressure_signal")
        if family == "pod" and any(token in signal_text for token in {"retry", "timeout", "exception_handler", "cache", "message_queue"}):
            reasons.append("restart_or_dependency_signal")
        if reasons:
            copy_item = {key: value for key, value in item.items() if key != "body_text"}
            copy_item["candidate_reasons"] = sorted(set(reasons))
            selected.append(copy_item)
    return selected[:160]


def load_deployments() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for path in (PROJECT_ROOT / "deployment").rglob("*"):
        if path.suffix.lower() not in {".yaml", ".yml"}:
            continue
        try:
            documents = yaml.safe_load_all(path.read_text(encoding="utf-8", errors="replace"))
            for document in documents:
                if not isinstance(document, dict) or document.get("kind") != "Deployment":
                    continue
                metadata = document.get("metadata") or {}
                template = ((document.get("spec") or {}).get("template") or {})
                labels = ((template.get("metadata") or {}).get("labels") or {})
                result.append({
                    "name": metadata.get("name"),
                    "app": labels.get("app"),
                    "path": relative(path),
                })
        except Exception:
            continue
    return result


def workflow_leaf_nodes(document: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    spec = document.get("spec") or {}
    templates = spec.get("templates") or []
    by_name = {item.get("name"): item for item in templates if isinstance(item, dict) and item.get("name")}
    graph_nodes: list[dict[str, Any]] = []
    graph_edges: list[dict[str, Any]] = []
    leaves: list[dict[str, Any]] = []
    for template in templates:
        name = template.get("name")
        template_type = template.get("templateType") or template.get("type") or "unknown"
        graph_nodes.append({"name": name, "template_type": template_type})
        for child in template.get("children") or []:
            graph_edges.append({"from": name, "to": child, "type": "controls"})
        if template_type in {"Serial", "Parallel", "Schedule", "StatusCheck", "Suspend", "Duration"} and not template.get("type"):
            continue
        chaos_type = template.get("type")
        if not chaos_type:
            continue
        key = chaos_type[:1].lower() + chaos_type[1:]
        body = template.get(key) or {}
        body_spec = body.get("spec") if isinstance(body, dict) and isinstance(body.get("spec"), dict) else body
        if not isinstance(body_spec, dict):
            body_spec = {}
        nodes = []
        if chaos_type == "NetworkChaos":
            nodes.append(f"network_{body_spec.get('action') or 'unspecified'}")
        elif chaos_type == "StressChaos":
            for stressor in (body_spec.get("stressors") or {}):
                nodes.append(f"stress_{stressor}")
        elif chaos_type == "PodChaos":
            nodes.append(f"pod_{body_spec.get('action') or 'unspecified'}")
        elif chaos_type == "HTTPChaos":
            nodes.append("http_fault_unspecified")
        else:
            nodes.append(chaos_type.lower())
        leaves.append({
            "template": name,
            "kind": chaos_type,
            "nodes": sorted(set(nodes)),
            "selector": body_spec.get("selector") or {},
            "mode": body_spec.get("mode"),
            "action": body_spec.get("action"),
            "spec_keys": sorted(body_spec),
        })
    return leaves, [{"nodes": graph_nodes, "edges": graph_edges, "entry": spec.get("entry")}]


def main() -> None:
    source_path = ARTIFACT_ROOT / "train_ticket_test_slices.json"
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    deployments = load_deployments()
    module_cache: dict[str, dict[str, Any]] = {}
    refined = []
    workflow_count = 0
    for original in payload["slices"]:
        item = copy.deepcopy(original)
        app = (item.get("selector") or {}).get("labels", {}).get("app", "")
        family = test_family(item.get("test_nodes") or [])
        module_path = PROJECT_ROOT / app if app else None
        if module_path and module_path.is_dir():
            module_cache.setdefault(app, build_module_index(module_path))
            index = module_cache[app]
            candidates = relevant_methods(index, family)
            function_edges = []
            known = {method["name"] for method in index["methods"]}
            for method in candidates:
                for called in method.get("calls", []):
                    if called in known:
                        function_edges.append({"from": method["name"], "to": called, "type": "calls", "evidence": method["path"]})
            item["function_slice"] = {
                "family": family,
                "module": index["module"],
                "production_method_count": index["production_method_count"],
                "test_method_count": index["test_method_count"],
                "candidate_methods": candidates,
                "edges": function_edges,
                "control_signals": sorted({signal for method in candidates for signal in method.get("control_signals", [])}),
                "data_signals": sorted({signal for method in candidates for signal in method.get("data_signals", [])}),
                "evidence": "static_source_candidate",
            }
        else:
            item["function_slice"] = {
                "family": family,
                "module": None,
                "production_method_count": 0,
                "test_method_count": 0,
                "candidate_methods": [],
                "edges": [],
                "control_signals": [],
                "data_signals": [],
                "evidence": "unverified",
            }
        if item.get("kind") == "Workflow":
            source = ROOT / item["source"]
            document = yaml.safe_load(source.read_text(encoding="utf-8", errors="replace"))
            leaves, workflow_graph = workflow_leaf_nodes(document)
            for leaf in leaves:
                selector = leaf.get("selector") or {}
                labels = selector.get("labelSelectors") or {}
                target_app = labels.get("app")
                if target_app:
                    matches = [d for d in deployments if d.get("app") == target_app]
                elif "train-ticket" in (selector.get("namespaces") or []):
                    matches = [d for d in deployments if str(d.get("app") or "").startswith("ts-")]
                else:
                    matches = []
                unique_matches = {}
                for match in matches:
                    unique_matches.setdefault((match.get("name"), match.get("app")), match)
                leaf["manifest_match_count"] = len(matches)
                leaf["target_match_count"] = len(unique_matches)
                leaf["target_matches"] = list(unique_matches.values())[:120]
                leaf["blast_radius"] = "high" if leaf.get("mode") == "all" and not target_app else "bounded_candidate"
                leaf["evidence"] = "static_manifest_candidate" if matches else "unverified"
            item["workflow_graph"] = workflow_graph[0]
            item["workflow_leaf_slices"] = leaves
            workflow_count += 1
        refined.append(item)
    output = {
        "schema_version": "0.2",
        "project": payload["project"],
        "commit": payload["commit"],
        "scope": "static test-node-centered source and workflow slice; runtime reachability remains pending",
        "slice_count": len(refined),
        "workflow_count": workflow_count,
        "module_count": len(module_cache),
        "slices": refined,
    }
    output_path = ARTIFACT_ROOT / "train_ticket_test_slices_refined.json"
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    report = {
        "slice_count": len(refined),
        "workflow_count": workflow_count,
        "module_count": len(module_cache),
        "source_function_candidates": sum(len(item["function_slice"]["candidate_methods"]) for item in refined),
        "function_edges": sum(len(item["function_slice"]["edges"]) for item in refined),
        "workflow_leaf_count": sum(len(item.get("workflow_leaf_slices", [])) for item in refined),
        "high_blast_radius_workflow_leaves": sum(
            1 for item in refined for leaf in item.get("workflow_leaf_slices", []) if leaf.get("blast_radius") == "high"
        ),
        "output": str(output_path.relative_to(ROOT)),
    }
    (ARTIFACT_ROOT / "refined_summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
