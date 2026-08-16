"""Fail-closed static, server dry-run, and applicability gate for R5 selection."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.runtime_applicability_gate import check_mutation


NAMESPACE = "chaosatlas-sock-shop"


def _resolve(path: str) -> Path:
    value = Path(path)
    if value.is_file():
        return value
    candidate = ROOT / value
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(path)


def _static_errors(path: Path, expected_sha256: str) -> tuple[list[str], dict[str, Any] | None, str]:
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    errors = []
    if actual != expected_sha256:
        errors.append("mutation_sha256_mismatch")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        return errors + ["mutation_not_mapping"], None, actual
    metadata = document.get("metadata") or {}
    spec = document.get("spec") or {}
    nested = spec.get("podChaos") if document.get("kind") == "Schedule" else None
    selector = (nested or spec).get("selector") or {}
    if metadata.get("namespace") != NAMESPACE:
        errors.append("mutation_namespace_mismatch")
    if selector.get("namespaces") != [NAMESPACE]:
        errors.append("selector_namespace_mismatch")
    return errors, document, actual


def gate_selection(selection_manifest: Path, report_path: Path) -> dict[str, Any]:
    if report_path.exists():
        raise FileExistsError(f"refusing to overwrite existing gate report: {report_path}")
    manifest = json.loads(selection_manifest.read_text(encoding="utf-8"))
    entries = list((manifest.get("groups") or {}).get("overlap_high_confidence") or [])
    entries.extend((manifest.get("groups") or {}).get("ablation_only_random") or [])
    results = []
    for entry in entries:
        result = {
            "group": entry.get("group"),
            "mutation_path": entry.get("mutation_path"),
            "expected_sha256": entry.get("mutation_sha256"),
            "actual_sha256": None,
            "static_errors": [],
            "server_side_dry_run": {"status": "not_run"},
            "applicability": {"decision": "not_run"},
            "status": "blocked",
        }
        try:
            path = _resolve(str(entry.get("mutation_path") or ""))
            errors, _document, actual = _static_errors(path, str(entry.get("mutation_sha256") or ""))
            result["actual_sha256"] = actual
            result["static_errors"] = errors
        except Exception as exc:  # fail closed before kubectl
            result["static_errors"] = [f"static_gate_exception:{type(exc).__name__}:{exc}"]
            results.append(result)
            continue
        if errors:
            results.append(result)
            continue

        completed = subprocess.run(
            ["kubectl", "apply", "--server-side", "--dry-run=server", "-f", str(path)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        dry_run = {
            "status": "passed" if completed.returncode == 0 else "failed",
            "return_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        result["server_side_dry_run"] = dry_run
        if completed.returncode != 0:
            results.append(result)
            continue

        applicability = check_mutation(path)
        result["applicability"] = applicability
        if applicability.get("decision") == "ready_for_injection":
            result["status"] = "passed"
        results.append(result)

    summary = {
        "selected": len(results),
        "dry_run_passed": sum(item["server_side_dry_run"].get("status") == "passed" for item in results),
        "ready_for_injection": sum(item["status"] == "passed" for item in results),
        "blocked": sum(item["status"] != "passed" for item in results),
    }
    report = {
        "schema_version": "sock-shop-r5-selection-gate-v1",
        "status": "passed" if summary["blocked"] == 0 else "blocked",
        "selection_manifest": str(selection_manifest),
        "selection_manifest_sha256": hashlib.sha256(selection_manifest.read_bytes()).hexdigest(),
        "namespace": NAMESPACE,
        "summary": summary,
        "results": results,
        "human_review": "pending",
        "knowledge_base_updated": False,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = gate_selection(args.selection, args.report)
    print(json.dumps({"status": report["status"], "summary": report["summary"]}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
