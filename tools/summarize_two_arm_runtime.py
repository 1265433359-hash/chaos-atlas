"""Summarize verified two-arm observations without assigning mechanisms."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _handoffs(discovery_root: Path) -> dict[tuple[int, str, str], dict[str, Any]]:
    result: dict[tuple[int, str, str], dict[str, Any]] = {}
    for path in Path(discovery_root).rglob("handoff.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        seed = int(value.get("seed"))
        method = str(value.get("method_id"))
        for item in value.get("selected_hypotheses", []):
            result[(seed, method, str(item.get("hypothesis_id")))] = item
    return result


def _reports(runtime_roots: list[Path]) -> dict[tuple[Any, ...], dict[str, Any]]:
    result: dict[tuple[Any, ...], dict[str, Any]] = {}
    for root in runtime_roots:
        for path in Path(root).rglob("*.json"):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(value, dict) or value.get("status") != "completed" or "replicate" not in value or "mutation_id" not in value:
                continue
            key = (value.get("project_id"), value.get("seed"), value.get("arm"), value.get("mutation_id"), value.get("replicate"))
            result.setdefault(key, value)
    return result


def summarize(discovery_root: Path, runtime_roots: list[Path]) -> dict[str, Any]:
    hypotheses = _handoffs(discovery_root)
    reports = _reports(runtime_roots)
    groups: dict[tuple[int, str, str], list[dict[str, Any]]] = {}
    for report in reports.values():
        key = (int(report.get("seed")), str(report.get("arm")), str(report.get("mutation_id")))
        groups.setdefault(key, []).append(report)
    rows: list[dict[str, Any]] = []
    for key, values in sorted(groups.items()):
        intent = hypotheses.get(key, {})
        weakness = sum((item.get("observation") or {}).get("classification") == "weakness_observed" for item in values)
        no_impact = sum((item.get("observation") or {}).get("classification") == "no_business_impact_observed" for item in values)
        distinct = {str((item.get("observation") or {}).get("classification")) for item in values}
        rows.append({
            "seed": key[0],
            "arm": key[1],
            "hypothesis_id": key[2],
            "target": intent.get("target"),
            "target_kind": intent.get("target_kind"),
            "fault_family": intent.get("fault_family"),
            "parameters": intent.get("parameters"),
            "repetitions": len(values),
            "weakness_repetitions": weakness,
            "no_business_impact_repetitions": no_impact,
            "consistency": "consistent" if len(distinct) == 1 else "mixed",
        })
    methods: dict[str, dict[str, int]] = {}
    for row in rows:
        method = methods.setdefault(row["arm"], {"reports": 0, "weakness_observed": 0, "no_business_impact_observed": 0})
        method["reports"] += row["repetitions"]
        method["weakness_observed"] += row["weakness_repetitions"]
        method["no_business_impact_observed"] += row["no_business_impact_repetitions"]
    return {
        "schema_version": "two-arm-runtime-summary-v1",
        "reports": len(reports),
        "methods": methods,
        "hypotheses": rows,
        "claim_boundary": "Observed business-oracle outcomes only; no internal retry, cache, discovery, registration, or other mechanism is inferred.",
        "human_review": "pending",
        "knowledge_base_updated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--discovery-root", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.discovery_root, args.runtime_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"reports": result["reports"], "methods": result["methods"]}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
