"""Build a read-only cross-project coverage report from RCA artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from tools.problem_identity import derive_problem_identity
except ModuleNotFoundError:  # direct script invocation
    from problem_identity import derive_problem_identity


def _empty_project() -> dict[str, Any]:
    return {
        "artifact_count": 0,
        "eligible_run_count": 0,
        "confirmed_rca_count": 0,
        "families": [],
        "unique_weakness_count": 0,
        "independent_problem_count": 0,
    }


def build_coverage_report(root: Path) -> dict[str, Any]:
    root = Path(root)
    projects: dict[str, dict[str, Any]] = {}
    families: dict[str, dict[str, Any]] = {}
    weakness_keys: set[tuple[str, str]] = set()
    issue_keys: set[tuple[str, str]] = set()
    artifact_count = 0
    parse_error_count = 0
    unattributed_artifact_count = 0
    eligible_count = 0
    for path in sorted(root.rglob("rca.json")):
        artifact_count += 1
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("artifact must be an object")
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
            parse_error_count += 1
            continue
        identity = derive_problem_identity(value)
        project = identity["project_id"]
        family = identity["fault_family"] or "unknown"
        if not project:
            unattributed_artifact_count += 1
            continue
        project_row = projects.setdefault(project, _empty_project())
        project_row["artifact_count"] += 1
        family_row = families.setdefault(family, {"projects": set(), "artifact_count": 0, "eligible_run_count": 0, "unique_weaknesses": set(), "independent_problems": set()})
        family_row["projects"].add(project)
        family_row["artifact_count"] += 1
        if not identity["eligible"]:
            continue
        eligible_count += 1
        project_row["eligible_run_count"] += 1
        project_row["confirmed_rca_count"] += 1
        family_row["eligible_run_count"] += 1
        if family not in project_row["families"]:
            project_row["families"].append(family)
        key = (project, identity["weakness_id"])
        if identity["weakness_id"]:
            weakness_keys.add(key)
            family_row["unique_weaknesses"].add(key)
        issue_key = (project, identity["issue_id"])
        issue_keys.add(issue_key)
        family_row["independent_problems"].add(issue_key)
    for project_row in projects.values():
        project_row["families"].sort()
        project = next((name for name, row in projects.items() if row is project_row), "")
        project_row["unique_weakness_count"] = len({key for key in weakness_keys if key[0] == project})
        project_row["independent_problem_count"] = len({key for key in issue_keys if key[0] == project})
    normalized_families = {}
    for family, row in sorted(families.items()):
        normalized_families[family] = {
            "projects": sorted(row["projects"]),
            "artifact_count": row["artifact_count"],
            "eligible_run_count": row["eligible_run_count"],
            "unique_weakness_count": len(row["unique_weaknesses"]),
            "independent_problem_count": len(row["independent_problems"]),
        }
    return {
        "schema_version": "chaosatlas-coverage-report-v1",
        "artifact_count": artifact_count,
        "parse_error_count": parse_error_count,
        "unattributed_artifact_count": unattributed_artifact_count,
        "eligible_run_count": eligible_count,
        "confirmed_weakness_count": len(weakness_keys),
        "independent_problem_count": len(issue_keys),
        "project_count": len(projects),
        "projects": {name: projects[name] for name in sorted(projects)},
        "families": normalized_families,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_coverage_report(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("project_count", "eligible_run_count", "confirmed_weakness_count", "independent_problem_count")}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
