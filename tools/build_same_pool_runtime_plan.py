"""Build a deduplicated runtime plan from same-pool selections."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


PROJECTS = ("online-boutique", "opentelemetry-demo", "sock-shop")
METHODS = ("ChaosAtlas-full", "ChaosAtlas-ablation", "ChaosEater-adapter")
REPLICATES = (1, 2)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object expected: {path}")
    return value


def build_runtime_plan(*, freeze_root: Path, selection_root: Path, projects: Iterable[str] = PROJECTS) -> dict[str, Any]:
    freeze_root = Path(freeze_root)
    selection_root = Path(selection_root)
    selected_projects = tuple(projects)
    candidate_lookup: dict[str, dict[str, dict[str, Any]]] = {}
    for project in selected_projects:
        candidates_path = freeze_root / "candidate_pools" / project / "candidates.json"
        candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
        candidate_lookup[project] = {item["candidate_id"]: item for item in candidates}

    selected_by: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for path in sorted(selection_root.rglob("selection.json")):
        selection = _load(path)
        if selection.get("status") != "completed":
            continue
        project = selection["project_id"]
        if project not in selected_projects:
            continue
        for item in selection.get("selection", {}).get("selected_candidates", []):
            candidate_id = item["candidate_id"]
            if candidate_id not in candidate_lookup[project]:
                raise ValueError(f"selection references outside candidate: {candidate_id}")
            selected_by[(project, candidate_id)].append({
                "method_id": selection["method_id"],
                "seed": selection["seed"],
                "rank": item.get("rank"),
                "reason": item.get("reason", ""),
            })

    candidates_out: list[dict[str, Any]] = []
    units: list[dict[str, Any]] = []
    for (project, candidate_id), selectors in sorted(selected_by.items()):
        candidate = candidate_lookup[project][candidate_id]
        record = {
            "project_id": project,
            "candidate_id": candidate_id,
            "target": candidate["target"],
            "fault_family": candidate["fault_family"],
            "parameters": candidate["parameters"],
            "mutation_path": str((freeze_root / candidate["yaml_path"]).resolve()).replace("\\", "/"),
            "yaml_sha256": candidate["yaml_sha256"],
            "selected_by": sorted(selectors, key=lambda item: (item["method_id"], item["seed"], int(item.get("rank") or 0))),
            "replicates": list(REPLICATES),
        }
        candidates_out.append(record)
        for replicate in REPLICATES:
            units.append({
                "project_id": project,
                "candidate_id": candidate_id,
                "replicate": replicate,
                "mutation_path": record["mutation_path"],
            })
    return {
        "schema_version": "chaosatlas-same-pool-runtime-plan-v1",
        "projects": list(selected_projects),
        "methods": list(METHODS),
        "total_unique_candidates": len(candidates_out),
        "total_runtime_units": len(units),
        "candidates": candidates_out,
        "units": units,
        "human_review": "pending",
        "knowledge_base_updated": False,
    }


def write_runtime_plan(*, freeze_root: Path, selection_root: Path, output: Path) -> dict[str, Any]:
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"refusing non-empty output: {output}")
    output.mkdir(parents=True, exist_ok=True)
    plan = build_runtime_plan(freeze_root=freeze_root, selection_root=selection_root)
    (output / "runtime-plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return plan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze-root", type=Path, required=True)
    parser.add_argument("--selection-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = write_runtime_plan(freeze_root=args.freeze_root, selection_root=args.selection_root, output=args.output)
    print(json.dumps({"status": "completed", "unique_candidates": result["total_unique_candidates"], "runtime_units": result["total_runtime_units"]}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
