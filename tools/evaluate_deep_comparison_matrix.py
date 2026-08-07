"""Evaluate a deep comparison matrix for schema, shared-pool and runtime eligibility."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from generate_deep_comparison_matrix import validate_plan
from runtime_applicability_gate import check_mutation


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def evaluate(registry: dict[str, Any]) -> dict[str, Any]:
    expected_pool = list(registry.get("candidate_universe") or [])
    method_results: list[dict[str, Any]] = []
    pool_sets: dict[str, set[str]] = {}
    for method in registry.get("methods", []):
        method_id = str(method.get("id"))
        plans = method.get("plans") or []
        pool_sets[method_id] = {str((plan.get("execution") or {}).get("candidate_id")) for plan in plans}
        decisions: Counter[str] = Counter()
        plan_results: list[dict[str, Any]] = []
        for plan in plans:
            execution = plan.get("execution") or {}
            schema_errors = validate_plan(plan)
            gate = None
            if not schema_errors and execution.get("mutation_path"):
                gate = check_mutation(Path(execution["mutation_path"]))
                decision = str(gate.get("decision"))
            elif schema_errors:
                decision = "schema_invalid"
            elif execution.get("preclassified"):
                decision = str(execution["preclassified"])
            else:
                decision = "missing_mutation_path"
            decisions[decision] += 1
            plan_results.append({
                "plan_id": plan.get("plan_id"),
                "candidate_id": execution.get("candidate_id"),
                "rank": plan.get("rank"),
                "schema_errors": schema_errors,
                "gate": gate,
                "decision": decision,
            })
        method_results.append({
            "id": method_id,
            "name": method.get("name"),
            "status": method.get("status"),
            "blocker": method.get("blocker"),
            "candidate_count": len(plans),
            "candidate_pool_complete": len(plans) == int(registry.get("candidate_budget") or 0)
            and pool_sets[method_id].issubset(set(expected_pool)),
            "summary": dict(sorted(decisions.items())),
            "plans": plan_results,
        })
    available_pools = [pool for method_id, pool in pool_sets.items() if next((item.get("status") for item in registry.get("methods", []) if item.get("id") == method_id), "") == "available"]
    common_pool = bool(available_pools) and all(pool.issubset(set(expected_pool)) for pool in available_pools)
    return {
        "schema_version": 1,
        "tool": "evaluate_deep_comparison_matrix",
        "evaluated_at": now(),
        "replicate": registry.get("replicate"),
        "seed": registry.get("seed"),
        "candidate_budget": registry.get("candidate_budget"),
        "expected_candidate_count": len(expected_pool),
        "same_candidate_pool": bool(registry.get("same_candidate_pool")) and common_pool,
        "methods": method_results,
        "interpretation": (
            "This is a pre-injection eligibility audit. A ready_for_injection decision proves only "
            "that the candidate is executable in the current isolated lab; it is not an effectiveness score."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(json.loads(args.registry.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "same_candidate_pool": result["same_candidate_pool"], "summaries": {item["id"]: item["summary"] for item in result["methods"]}}, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
