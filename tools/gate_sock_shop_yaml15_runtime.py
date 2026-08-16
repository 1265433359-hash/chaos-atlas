"""Fail-closed server dry-run and applicability gate for YAML15 runtime families."""

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


METHOD = "chaosatlas-ablation-yaml15"
NAMESPACE = "chaosatlas-sock-shop"


def _resolve(path: str) -> Path:
    value = Path(path)
    if value.is_file():
        return value
    candidate = ROOT / value
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(path)


def _static_errors(path: Path, expected_sha256: str) -> tuple[list[str], str]:
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    errors = []
    if actual != expected_sha256:
        errors.append("mutation_sha256_mismatch")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        return errors + ["mutation_not_mapping"], actual
    metadata = document.get("metadata") or {}
    spec = document.get("spec") or {}
    effective_spec = spec.get("podChaos") if document.get("kind") == "Schedule" else spec
    selector = (effective_spec or {}).get("selector") or {}
    if metadata.get("namespace") != NAMESPACE:
        errors.append("mutation_namespace_mismatch")
    if selector.get("namespaces") != [NAMESPACE]:
        errors.append("selector_namespace_mismatch")
    return errors, actual


def gate_yaml15_runtime_plan(runtime_plan_path: Path, report_path: Path) -> dict[str, Any]:
    if report_path.exists():
        raise FileExistsError(f"refusing to overwrite existing YAML15 gate report: {report_path}")
    plan_bytes = runtime_plan_path.read_bytes()
    plan = json.loads(plan_bytes.decode("utf-8"))
    method = (plan.get("methods") or {}).get(METHOD)
    if not isinstance(method, dict):
        raise ValueError(f"runtime plan does not contain {METHOD}")

    results = []
    for candidate in method.get("candidates") or []:
        compile_gate = candidate.get("gate") or {}
        result = {
            "hypothesis_id": candidate.get("hypothesis_id"),
            "target_service": candidate.get("target_service"),
            "category": candidate.get("category"),
            "mutation_path": candidate.get("path"),
            "expected_sha256": candidate.get("sha256"),
            "actual_sha256": None,
            "compile_gate": compile_gate,
            "static_errors": [],
            "server_side_dry_run": {"status": "not_run"},
            "applicability": {"decision": "not_run"},
            "status": "compile_blocked" if compile_gate.get("status") != "passed" else "runtime_blocked",
        }
        if compile_gate.get("status") != "passed":
            results.append(result)
            continue
        try:
            path = _resolve(str(candidate.get("path") or ""))
            errors, actual = _static_errors(path, str(candidate.get("sha256") or ""))
            result["actual_sha256"] = actual
            result["static_errors"] = errors
        except Exception as exc:
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
        result["server_side_dry_run"] = {
            "status": "passed" if completed.returncode == 0 else "failed",
            "return_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        if completed.returncode != 0:
            results.append(result)
            continue

        applicability = check_mutation(path)
        result["applicability"] = applicability
        if applicability.get("decision") == "ready_for_injection":
            result["status"] = "runtime_ready"
        results.append(result)

    summary = {
        "generated_families": len(results),
        "compile_blocked": sum(item["status"] == "compile_blocked" for item in results),
        "server_dry_run_passed": sum(item["server_side_dry_run"].get("status") == "passed" for item in results),
        "ready_for_injection": sum(item["status"] == "runtime_ready" for item in results),
        "runtime_blocked": sum(item["status"] == "runtime_blocked" for item in results),
    }
    if summary["runtime_blocked"]:
        status = "blocked"
    elif summary["compile_blocked"]:
        status = "passed_with_exclusions"
    else:
        status = "passed"
    report = {
        "schema_version": "sock-shop-ablation-yaml15-runtime-gate-v1",
        "status": status,
        "method": METHOD,
        "namespace": NAMESPACE,
        "runtime_plan": str(runtime_plan_path),
        "runtime_plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
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
    parser.add_argument("--runtime-plan", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = gate_yaml15_runtime_plan(args.runtime_plan, args.report)
    print(json.dumps({"status": report["status"], "summary": report["summary"]}, ensure_ascii=False))
    return 0 if report["status"] in {"passed", "passed_with_exclusions"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
