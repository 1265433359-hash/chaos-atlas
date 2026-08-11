"""Analyze selection-only outputs against the out-of-band static oracle."""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INPUT_ROOT = ROOT / "artifacts/experiments/knowledge_ablation_selection_only"
ORACLE_ROOT = ROOT / "artifacts/experiments/knowledge_ablation_oracle"
OUT_ROOT = INPUT_ROOT / "analysis"
DEFAULT_SELECTION_ROOT = INPUT_ROOT / "selections" / "run-20260810-r2"
PROJECT_ARMS = {"ESHOP": ("blind", "generic", "partial-pre"), "SOCIALNET": ("blind", "generic", "full-pre")}
SEEDS = {"pilot": (1001, 1002, 1003), "formal": (2001, 2002, 2003)}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def expected_records() -> list[tuple[str, str, str, int]]:
    return [(project, arm, phase, seed) for project, arms in PROJECT_ARMS.items() for arm in arms for phase, seeds in SEEDS.items() for seed in seeds]


def run(selection_root: Path = DEFAULT_SELECTION_ROOT) -> dict[str, Any]:
    selection_root = selection_root.resolve()
    rows: list[dict[str, Any]] = []
    for project, arm_dir, phase, seed in expected_records():
        result_path = selection_root / project / arm_dir / phase / f"seed-{seed}.json"
        if not result_path.exists():
            rows.append({"project": project, "arm_dir": arm_dir, "phase": phase, "seed": seed, "status": "missing_selection"})
            continue
        result = load(result_path)
        oracle = load(ORACLE_ROOT / project / "candidate_protection_classification.json")["classifications"]
        selected = result.get("selected") or []
        classes = [oracle.get(item.get("candidate_id"), {}).get("class", "unknown") for item in selected]
        k = len(selected)
        rows.append({
            "project": project,
            "arm": result.get("arm"),
            "arm_dir": arm_dir,
            "phase": phase,
            "seed": seed,
            "status": result.get("status"),
            "selected_count": k,
            "protected_selected": classes.count("protected"),
            "unprotected_selected": classes.count("unprotected"),
            "unknown_selected": classes.count("unknown"),
            "protected_waste": classes.count("protected") / k if k else None,
            "unprotected_selection_fraction": classes.count("unprotected") / k if k else None,
            "tokens": (result.get("metadata") or {}).get("total_tokens"),
            "elapsed_ms": result.get("elapsed_ms"),
            "result_path": str(result_path.relative_to(ROOT)).replace("\\", "/"),
        })
    valid = [row for row in rows if row["status"] == "valid"]
    by_condition: dict[str, list[dict[str, Any]]] = {}
    for row in valid:
        by_condition.setdefault(f"{row['project']}::{row['arm']}::{row['phase']}", []).append(row)
    summaries = []
    for key, group in sorted(by_condition.items()):
        summaries.append({
            "condition": key,
            "n_valid_seeds": len(group),
            "protected_waste_mean": sum(row["protected_waste"] for row in group) / len(group),
            "unprotected_selection_fraction_mean": sum(row["unprotected_selection_fraction"] for row in group) / len(group),
            "selected_count_mean": sum(row["selected_count"] for row in group) / len(group),
            "total_tokens": sum(row["tokens"] for row in group if isinstance(row["tokens"], int)),
            "elapsed_ms_mean": sum(row["elapsed_ms"] for row in group) / len(group),
        })
    paired_differences: list[dict[str, Any]] = []
    for project in PROJECT_ARMS:
        for phase in SEEDS:
            blind = {(row["seed"]): row for row in valid if row["project"] == project and row["phase"] == phase and row["arm"] == "LLM-blind"}
            knowledge_arms = sorted({row["arm"] for row in valid if row["project"] == project and row["phase"] == phase and row["arm"] != "LLM-blind"})
            for arm in knowledge_arms:
                treated = {(row["seed"]): row for row in valid if row["project"] == project and row["phase"] == phase and row["arm"] == arm}
                deltas = [
                    {
                        "seed": seed,
                        "delta_protected_waste": treated[seed]["protected_waste"] - blind[seed]["protected_waste"],
                        "delta_unprotected_selection_fraction": treated[seed]["unprotected_selection_fraction"] - blind[seed]["unprotected_selection_fraction"],
                        "delta_tokens": treated[seed]["tokens"] - blind[seed]["tokens"] if isinstance(treated[seed]["tokens"], int) and isinstance(blind[seed]["tokens"], int) else None,
                    }
                    for seed in sorted(set(blind) & set(treated))
                ]
                paired_differences.append({
                    "project": project,
                    "phase": phase,
                    "arm": arm,
                    "baseline": "LLM-blind",
                    "seed_deltas": deltas,
                    "median_delta_protected_waste": statistics.median(item["delta_protected_waste"] for item in deltas),
                    "median_delta_unprotected_selection_fraction": statistics.median(item["delta_unprotected_selection_fraction"] for item in deltas),
                    "median_delta_tokens": statistics.median(item["delta_tokens"] for item in deltas if item["delta_tokens"] is not None),
                })
    return {
        "schema_version": 1,
        "kind": "selection_only_analysis",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "complete" if len(valid) == len(rows) else "blocked_missing_or_invalid_selection_outputs",
        "records_expected": len(rows),
        "records_valid": len(valid),
        "runtime_execution_performed": False,
        "runtime_claims_allowed": False,
        "rows": rows,
        "summaries": summaries,
        "paired_differences": paired_differences,
        "metric_definition": {
            "protected_waste": "protected static-oracle candidates selected / selected count",
            "unprotected_selection_fraction": "unprotected static-oracle candidates selected / selected count",
            "note": "These are selection-only static metrics, not confirmed runtime weakness metrics.",
        },
    }


def render(report: dict[str, Any]) -> str:
    lines = [
        "# Selection-Only Analysis",
        "",
        f"Status: **{report['status']}**",
        "",
        f"Valid selection records: {report['records_valid']}/{report['records_expected']}",
        "",
        "This report uses only the out-of-band static protection oracle. It does not measure runtime weakness discovery, recall, RCA, or unique issue yield.",
        "",
        "| Condition | Valid seeds | Protected waste | Unprotected selection |",
        "|---|---:|---:|---:|",
    ]
    for row in report["summaries"]:
        lines.append(f"| {row['condition']} | {row['n_valid_seeds']} | {row['protected_waste_mean']:.3f} | {row['unprotected_selection_fraction_mean']:.3f} |")
    lines.extend([
        "",
        "## Paired Differences vs Blind",
        "",
        "Positive protected-waste differences are worse; positive unprotected-selection differences indicate more statically unprotected candidates selected. These are descriptive seed-level comparisons, not cross-project inference.",
        "",
        "| Project | Phase | Arm | Median delta protected waste | Median delta unprotected selection | Median delta tokens |",
        "|---|---|---|---:|---:|---:|",
    ])
    for row in report["paired_differences"]:
        lines.append(f"| {row['project']} | {row['phase']} | {row['arm']} | {row['median_delta_protected_waste']:.3f} | {row['median_delta_unprotected_selection_fraction']:.3f} | {row['median_delta_tokens']} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUT_ROOT)
    parser.add_argument("--selection-root", type=Path, default=DEFAULT_SELECTION_ROOT)
    args = parser.parse_args()
    report = run(args.selection_root)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "selection_only_analysis.json").write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    (args.output_dir / "selection_only_analysis.md").write_text(render(report), encoding="utf-8")
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
