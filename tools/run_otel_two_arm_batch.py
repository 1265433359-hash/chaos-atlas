"""Run the OTel discovery handoffs serially with resumable stop-on-failure."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from collections.abc import Iterable
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def report_path_for(runtime_root: Path, method: str, seed: int, hypothesis_id: str, replicate: int) -> Path:
    return Path(runtime_root) / "opentelemetry-demo" / f"seed-{seed}" / method.lower() / f"{hypothesis_id}-rep-{replicate}.json"


def _prior_roots(value: Path | Iterable[Path] | None) -> list[Path]:
    if value is None:
        return []
    if isinstance(value, Path):
        return [value]
    return [Path(item) for item in value]


def runtime_units(discovery_root: Path, runtime_root: Path, prior_runtime_root: Path | Iterable[Path] | None = None) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    prior_roots = _prior_roots(prior_runtime_root)
    for seed in (1001, 1002, 1003):
        for method in ("ChaosAtlas-full", "ChaosAtlas-ablation"):
            handoff = json.loads((Path(discovery_root) / f"seed-{seed}" / method.lower() / "handoff.json").read_text(encoding="utf-8"))
            if handoff.get("status") != "handoff_ready":
                raise ValueError(f"handoff is not ready: {method}/{seed}")
            for item in handoff.get("selected_hypotheses", [])[:4]:
                mutation = Path(discovery_root) / f"seed-{seed}" / method.lower() / "mutations" / f"{item['canonical_signature'][:12]}.yaml"
                for replicate in (1, 2):
                    current_report = report_path_for(runtime_root, method, seed, item["hypothesis_id"], replicate)
                    prior_report = next(
                        (
                            candidate
                            for root in prior_roots
                            if (candidate := report_path_for(root, method, seed, item["hypothesis_id"], replicate)).is_file()
                        ),
                        None,
                    )
                    units.append({"seed": seed, "method": method, "hypothesis_id": item["hypothesis_id"], "mutation": mutation, "replicate": replicate, "report": current_report, "prior_report": prior_report})
    return units


def run_batch(discovery_root: Path, runtime_root: Path, client: Path, progress_path: Path, prior_runtime_root: Path | Iterable[Path] | None = None) -> dict[str, Any]:
    units = runtime_units(discovery_root, runtime_root, prior_runtime_root)
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    stopped = False
    for index, unit in enumerate(units, 1):
        report = Path(unit["report"])
        prior_report = unit.get("prior_report")
        if prior_report and Path(prior_report).is_file():
            previous = json.loads(Path(prior_report).read_text(encoding="utf-8"))
            previous_status = previous.get("status")
            previous_injection = previous.get("injection") or {}
            previous_preflight = previous.get("preflight") or {}
            if previous_status == "completed":
                rows.append({"index": index, **{key: unit[key] for key in ("seed", "method", "hypothesis_id", "replicate")}, "status": "completed", "classification": (previous.get("observation") or {}).get("classification"), "skipped_existing": True, "source_report": str(prior_report).replace("\\", "/")})
                continue
            retryable_environment_block = previous_status == "failed" and not previous_injection.get("applied") and (previous_preflight.get("decision") == "blocked" or any("runtime applicability gate" in str(error) for error in previous.get("errors", [])))
            if not retryable_environment_block:
                rows.append({"index": index, **{key: unit[key] for key in ("seed", "method", "hypothesis_id", "replicate")}, "status": previous_status or "failed", "classification": (previous.get("observation") or {}).get("classification"), "skipped_existing": True, "source_report": str(prior_report).replace("\\", "/")})
                stopped = True
                break
        if report.is_file():
            value = json.loads(report.read_text(encoding="utf-8"))
            row = {"index": index, **{key: unit[key] for key in ("seed", "method", "hypothesis_id", "replicate")}, "status": value.get("status"), "classification": (value.get("observation") or {}).get("classification"), "skipped_existing": True}
            rows.append(row)
            if value.get("status") != "completed":
                stopped = True
                break
            continue
        report.parent.mkdir(parents=True, exist_ok=True)
        command = [PYTHON, str(ROOT / "tools/run_otel_two_arm.py"), str(unit["mutation"]), "--report", str(report), "--arm", unit["method"], "--seed", str(unit["seed"]), "--hypothesis-id", unit["hypothesis_id"], "--replicate", str(unit["replicate"]), "--client", str(client), "--baseline-count", "5", "--washout-seconds", "60", "--washout-successes", "10", "--washout-timeout", "180"]
        completed = subprocess.run(command, cwd=ROOT, check=False)
        value = json.loads(report.read_text(encoding="utf-8")) if report.exists() else {"status": "runner_no_report", "errors": [f"exit={completed.returncode}"]}
        row = {"index": index, **{key: unit[key] for key in ("seed", "method", "hypothesis_id", "replicate")}, "status": value.get("status"), "classification": (value.get("observation") or {}).get("classification"), "skipped_existing": False}
        rows.append(row)
        if value.get("status") != "completed":
            stopped = True
            break
        progress_path.write_text(json.dumps({"schema_version": "otel-two-arm-batch-progress-v1", "completed_units": len([item for item in rows if item["status"] == "completed"]), "total_units": len(units), "stopped": stopped, "rows": rows, "human_review": "pending", "knowledge_base_updated": False}, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    result = {"schema_version": "otel-two-arm-batch-v1", "status": "stopped_on_failure" if stopped else ("completed" if len(rows) == len(units) else "in_progress"), "completed_units": len([item for item in rows if item["status"] == "completed"]), "total_units": len(units), "rows": rows, "human_review": "pending", "knowledge_base_updated": False}
    progress_path.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--discovery-root", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--client", type=Path, default=Path("artifacts/opentelemetry-demo/otel_client.py"))
    parser.add_argument("--progress", type=Path, required=True)
    parser.add_argument("--prior-runtime-root", type=Path, action="append")
    args = parser.parse_args()
    result = run_batch(args.discovery_root, args.runtime_root, args.client, args.progress, args.prior_runtime_root)
    print(json.dumps({key: result[key] for key in ("status", "completed_units", "total_units")}, ensure_ascii=True))
    return 0 if result["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
