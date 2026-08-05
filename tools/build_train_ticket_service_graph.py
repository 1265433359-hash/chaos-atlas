from __future__ import annotations

import copy
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT / "train-ticket"
ARTIFACT_ROOT = ROOT / "artifacts" / "train-ticket"
SERVICE_RE = re.compile(r"\bts-[a-z0-9-]+-service\b")
GET_SERVICE_RE = re.compile(r"getServiceUrl\(\s*[\"'](ts-[a-z0-9-]+-service)[\"']\s*\)")
FEIGN_RE = re.compile(r"@FeignClient\s*\([^)]*?(?:name|value)\s*=\s*[\"'](ts-[a-z0-9-]+-service)[\"']")


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def service_dirs() -> dict[str, Path]:
    return {
        path.name: path
        for path in PROJECT_ROOT.iterdir()
        if path.is_dir() and path.name.startswith("ts-") and path.name != "ts-common"
    }


def config_info(module: Path, service: str) -> dict[str, Any]:
    configs = list((module / "src" / "main" / "resources").glob("application.y*ml"))
    info: dict[str, Any] = {"application": service, "port": None, "paths": [], "dependencies": []}
    for path in configs:
        info["paths"].append(relative(path))
        text = path.read_text(encoding="utf-8", errors="replace")
        port_match = re.search(r"(?m)^\s*port:\s*(\d+)\s*(?:#.*)?$", text)
        if port_match:
            info["port"] = int(port_match.group(1))
        lower = text.lower()
        if "jdbc:mysql" in lower:
            info["dependencies"].append({"name": "mysql", "type": "database", "evidence": relative(path)})
        if "nacos" in lower:
            info["dependencies"].append({"name": "nacos", "type": "service_discovery", "evidence": relative(path)})
        if "rabbitmq" in lower:
            info["dependencies"].append({"name": "rabbitmq", "type": "message_queue", "evidence": relative(path)})
    return info


def source_edges(module: Path, service: str, all_services: set[str]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for path in (module / "src" / "main").rglob("*") if (module / "src" / "main").exists() else []:
        if not path.is_file() or path.suffix.lower() not in {".java", ".py", ".js", ".ts", ".go"}:
            continue
        if any(part.lower() in {"node_modules", "target", "build", ".git"} for part in path.parts):
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line_number, line in enumerate(lines, start=1):
            targets = set(GET_SERVICE_RE.findall(line)) | set(FEIGN_RE.findall(line))
            for target in SERVICE_RE.findall(line):
                if target in all_services and target != service:
                    targets.add(target)
            for target in sorted(targets):
                mechanism = "service_name_reference"
                if GET_SERVICE_RE.search(line):
                    mechanism = "service_discovery_url"
                elif FEIGN_RE.search(line):
                    mechanism = "feign_client"
                elif "restTemplate" in line or "RestTemplate" in line:
                    mechanism = "rest_template_reference"
                edges.append({
                    "from": service,
                    "to": target,
                    "type": "calls_candidate",
                    "mechanism": mechanism,
                    "path": relative(path),
                    "line": line_number,
                })
    unique: dict[tuple[str, str, str, str, int], dict[str, Any]] = {}
    for edge in edges:
        key = (edge["from"], edge["to"], edge["mechanism"], edge["path"], edge["line"])
        unique[key] = edge
    return list(unique.values())


def main() -> None:
    dirs = service_dirs()
    all_services = set(dirs)
    nodes = []
    edges = []
    for service, module in sorted(dirs.items()):
        info = config_info(module, service)
        nodes.append({"id": service, "module": relative(module), **info})
        edges.extend(source_edges(module, service, all_services))
    graph = {
        "schema_version": "0.1",
        "project": "FudanSELab/train-ticket",
        "commit": "313886e99befb94be6cd45f085c98e0019f59829",
        "scope": "static source/config service graph; runtime reachability remains pending",
        "nodes": nodes,
        "edges": edges,
    }
    graph_path = ARTIFACT_ROOT / "train_ticket_service_graph.json"
    graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")

    refined = json.loads((ARTIFACT_ROOT / "train_ticket_test_slices_refined.json").read_text(encoding="utf-8"))
    edge_by_source = defaultdict(list)
    for edge in edges:
        edge_by_source[edge["from"]].append(edge)
    slices = []
    for original in refined["slices"]:
        item = copy.deepcopy(original)
        app = ((item.get("selector") or {}).get("labels") or {}).get("app")
        outgoing = edge_by_source.get(app, []) if app else []
        item["service_slice"] = {
            "root_test_node": item.get("test_nodes", []),
            "target_service": app,
            "outgoing_call_candidates": outgoing,
            "downstream_services": sorted({edge["to"] for edge in outgoing}),
            "evidence": "static_source_config_candidate" if outgoing else "no_static_outgoing_edge_found",
            "runtime_trace_status": "pending",
        }
        slices.append(item)
    slice_payload = {
        "schema_version": "0.2",
        "project": refined["project"],
        "commit": refined["commit"],
        "scope": "test-node-centered slice plus static cross-service call candidates",
        "slice_count": len(slices),
        "slices": slices,
    }
    slice_path = ARTIFACT_ROOT / "train_ticket_test_slices_graph.json"
    slice_path.write_text(json.dumps(slice_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report = {
        "service_count": len(nodes),
        "call_edge_count": len(edges),
        "services_with_outgoing_edges": len({edge["from"] for edge in edges}),
        "slices_with_outgoing_edges": sum(bool(item["service_slice"]["outgoing_call_candidates"]) for item in slices),
        "output_graph": str(graph_path.relative_to(ROOT)),
        "output_slices": str(slice_path.relative_to(ROOT)),
    }
    (ARTIFACT_ROOT / "service_graph_summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
