"""Execute the frozen R5 Ablation selection serially with stop-on-failure."""

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
ARM = "ChaosAtlas-ablation-r5"
SEED = 0


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


def build_units(selection_path: Path, gate_path: Path, runtime_root: Path) -> list[dict[str, Any]]:
    selection_bytes = selection_path.read_bytes()
    selection_sha = hashlib.sha256(selection_bytes).hexdigest()
    selection = json.loads(selection_bytes.decode("utf-8"))
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    if gate.get("status") != "passed" or int((gate.get("summary") or {}).get("blocked") or 0) != 0:
        raise ValueError("selection gate is not fully passed")
    if gate.get("selection_manifest_sha256") != selection_sha:
        raise ValueError("selection gate does not match the selection manifest SHA-256")

    entries = list((selection.get("groups") or {}).get("overlap_high_confidence") or [])
    entries.extend((selection.get("groups") or {}).get("ablation_only_random") or [])
    if int((gate.get("summary") or {}).get("ready_for_injection") or 0) != len(entries):
        raise ValueError("selection gate ready count does not match selected runtime entries")

    units = []
    for index, entry in enumerate(entries, 1):
        mutation = _resolve(str(entry.get("mutation_path") or ""))
        actual_sha = hashlib.sha256(mutation.read_bytes()).hexdigest()
        if actual_sha != entry.get("mutation_sha256"):
            raise ValueError(f"selected mutation SHA-256 mismatch: {mutation}")
        hypothesis_id = entry.get("ablation_hypothesis_id") or entry.get("full_hypothesis_id")
        unit_id = f"{index:02d}-{_slug(entry.get('group'))}-{_slug(hypothesis_id)}"
        for replicate in (1, 2):
            units.append(
                {
                    "index": index,
                    "unit_id": unit_id,
                    "group": entry.get("group"),
                    "hypothesis_id": str(hypothesis_id),
                    "replicate": replicate,
                    "mutation": mutation,
                    "mutation_sha256": actual_sha,
                    "report": runtime_root / "runtime_reports" / f"{unit_id}-rep-{replicate}.json",
                    "arm": ARM,
                    "seed": SEED,
                }
            )
    return units


def _load_report(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "invalid_existing_report", "errors": [f"{type(exc).__name__}: {exc}"]}


def run_batch(selection_path: Path, gate_path: Path, runtime_root: Path) -> dict[str, Any]:
    progress_path = runtime_root / "batch-progress.json"
    if runtime_root.exists() and any(runtime_root.iterdir()) and not progress_path.is_file():
        raise FileExistsError(f"refusing non-empty runtime directory without resumable progress: {runtime_root}")
    runtime_root.mkdir(parents=True, exist_ok=True)
    units = build_units(selection_path, gate_path, runtime_root)
    rows = []
    stopped = False
    for sequence, unit in enumerate(units, 1):
        report_path = unit["report"]
        if report_path.is_file():
            value = _load_report(report_path)
            skipped = value.get("status") == "completed"
            if not skipped:
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
                unit["arm"],
                "--seed",
                str(unit["seed"]),
                "--hypothesis-id",
                unit["hypothesis_id"],
                "--replicate",
                str(unit["replicate"]),
                "--recovery-timeout",
                "240",
            ]
            completed = subprocess.run(command, cwd=ROOT, check=False)
            value = _load_report(report_path) if report_path.is_file() else {
                "status": "runner_no_report",
                "errors": [f"exit={completed.returncode}"],
            }
            skipped = False
            stopped = value.get("status") != "completed" or completed.returncode != 0
        rows.append(
            {
                "sequence": sequence,
                "unit_id": unit["unit_id"],
                "group": unit["group"],
                "hypothesis_id": unit["hypothesis_id"],
                "replicate": unit["replicate"],
                "mutation_path": str(unit["mutation"]),
                "mutation_sha256": unit["mutation_sha256"],
                "report_path": str(report_path),
                "status": value.get("status"),
                "classification": (value.get("observation") or {}).get("classification"),
                "skipped_existing": skipped,
            }
        )
        result = {
            "schema_version": "sock-shop-r5-selection-batch-v1",
            "status": "stopped_on_failure" if stopped else ("completed" if len(rows) == len(units) else "in_progress"),
            "selection_manifest": str(selection_path),
            "selection_manifest_sha256": hashlib.sha256(selection_path.read_bytes()).hexdigest(),
            "gate_report": str(gate_path),
            "gate_report_sha256": hashlib.sha256(gate_path.read_bytes()).hexdigest(),
            "arm": ARM,
            "seed": SEED,
            "prior_runtime_roots": [],
            "completed_units": sum(row["status"] == "completed" for row in rows),
            "total_units": len(units),
            "rows": rows,
            "human_review": "pending",
            "knowledge_base_updated": False,
        }
        progress_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        if stopped:
            break
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    args = parser.parse_args()
    result = run_batch(args.selection, args.gate, args.runtime_root)
    print(json.dumps({key: result[key] for key in ("status", "completed_units", "total_units")}, ensure_ascii=False))
    return 0 if result["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
