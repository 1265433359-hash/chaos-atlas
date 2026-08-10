#!/usr/bin/env python3
"""Read-only feasibility check for the pooled held-out protocol v1.2."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List


DEFAULT_PROJECTS = ("HOTEL", "SOCIALNET", "TEASTORE")
CLASS_NAMES = ("protected", "unprotected", "unknown")


def _pool_path(root: Path, project: str) -> Path:
    return root / f"{project.lower()}_candidate_pool_formal.json"


def _load_pool(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("candidates"), list):
        raise ValueError(f"invalid candidate pool schema: {path}")
    return payload


def _counts(candidates: Iterable[Dict[str, Any]]) -> Counter:
    counts = Counter()
    for candidate in candidates:
        protection_class = candidate.get("protection_class")
        if protection_class not in CLASS_NAMES:
            raise ValueError(f"invalid protection_class={protection_class!r}")
        counts[protection_class] += 1
    return counts


def check_feasibility(
    root: Path,
    projects: Iterable[str] = DEFAULT_PROJECTS,
    protected_min: int = 16,
    unprotected_min: int = 16,
    unknown_min: int = 16,
    legal_total_min: int = 48,
    min_project_legal: int = 8,
) -> Dict[str, Any]:
    project_rows: List[Dict[str, Any]] = []
    pooled = Counter()
    for project in projects:
        normalized = project.upper()
        path = _pool_path(root, normalized)
        payload = _load_pool(path)
        candidates = payload["candidates"]
        counts = _counts(candidates)
        pooled.update(counts)
        project_rows.append(
            {
                "project_id": normalized,
                "source_file": str(path).replace("\\", "/"),
                "pool_status": payload.get("status"),
                "total": len(candidates),
                "protected": counts["protected"],
                "unprotected": counts["unprotected"],
                "unknown": counts["unknown"],
                "project_legal_min_pass": len(candidates) >= min_project_legal,
            }
        )

    thresholds = {
        "protected": protected_min,
        "unprotected": unprotected_min,
        "unknown": unknown_min,
        "legal_total": legal_total_min,
    }
    pooled_row = {
        "protected": pooled["protected"],
        "unprotected": pooled["unprotected"],
        "unknown": pooled["unknown"],
        "legal_total": sum(pooled[name] for name in CLASS_NAMES),
    }
    pooled_gate = {
        name: pooled_row[name] >= minimum for name, minimum in thresholds.items()
    }
    class_project_support = {
        name: sum(row[name] > 0 for row in project_rows) for name in CLASS_NAMES
    }
    # A class supported by one project remains descriptive-only in v1.2.
    inferential_class_support = {
        name: class_project_support[name] >= 2 for name in CLASS_NAMES
    }
    project_gate = all(row["project_legal_min_pass"] for row in project_rows)
    return {
        "schema_version": 1,
        "protocol": "heldout_protocol_v1_2",
        "read_only": True,
        "projects": project_rows,
        "pooled": pooled_row,
        "thresholds": thresholds,
        "pooled_gate": pooled_gate,
        "all_pooled_gates_pass": all(pooled_gate.values()),
        "min_project_legal": min_project_legal,
        "all_project_minimums_pass": project_gate,
        "class_project_support": class_project_support,
        "inferential_class_support": inferential_class_support,
        "descriptive_only_classes": [
            name for name, supported in inferential_class_support.items() if not supported
        ],
        "qualification": "pass"
        if all(pooled_gate.values()) and project_gate
        else "blocked",
        "no_experiment_run": True,
        "no_candidate_pool_mutation": True,
        "note": (
            "Pooled eligibility is separate from v1.1 per-project eligibility. "
            "Inference remains equally weighted by project; classes supported by "
            "fewer than two projects are descriptive-only."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("artifacts/experiments/heldout"),
        help="directory containing *_candidate_pool_formal.json",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--projects", nargs="+", default=list(DEFAULT_PROJECTS))
    args = parser.parse_args()
    result = check_feasibility(args.root, args.projects)
    encoded = json.dumps(result, indent=2, ensure_ascii=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0 if result["qualification"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
