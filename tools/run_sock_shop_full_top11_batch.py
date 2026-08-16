"""Execute only missing ready Full Top 11 candidates, serially and fail closed."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
ARM = "ChaosAtlas-full-top11"
SEED = 0

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.build_sock_shop_r5_evidence_selection import validate_runtime_report


def _resolve(path: str) -> Path:
    value = Path(path)
    if value.is_file():
        return value
    candidate = ROOT / value
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(path)


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", str(value or "unknown").lower()).strip("-")[:96]


def build_units(plan: dict[str, Any], runtime_root: Path) -> list[dict[str, Any]]:
    units = []
    for entry in plan.get("entries") or []:
        if entry.get("execution_status") != "fresh_required":
            continue
        mutation = _resolve(str(entry.get("source_path") or ""))
        actual_sha = hashlib.sha256(mutation.read_bytes()).hexdigest()
        if actual_sha != entry.get("mutation_sha256"):
            raise ValueError(f"mutation SHA-256 mismatch: {mutation}")
        rank = int(entry.get("rank") or 0)
        hypothesis_id = str(entry.get("hypothesis_id") or "")
        stem = f"rank-{rank:02d}-{_slug(hypothesis_id)}"
        for replicate in (1, 2):
            units.append(
                {
                    "rank": rank,
                    "hypothesis_id": hypothesis_id,
                    "replicate": replicate,
                    "mutation": mutation,
                    "mutation_sha256": actual_sha,
                    "report": runtime_root / "runtime_reports" / f"{stem}-rep-{replicate}.json",
                }
            )
    return units


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "invalid_existing_report", "errors": [f"{type(exc).__name__}: {exc}"]}


def _validate_unit_report(path: Path, unit: dict[str, Any]) -> dict[str, Any]:
    try:
        value = _load_json(path)
        evidence = validate_runtime_report(path)
    except Exception as exc:
        return {"valid": False, "reasons": [f"report_validation:{type(exc).__name__}:{exc}"]}
    reasons = list(evidence.get("reasons") or [])
    if value.get("arm") != ARM:
        reasons.append("arm_mismatch")
    if value.get("mutation_id") != unit["hypothesis_id"]:
        reasons.append("hypothesis_id_mismatch")
    if int(value.get("replicate") or 0) != int(unit["replicate"]):
        reasons.append("replicate_mismatch")
    if evidence.get("mutation_sha256") != unit["mutation_sha256"]:
        reasons.append("mutation_sha256_mismatch")
    evidence["valid"] = not reasons
    evidence["reasons"] = reasons
    return evidence


def _progress_result(plan_path: Path, units: list[dict[str, Any]], rows: list[dict[str, Any]], stopped: bool) -> dict[str, Any]:
    return {
        "schema_version": "sock-shop-full-top11-batch-v1",
        "status": "stopped_on_failure" if stopped else ("completed" if len(rows) == len(units) else "in_progress"),
        "execution_plan": str(plan_path),
        "execution_plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        "arm": ARM,
        "seed": SEED,
        "prior_runtime_roots": [],
        "completed_units": sum(row["status"] == "completed" and row["evidence_valid"] for row in rows),
        "total_units": len(units),
        "rows": rows,
        "human_review": "pending",
        "knowledge_base_updated": False,
    }


def run_batch(plan_path: Path, runtime_root: Path) -> dict[str, Any]:
    progress_path = runtime_root / "batch-progress.json"
    if runtime_root.exists() and any(runtime_root.iterdir()) and not progress_path.is_file():
        raise FileExistsError(f"refusing non-empty runtime directory without progress: {runtime_root}")
    runtime_root.mkdir(parents=True, exist_ok=True)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    units = build_units(plan, runtime_root)
    rows = []
    stopped = False
    result = _progress_result(plan_path, units, rows, stopped)

    for sequence, unit in enumerate(units, 1):
        report_path = unit["report"]
        if report_path.is_file():
            value = _load_json(report_path)
            skipped = value.get("status") == "completed"
            validation = _validate_unit_report(report_path, unit) if skipped else {"valid": False, "reasons": ["not_completed"]}
            if not skipped or not validation["valid"]:
                stopped = True
        else:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            command = [
                PYTHON,
                str(ROOT / "tools" / "run_sock_shop_two_arm.py"),
                str(unit["mutation"]),
                "--report",
                str(report_path),
                "--arm",
                ARM,
                "--seed",
                str(SEED),
                "--hypothesis-id",
                unit["hypothesis_id"],
                "--replicate",
                str(unit["replicate"]),
                "--recovery-timeout",
                "240",
            ]
            completed = subprocess.run(command, cwd=ROOT, check=False)
            value = _load_json(report_path) if report_path.is_file() else {
                "status": "runner_no_report",
                "errors": [f"exit={completed.returncode}"],
            }
            validation = _validate_unit_report(report_path, unit) if value.get("status") == "completed" else {
                "valid": False,
                "reasons": value.get("errors") or ["not_completed"],
            }
            skipped = False
            stopped = completed.returncode != 0 or not validation["valid"]

        rows.append(
            {
                "sequence": sequence,
                "rank": unit["rank"],
                "hypothesis_id": unit["hypothesis_id"],
                "replicate": unit["replicate"],
                "mutation_path": str(unit["mutation"]),
                "mutation_sha256": unit["mutation_sha256"],
                "report_path": str(report_path),
                "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest() if report_path.is_file() else None,
                "arm": value.get("arm"),
                "status": value.get("status"),
                "classification": (value.get("observation") or {}).get("classification"),
                "evidence_valid": validation.get("valid"),
                "validation_reasons": validation.get("reasons") or [],
                "skipped_existing": skipped,
            }
        )
        result = _progress_result(plan_path, units, rows, stopped)
        progress_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        if stopped:
            break
    if not units:
        progress_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    args = parser.parse_args()
    result = run_batch(args.plan, args.runtime_root)
    print(json.dumps({key: result[key] for key in ("status", "completed_units", "total_units")}, ensure_ascii=False))
    return 0 if result["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
