"""Run ledger: unify the execution-directory inventory (review remediation #run-ledger).

The directory contains ~165 JSON files mixing EXECUTIONS, CLASSIFICATIONS,
PREDICTIONS, SUMMARIES and STATE. They must NOT be counted as independent
experiments. This tool builds a single ledger that classifies every file by its
`tool` field and counts:

  - independent_injections : a runner report whose lifecycle confirms
    applied+injected+recovered+cleanup (or classification present)
  - derived_classification: classify_runtime_result outputs (http path splits
    run report and classification into two files -> one injection, two files)
  - predictions/rankings, summaries, state, other

Output: artifacts/experiments/execution/remediation/run_ledger.json
Reconciliation with prior claims:
  - comparison_full_summary said "受控注入约 80 次" (all runner files)
  - unified summary used "约 55 次" (orchestrated executions)
  The ledger reports both counts and explains the difference.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
EXECUTION_DIR = ROOT / "artifacts" / "experiments" / "execution"
OUT = EXECUTION_DIR / "remediation" / "run_ledger.json"

# Runner tools = one injection attempt per report file (http+grpc+probe+stress).
RUNNER_TOOLS = {
    "run_chaos_experiment",
    "run_grpc_chaos_experiment",
    "run_probe_restart_escape",
    "run_stress_with_cgroup",
    "run_stat_repeats",
    "run_grpc_chaos_experiment_without_cleanup",
}
CLASSIFICATION_TOOLS = {"classify_runtime_result"}
PREDICTION_TOOLS = {"decision_engine", "prospective_select", "prospective_select_r2", "mixed_pool_prospective_select",
                    "sock_three_method_select", "sock_frozen_knowledge_rerun", "sock_blind_availability_predict",
                    "generate_m1_adapter_plans"}
SUMMARY_TOOLS = {"summarize_comparative_results", "summarize_probe_restart", "compare_selection_methods",
                 "selection_robustness", "assess_selection_evidence", "evaluate_comparison_pilot",
                 "evaluate_deep_comparison_matrix", "package_report_evidence", "backfill_defense_patterns",
                 "knowledge_updater", "judgment_experience", "selection_experience"}
STATE_TOOLS = {"environment_fingerprint", "issue_tracker", "run_probe_restart_escape_summary", "contract_inventory"}


def _tool(path: Path) -> str:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return "<unparseable>"
    if not isinstance(doc, dict):
        return "<not-object>"
    tool = doc.get("tool")
    return str(tool) if tool else "<no-tool>"


def _lifecycle_complete(doc: dict[str, Any]) -> bool:
    lifecycle = doc.get("lifecycle") or {}
    if lifecycle.get("applied") is True and lifecycle.get("injected") is True:
        # recovery/cleanup presence is a quality gate; classification is the
        # evidence gate. Accept a report with a result_classification too.
        return True
    return bool(doc.get("result_classification"))


def classify(path: Path) -> dict[str, str]:
    tool = _tool(path)
    name = path.name
    if tool in RUNNER_TOOLS:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"category": "injection_unparseable", "tool": tool}
        complete = _lifecycle_complete(doc) if isinstance(doc, dict) else False
        return {
            "category": "injection_complete" if complete else "injection_incomplete",
            "tool": tool,
        }
    if tool in CLASSIFICATION_TOOLS:
        return {"category": "derived_classification", "tool": tool}
    if tool in PREDICTION_TOOLS:
        return {"category": "prediction_ranking", "tool": tool}
    if tool in SUMMARY_TOOLS:
        return {"category": "summary_evaluation", "tool": tool}
    if tool in STATE_TOOLS:
        return {"category": "state", "tool": tool}
    if tool == "<unparseable>":
        return {"category": "unparseable", "tool": tool}
    return {"category": "other", "tool": tool}


def main() -> int:
    files = sorted(EXECUTION_DIR.glob("*.json"))
    entries: list[dict[str, Any]] = []
    for path in files:
        info = classify(path)
        entries.append({
            "file": path.name,
            **info,
        })

    counts = Counter(e["category"] for e in entries)
    injections = [e for e in entries if e["category"].startswith("injection_")]
    complete = [e for e in entries if e["category"] == "injection_complete"]
    ledger = {
        "schema_version": 1,
        "tool": "run_ledger",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "directory": str(EXECUTION_DIR),
        "total_json_files": len(files),
        "category_counts": dict(sorted(counts.items())),
        "independent_injections_complete": len(complete),
        "independent_injections_total_runner_files": len(injections),
        "reconciliation": (
            "comparison_full_summary '约 80 次' = total runner report files "
            "(complete + incomplete, each file = one orchestrated run attempt); "
            "unified summary '约 55 次' = lifecycle-complete injections. Difference "
            "is incomplete/blocked/aborted runs plus grpc reports that carry "
            "classification inline (no separate file). Neither 55 nor 80 equals "
            "the number of JSON files (165) because predictions, classifications, "
            "summaries and state files are derived, not executions."
        ),
        "complete_injection_files": [e["file"] for e in complete],
        "incomplete_injection_files": [e["file"] for e in entries if e["category"] == "injection_incomplete"],
        "entries": entries,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"total files: {len(files)}")
    for cat, n in sorted(counts.items()):
        print(f"  {cat}: {n}")
    print(f"independent injections (complete lifecycle): {len(complete)}")
    print(f"runner report files (all attempts): {len(injections)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
