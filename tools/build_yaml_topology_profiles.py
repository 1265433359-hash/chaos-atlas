"""Build secret-free topology evidence for the frozen ten-project matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from tools.yaml_topology import parse_paths
except ModuleNotFoundError:  # direct `python tools/script.py` invocation
    from yaml_topology import parse_paths


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "artifacts/experiments/chaosatlas_10_projects"
SOURCE_ROOT = EXPERIMENT / "sources"
OUT_ROOT = EXPERIMENT / "topology_profiles"


def build(project_id: str) -> dict:
    source = SOURCE_ROOT / project_id
    result = parse_paths([source]) if source.exists() else parse_paths([])
    result["project_id"] = project_id
    result["source_tree_root"] = str(source.relative_to(ROOT)).replace("\\", "/") if source.exists() else None
    result["source_files"] = [str(Path(item).resolve().relative_to(ROOT)).replace("\\", "/") for item in result.get("source_files", []) if Path(item).resolve().is_relative_to(ROOT)]
    result["runtime_use"] = "evidence_only"
    return result


def merge_reports(existing: list[dict], updates: list[dict]) -> list[dict]:
    by_project = {str(item.get("project_id")): item for item in existing}
    by_project.update({str(item.get("project_id")): item for item in updates})
    return [by_project[key] for key in sorted(by_project)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--projects", nargs="+", default=[f"P{i:02d}" for i in range(1, 11)])
    args = parser.parse_args()
    existing_path = OUT_ROOT / "manifest.json"
    existing = json.loads(existing_path.read_text(encoding="utf-8")) if existing_path.exists() else {"projects": []}
    existing_reports = list(existing.get("projects", []))
    reports: list[dict] = []
    for project_id in args.projects:
        result = build(project_id)
        out = OUT_ROOT / project_id / "topology.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        reports.append({"project_id": project_id, "nodes": len(result["nodes"]), "edges": len(result["edges"]), "graph_hash": result["graph_hash"]})
    reports = merge_reports(existing_reports, reports)
    expected = {f"P{i:02d}" for i in range(1, 11)}
    manifest = {"schema_version": "1.0", "kind": "topology_profile_manifest", "projects": reports, "requested_projects": args.projects, "complete": {str(item.get("project_id")) for item in reports} >= expected, "source": "frozen source trees", "no_llm_called": True}
    (OUT_ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
