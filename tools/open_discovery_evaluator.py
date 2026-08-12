"""Post-hoc evaluator for the open-discovery track.

The evaluator consumes compiled intents and an independent oracle ledger.  It
does not infer a verdict from model prose, and it reports project-level rows so
that hypotheses are not treated as independent statistical samples.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

try:
    from tools.feedback_protocol import classify_outcome
except ModuleNotFoundError:  # direct `python tools/script.py` invocation
    from feedback_protocol import classify_outcome


def evaluate_compiled(compiled: dict[str, Any], oracle: dict[str, dict[str, Any]], known_signatures: set[str] | None = None) -> dict[str, Any]:
    known_signatures = known_signatures or set()
    rows: list[dict[str, Any]] = []
    for item in compiled.get("accepted", []):
        signature = str(item.get("canonical_signature", ""))
        evidence = oracle.get(signature, {})
        merged = dict(evidence)
        merged.update({"project_id": item.get("project_id"), "project_commit": item.get("project_commit", ""), "canonical_signature": signature, "target": item.get("target"), "target_kind": item.get("target_kind"), "fault_family": item.get("fault_family")})
        classification = classify_outcome(merged)
        rows.append({
            "project_id": item.get("project_id"),
            "canonical_signature": signature,
            "novelty": "known_candidate" if signature in known_signatures else item.get("novelty", "novel_candidate"),
            "classification": classification,
            "evidence": evidence,
            "target": item.get("target"),
            "fault_family": item.get("fault_family"),
            "issue_id": evidence.get("issue_id") or signature,
        })
    valid = len(rows)
    confirmed = [row for row in rows if row["classification"] == "confirmed_weakness"]
    protected = [row for row in rows if row["classification"] == "protected"]
    known_issues = [row for row in confirmed if row["novelty"] == "known_candidate"]
    novel_issues = [row for row in confirmed if row["novelty"] == "novel_candidate"]
    evidence_complete = [row for row in rows if row["classification"] == "confirmed_weakness" or row["classification"] == "protected"]
    return {
        "schema_version": "1.0",
        "project_id": compiled.get("accepted", [{}])[0].get("project_id") if compiled.get("accepted") else compiled.get("project_id"),
        "valid_hypotheses": valid,
        "confirmed_weaknesses": len(confirmed),
        "unique_issue_yield": len({row["issue_id"] for row in confirmed}),
        "novel_issue_yield": len({row["issue_id"] for row in novel_issues}),
        "known_pattern_coverage": len({row["canonical_signature"] for row in known_issues}),
        "protected_waste": len(protected) / valid if valid else 0.0,
        "evidence_completeness": len(evidence_complete) / valid if valid else 0.0,
        "method_invalid": int(compiled.get("rejected_count", 0)) or int(compiled.get("status") == "method_invalid"),
        "rows": rows,
    }


def summarize_projects(reports: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for report in reports:
        grouped[(str(report.get("project_id", "")), str(report.get("arm", "")))].append(report)
    output: list[dict[str, Any]] = []
    for (project_id, arm), items in sorted(grouped.items()):
        total = sum(int(item.get("valid_hypotheses", 0)) for item in items)
        output.append({
            "project_id": project_id,
            "arm": arm,
            "seeds": len(items),
            "valid_hypotheses": total,
            "confirmed_weaknesses": sum(int(item.get("confirmed_weaknesses", 0)) for item in items),
            "unique_issue_yield": sum(int(item.get("unique_issue_yield", 0)) for item in items),
            "novel_issue_yield": sum(int(item.get("novel_issue_yield", 0)) for item in items),
            "protected_waste": sum(float(item.get("protected_waste", 0)) for item in items) / len(items),
            "evidence_completeness": sum(float(item.get("evidence_completeness", 0)) for item in items) / len(items),
            "unit_of_analysis": "project_seed_group; not individual hypothesis",
        })
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiled", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--known-signatures", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    compiled = json.loads(args.compiled.read_text(encoding="utf-8"))
    oracle = json.loads(args.oracle.read_text(encoding="utf-8"))
    known = set(json.loads(args.known_signatures.read_text(encoding="utf-8"))) if args.known_signatures else set()
    report = evaluate_compiled(compiled, oracle, known)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"project_id": report.get("project_id"), "confirmed_weaknesses": report["confirmed_weaknesses"], "novel_issue_yield": report["novel_issue_yield"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
