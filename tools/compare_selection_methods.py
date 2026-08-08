"""Compare candidate-selection methods (M0/M1/M3/M4) against partial ground truth.

The 12-candidate pool has only PARTIAL ground truth: 6 candidates were
executed with a concluded runtime finding, the other 6 were never executed
(their outcome is unknown). Full U@10 is therefore NOT computable without
running the remaining 6 experiments.

What IS computed honestly:
- known-positive recall@10: |selected ∩ D_known| / |D_known|, where D_known is
  the 6 candidates with concluded findings. This is the fraction of known
  weaknesses each method selected.
- unknown remainder: selected candidates with no concluded outcome. Selecting
  unknown candidates is exploration credit, not a miss — a method cannot be
  penalized for candidates whose ground truth is absent.

An important bias is stated explicitly: D_known was chosen for execution by
our earlier methodology (M4 lineage), so M3/M4 are partially circular against
this ground truth; M1 (external LLM) had no access to that history and its hit
rate is the least biased signal.

Reads only committed registries; performs no injection.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXECUTION_DIR = ROOT / "artifacts" / "experiments" / "execution"

METHOD_IDS = ("M0", "M1", "M3", "M4")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def known_discovered_candidates(evidence: dict[str, Any]) -> set[str]:
    discovered: set[str] = set()
    for item in evidence.get("candidates", []):
        if item.get("own_discovery_evidence"):
            discovered.add(str(item["candidate_id"]))
    return discovered


def compute(replicate: int) -> dict[str, Any]:
    registry = load_json(EXECUTION_DIR / f"deep_matrix_registry_r{replicate}_m1.json")
    evidence = load_json(EXECUTION_DIR / "candidate_evidence_status.json")
    known = known_discovered_candidates(evidence)
    universe = set(registry.get("candidate_universe") or [])

    rows: list[dict[str, Any]] = []
    for method in registry.get("methods", []):
        method_id = str(method.get("id"))
        if method_id not in METHOD_IDS:
            continue
        plans = method.get("plans") or []
        selected = {str((plan.get("execution") or {}).get("candidate_id")) for plan in plans}
        hits = selected & known
        recall = len(hits) / len(known) if known else 0.0
        unknown_selected = selected - known
        rows.append(
            {
                "method": method_id,
                "name": method.get("name"),
                "status": method.get("status"),
                "selected_count": len(selected),
                "known_hits": len(hits),
                "known_hit_ids": sorted(hits),
                "known_recall@10": round(recall, 3),
                "unknown_selected": len(unknown_selected),
                "unknown_selected_ids": sorted(unknown_selected),
            }
        )
    return {
        "schema_version": 1,
        "tool": "compare_selection_methods",
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "replicate": replicate,
        "candidate_universe_size": len(universe),
        "known_discovered": sorted(known),
        "known_discovered_count": len(known),
        "metric": "known-positive recall@10 (full U@10 not computable with partial ground truth)",
        "bias_note": (
            "D_known was selected for execution by our earlier methodology (M4 lineage); "
            "M3/M4 recall is partly circular. M1 used no execution history and is the least "
            "biased signal. Unknown candidates count as exploration, never as misses."
        ),
        "methods": rows,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Selection comparison — replicate {report['replicate']}",
        "",
        f"Known discovered candidates ({report['known_discovered_count']}): "
        + ", ".join(report["known_discovered"]),
        "",
        "Metric: **known-positive recall@10** = fraction of known-weakness candidates selected.",
        "Full U@10 is not computable until the remaining "
        f"{report['candidate_universe_size'] - report['known_discovered_count']} "
        "candidates are executed with concluded findings.",
        "",
        "| Method | Selected | Known hits | recall@10 | Unknown selected (exploration) |",
        "|---|---|---:|---:|---:|",
    ]
    for row in report["methods"]:
        lines.append(
            f"| {row['method']} {row['name']} | {row['selected_count']} | "
            f"{row['known_hits']} | {row['known_recall@10']:.3f} | {row['unknown_selected']} |"
        )
    lines.append("")
    lines.append(f"Bias note: {report['bias_note']}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replicate", type=int, required=True)
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--output-md", type=Path, default=None)
    args = parser.parse_args()
    report = compute(args.replicate)
    out_json = args.output_json or EXECUTION_DIR / f"selection_comparison_r{args.replicate}.json"
    out_md = args.output_md or EXECUTION_DIR / f"selection_comparison_r{args.replicate}.md"
    out_json.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    out_md.write_text(render_markdown(report), encoding="utf-8")
    print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
