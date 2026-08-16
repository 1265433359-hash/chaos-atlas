"""Verify strict lifecycle and diagnostic integrity across runtime roots."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def verify_reports(roots: list[Path], *, expected: int) -> dict[str, Any]:
    reports: dict[tuple[Any, ...], tuple[Path, dict[str, Any]]] = {}
    for root in roots:
        for path in Path(root).rglob("*.json"):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(value, dict) or "replicate" not in value or "mutation_id" not in value:
                continue
            key = (value.get("project_id"), value.get("seed"), value.get("arm") or value.get("method_id"), value.get("mutation_id"), value.get("replicate"))
            previous = reports.get(key)
            if previous is None or (previous[1].get("status") != "completed" and value.get("status") == "completed"):
                reports[key] = (path, value)
    failures: list[dict[str, Any]] = []
    report_evidence: list[dict[str, Any]] = []
    classifications: dict[str, int] = {}
    methods: dict[str, int] = {}
    for key, (path, report) in reports.items():
        reasons: list[str] = []
        checks = (
            (report.get("status") == "completed", "status"),
            ((report.get("baseline") or {}).get("pass") is True, "baseline.pass"),
            ((report.get("injection") or {}).get("applied") is True, "injection.applied"),
            ((report.get("injection") or {}).get("injected") is True, "injection.injected"),
            ((report.get("recovery") or {}).get("recovered") is True, "recovery.recovered"),
            ((report.get("cleanup") or {}).get("absent_confirmed") is True, "cleanup.absent_confirmed"),
            ((report.get("cleanup") or {}).get("residual_resources") == [], "cleanup.residual_resources"),
            ((report.get("cleanup") or {}).get("global_scan_errors", []) == [], "cleanup.global_scan_errors"),
            ((report.get("washout") or {}).get("stable") is True, "washout.stable"),
            ((report.get("diagnostics") or {}).get("status") == "captured", "diagnostics.status"),
            (report.get("human_review") == "pending", "human_review"),
            (report.get("knowledge_base_updated") is False, "knowledge_base_updated"),
        )
        failed_lifecycle_checks = [name for ok, name in checks if not ok]
        reasons.extend(failed_lifecycle_checks)
        mutation = report.get("mutation") or {}
        mutation_path = Path(str(mutation.get("path", "")))
        if not mutation_path.is_file():
            reasons.append(f"mutation_missing:{mutation_path}")
        elif hashlib.sha256(mutation_path.read_bytes()).hexdigest() != mutation.get("sha256"):
            reasons.append(f"mutation_sha256:{mutation_path}")
        diagnostic_files = (report.get("diagnostics") or {}).get("files") or []
        if not diagnostic_files:
            reasons.append("diagnostics.files")
        for item in diagnostic_files:
            diagnostic_path = Path(str(item.get("path", "")))
            if not diagnostic_path.is_file():
                reasons.append(f"diagnostic_missing:{diagnostic_path}")
            elif hashlib.sha256(diagnostic_path.read_bytes()).hexdigest() != item.get("sha256"):
                reasons.append(f"diagnostic_sha256:{diagnostic_path}")
        if reasons:
            failures.append({"report": str(path).replace("\\", "/"), "reasons": reasons})
        classification = str((report.get("observation") or {}).get("classification", "missing"))
        classifications[classification] = classifications.get(classification, 0) + 1
        method = str(report.get("arm") or report.get("method_id"))
        methods[method] = methods.get(method, 0) + 1
        report_evidence.append(
            {
                "path": str(path).replace("\\", "/"),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "project_id": report.get("project_id"),
                "seed": report.get("seed"),
                "method": method,
                "mutation_id": report.get("mutation_id"),
                "replicate": report.get("replicate"),
                "classification": classification,
                "lifecycle_valid": not failed_lifecycle_checks,
            }
        )
    if len(reports) != expected:
        failures.append({"report": "<aggregate>", "reasons": [f"expected_reports={expected},actual={len(reports)}"]})
    return {"schema_version": "two-arm-runtime-verification-v1", "status": "passed" if not failures else "failed", "reports": len(reports), "expected": expected, "methods": methods, "classifications": classifications, "report_evidence": sorted(report_evidence, key=lambda item: item["path"]), "failures": failures, "human_review": "pending", "knowledge_base_updated": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, action="append", required=True)
    parser.add_argument("--expected", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify_reports(args.root, expected=args.expected)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("status", "reports", "expected", "classifications")}))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
