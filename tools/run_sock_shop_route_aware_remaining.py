"""Run the remaining route-aware Sock Shop families with resumable evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
ARM = "native-full"
SEED = 20260815

from tools.build_sock_shop_r5_evidence_selection import validate_runtime_report


def _resolve(path: str) -> Path:
    value = Path(path)
    if value.is_file():
        return value
    candidate = ROOT / value
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(path)


def build_units(
    selection_path: Path,
    gate_path: Path,
    report_dir: Path,
    *,
    kinds: set[str],
) -> list[dict[str, Any]]:
    selection_bytes = selection_path.read_bytes()
    selection_sha = hashlib.sha256(selection_bytes).hexdigest()
    selection = json.loads(selection_bytes.decode("utf-8"))
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    if gate.get("status") != "passed" or int((gate.get("summary") or {}).get("blocked") or 0) != 0:
        raise ValueError("route-aware selection gate is not fully passed")
    if gate.get("selection_manifest_sha256") != selection_sha:
        raise ValueError("route-aware selection gate does not match selection manifest")

    units: list[dict[str, Any]] = []
    for entry in selection.get("fresh_candidates") or []:
        if entry.get("kind") not in kinds:
            continue
        mutation = _resolve(str(entry.get("mutation_path") or ""))
        actual_sha = hashlib.sha256(mutation.read_bytes()).hexdigest()
        if actual_sha != entry.get("mutation_sha256"):
            raise ValueError(f"mutation SHA-256 mismatch: {mutation}")
        for replicate in (1, 2):
            units.append(
                {
                    "hypothesis_id": str(entry["hypothesis_id"]),
                    "kind": entry["kind"],
                    "replicate": replicate,
                    "mutation": mutation,
                    "mutation_sha256": actual_sha,
                    "report": report_dir / f"{entry['hypothesis_id']}-rep-{replicate}.json",
                }
            )
    return units


def _load_report(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "invalid_existing_report", "errors": [f"{type(exc).__name__}: {exc}"]}


def _validate_unit_report(path: Path, unit: dict[str, Any]) -> dict[str, Any]:
    try:
        value = _load_report(path)
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


def _write_progress(path: Path, selection_path: Path, gate_path: Path, units: list[dict[str, Any]], rows: list[dict[str, Any]], stopped: bool) -> dict[str, Any]:
    result = {
        "schema_version": "sock-shop-route-aware-remaining-execution-v1",
        "status": "stopped_on_failure" if stopped else ("completed" if len(rows) == len(units) else "in_progress"),
        "selection_manifest": str(selection_path).replace("\\", "/"),
        "selection_manifest_sha256": hashlib.sha256(selection_path.read_bytes()).hexdigest(),
        "gate_report": str(gate_path).replace("\\", "/"),
        "gate_report_sha256": hashlib.sha256(gate_path.read_bytes()).hexdigest(),
        "arm": ARM,
        "seed": SEED,
        "completed_units": sum(row["status"] == "completed" and row.get("evidence_valid") is True for row in rows),
        "total_units": len(units),
        "rows": rows,
        "human_review": "pending",
        "knowledge_base_updated": False,
    }
    path.write_text(json.dumps(result, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return result


def run_batch(selection_path: Path, gate_path: Path, runtime_root: Path, report_dir: Path, *, kinds: set[str]) -> dict[str, Any]:
    runtime_root.mkdir(parents=True, exist_ok=True)
    progress_path = runtime_root / "execution-progress.json"
    units = build_units(selection_path, gate_path, report_dir, kinds=kinds)
    rows: list[dict[str, Any]] = []
    stopped = False
    for sequence, unit in enumerate(units, 1):
        report_path = unit["report"]
        skipped = False
        if report_path.is_file():
            value = _load_report(report_path)
            validation = _validate_unit_report(report_path, unit) if value.get("status") == "completed" else {"valid": False, "reasons": ["not_completed"]}
            if validation["valid"]:
                skipped = True
            else:
                stopped = True
        else:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            command = [
                PYTHON,
                str(ROOT / "tools" / "run_sock_shop_two_arm.py"),
                str(unit["mutation"]),
                "--report", str(report_path),
                "--arm", ARM,
                "--seed", str(SEED),
                "--hypothesis-id", unit["hypothesis_id"],
                "--replicate", str(unit["replicate"]),
                "--recovery-timeout", "240",
            ]
            completed = subprocess.run(command, cwd=ROOT, check=False)
            value = _load_report(report_path) if report_path.is_file() else {"status": "runner_no_report", "errors": [f"exit={completed.returncode}"]}
            validation = _validate_unit_report(report_path, unit) if value.get("status") == "completed" else {"valid": False, "reasons": value.get("errors") or ["not_completed"]}
            stopped = value.get("status") != "completed" or completed.returncode != 0 or not validation["valid"]
        rows.append(
            {
                "sequence": sequence,
                "hypothesis_id": unit["hypothesis_id"],
                "kind": unit["kind"],
                "replicate": unit["replicate"],
                "mutation_path": str(unit["mutation"]).replace("\\", "/"),
                "mutation_sha256": unit["mutation_sha256"],
                "report_path": str(report_path).replace("\\", "/"),
                "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest() if report_path.is_file() else None,
                "arm": value.get("arm"),
                "status": value.get("status"),
                "evidence_valid": validation.get("valid"),
                "validation_reasons": validation.get("reasons") or [],
                "classification": (value.get("observation") or {}).get("classification"),
                "injected": (value.get("injection") or {}).get("injected"),
                "recovered": (value.get("recovery") or {}).get("recovered"),
                "cleanup_absent_confirmed": (value.get("cleanup") or {}).get("absent_confirmed"),
                "washout_stable": (value.get("washout") or {}).get("stable"),
                "skipped_existing": skipped,
            }
        )
        _write_progress(progress_path, selection_path, gate_path, units, rows, stopped)
        if stopped:
            break
    return _write_progress(progress_path, selection_path, gate_path, units, rows, stopped)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--kind", dest="kinds", action="append", required=True)
    args = parser.parse_args()
    result = run_batch(args.selection, args.gate, args.runtime_root, args.report_dir, kinds=set(args.kinds))
    print(json.dumps({key: result[key] for key in ("status", "completed_units", "total_units")}, ensure_ascii=True))
    return 0 if result["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
