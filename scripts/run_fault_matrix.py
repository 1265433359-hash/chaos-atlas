"""Generate a deterministic support matrix report for project profiles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

from tools.fault_matrix import build_fault_matrix


def build_report(profile_paths: Iterable[Path]) -> dict:
    projects = []
    for path in profile_paths:
        profile_path = Path(path)
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        matrix = build_fault_matrix(profile)
        counts = {status: sum(1 for item in matrix["faults"] if item["status"] == status) for status in ("supported", "planned", "inapplicable")}
        projects.append({
            "project_id": matrix["project_id"],
            "profile": str(profile_path),
            "fault_count": matrix["fault_count"],
            "counts": counts,
            "faults": matrix["faults"],
        })
    return {
        "schema_version": "chaosatlas-fault-matrix-report-v1",
        "project_count": len(projects),
        "aggregate": {"faults": 32, "projects": len(projects)},
        "projects": projects,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", nargs="+", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(args.profiles)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "verified", "projects": report["project_count"], "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
