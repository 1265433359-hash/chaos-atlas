"""Run Online Boutique discovery handoffs serially with stop-on-failure."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
METHODS = ("ChaosAtlas-full", "ChaosAtlas-ablation")
SEEDS = (1001, 1002)


def report_path_for(runtime_root: Path, method: str, seed: int, hypothesis_id: str, replicate: int) -> Path:
    return Path(runtime_root) / f"seed-{seed}" / method.lower() / hypothesis_id / f"rep-{replicate}.json"


def runtime_units(
    discovery_root: Path,
    runtime_root: Path,
    *,
    methods: tuple[str, ...] = METHODS,
    seeds: Iterable[int] = SEEDS,
) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for seed in seeds:
        for method in methods:
            directory = Path(discovery_root) / f"seed-{seed}" / method.lower()
            handoff = json.loads((directory / "handoff.json").read_text(encoding="utf-8"))
            if handoff.get("status") != "handoff_ready":
                raise ValueError(f"handoff is not ready: {method}/{seed}")
            selected = handoff.get("selected_hypotheses", [])
            if len(selected) != 4:
                raise ValueError(f"handoff must contain exactly four selected hypotheses: {method}/{seed}")
            for item in selected:
                mutation = directory / "mutations" / f"{item['canonical_signature'][:12]}.yaml"
                if not mutation.is_file():
                    raise FileNotFoundError(f"compiled mutation is missing: {mutation}")
                for replicate in (1, 2):
                    units.append(
                        {
                            "seed": seed,
                            "method": method,
                            "hypothesis_id": item["hypothesis_id"],
                            "replicate": replicate,
                            "mutation": mutation,
                            "report": report_path_for(runtime_root, method, seed, item["hypothesis_id"], replicate),
                        }
                    )
    return units


def run_batch(
    discovery_root: Path,
    runtime_root: Path,
    progress_path: Path,
    *,
    methods: tuple[str, ...] = METHODS,
    seeds: Iterable[int] = SEEDS,
    client_script: Path = Path("artifacts/online-boutique/ob_client.py"),
) -> dict[str, Any]:
    units = runtime_units(discovery_root, runtime_root, methods=methods, seeds=seeds)
    rows: list[dict[str, Any]] = []
    stopped = False
    for index, unit in enumerate(units, 1):
        report = Path(unit["report"])
        if report.exists():
            value = json.loads(report.read_text(encoding="utf-8"))
            skipped = True
        else:
            report.parent.mkdir(parents=True, exist_ok=True)
            command = [
                PYTHON,
                str(ROOT / "tools/run_online_boutique_two_arm.py"),
                str(unit["mutation"]),
                "--report",
                str(report),
                "--arm",
                unit["method"],
                "--seed",
                str(unit["seed"]),
                "--hypothesis-id",
                unit["hypothesis_id"],
                "--replicate",
                str(unit["replicate"]),
                "--client-script",
                str(client_script),
                "--baseline-count",
                "5",
                "--washout-seconds",
                "60",
                "--washout-successes",
                "10",
                "--washout-timeout",
                "180",
            ]
            completed = subprocess.run(command, cwd=ROOT, check=False)
            value = json.loads(report.read_text(encoding="utf-8")) if report.exists() else {"status": "runner_no_report", "errors": [f"exit={completed.returncode}"]}
            skipped = False
        row = {"index": index, **{key: unit[key] for key in ("seed", "method", "hypothesis_id", "replicate")}, "status": value.get("status"), "classification": (value.get("observation") or {}).get("classification"), "skipped_existing": skipped}
        rows.append(row)
        stopped = value.get("status") != "completed"
        result = {"schema_version": "online-boutique-two-arm-batch-v1", "methods": list(methods), "seeds": list(seeds), "status": "stopped_on_failure" if stopped else ("completed" if len(rows) == len(units) else "in_progress"), "completed_units": sum(row["status"] == "completed" for row in rows), "total_units": len(units), "rows": rows, "human_review": "pending", "knowledge_base_updated": False}
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        progress_path.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        if stopped:
            break
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--discovery-root", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--progress", type=Path, required=True)
    parser.add_argument("--method", action="append")
    parser.add_argument("--seed", type=int, action="append")
    parser.add_argument("--client-script", type=Path, default=Path("artifacts/online-boutique/ob_client.py"))
    args = parser.parse_args()
    result = run_batch(
        args.discovery_root,
        args.runtime_root,
        args.progress,
        methods=tuple(args.method or METHODS),
        seeds=tuple(args.seed or SEEDS),
        client_script=args.client_script,
    )
    print(json.dumps({key: result[key] for key in ("status", "completed_units", "total_units")}, ensure_ascii=True))
    return 0 if result["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
