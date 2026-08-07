"""Apply the common schema and runtime gate to a generated comparison pilot."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from generate_comparison_pilot import validate_plan
from runtime_applicability_gate import check_mutation


def evaluate_registry(registry: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": 1,
        "tool": "evaluate_comparison_pilot",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "replicate": registry.get("replicate"),
        "seed": registry.get("seed"),
        "methods": [],
    }
    for method in registry.get("methods", []):
        method_result = {
            "id": method.get("id"),
            "name": method.get("name"),
            "status": method.get("status"),
            "blocker": method.get("blocker"),
            "plans": [],
        }
        decisions: Counter[str] = Counter()
        for plan in method.get("plans", []):
            schema_errors = validate_plan(plan)
            execution = plan.get("execution") or {}
            preclassified = execution.get("preclassified")
            evaluation: dict[str, Any] = {
                "plan_id": plan.get("plan_id"),
                "project_id": plan.get("project_id"),
                "rank": plan.get("rank"),
                "candidate_id": execution.get("candidate_id"),
                "schema_errors": schema_errors,
                "gate": None,
            }
            if schema_errors:
                decision = "schema_invalid"
            elif preclassified:
                decision = str(preclassified)
            elif not execution.get("mutation_path"):
                decision = "missing_mutation_path"
            else:
                gate = check_mutation(Path(execution["mutation_path"]))
                evaluation["gate"] = gate
                decision = str(gate.get("decision"))
            evaluation["decision"] = decision
            decisions[decision] += 1
            method_result["plans"].append(evaluation)
        method_result["summary"] = dict(sorted(decisions.items()))
        result["methods"].append(method_result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    result = evaluate_registry(registry)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "summaries": {method["id"]: method["summary"] for method in result["methods"]},
    }, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
