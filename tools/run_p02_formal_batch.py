"""Plan or execute the isolated P02 teacher-Minikube formal runtime batch.

Execution is deliberately opt-in. The batch interleaves method outputs,
checks the read-only gate before every mutation, never overwrites evidence,
and stops immediately when a run fails.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from tools.p02_execution_gate import check
    from tools.run_p02_podchaos import cluster_identity
except ModuleNotFoundError:  # Direct execution from tools/.
    from p02_execution_gate import check
    from run_p02_podchaos import cluster_identity


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts/experiments/chaosatlas_10_projects/open_discovery_results/P02/seed-1001"
DEFAULT_OUTPUT = ROOT / "artifacts/experiments/chaosatlas_10_projects/runtime_results/P02/teacher-minikube-formal"
METHOD_OUTPUTS = (
    ("ChaosAtlas-KB-open", "chaosatlas-kb-open", "mutation-1"),
    ("ChaosAtlas-noKB-open", "chaosatlas-nokb-open", "mutation-1"),
    ("ChaosEater-adapter-open", "chaoseater-adapter-open", "mutation-1"),
    ("ChaosAtlas-KB-open", "chaosatlas-kb-open", "mutation-2"),
    ("ChaosAtlas-noKB-open", "chaosatlas-nokb-open", "mutation-2"),
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def schedule(replicates: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for replicate in range(1, replicates + 1):
        # Rotate each block so the same arm is not always first.
        offset = (replicate - 1) % len(METHOD_OUTPUTS)
        ordered = METHOD_OUTPUTS[offset:] + METHOD_OUTPUTS[:offset]
        for sequence, (arm, directory, mutation_id) in enumerate(ordered, start=1):
            mutation = SOURCE / directory / f"{mutation_id}.yaml"
            rows.append(
                {
                    "replicate": replicate,
                    "sequence_in_replicate": sequence,
                    "arm": arm,
                    "mutation_id": mutation_id,
                    "mutation": str(mutation.relative_to(ROOT)).replace("\\", "/"),
                }
            )
    return rows


def report_path(output: Path, row: dict[str, Any]) -> Path:
    return output / row["arm"] / row["mutation_id"] / f"rep-{row['replicate']}.json"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--baseline-count", type=int, default=5)
    parser.add_argument("--observe-count", type=int, default=10)
    parser.add_argument("--settle-seconds", type=float, default=15.0)
    parser.add_argument("--washout-seconds", type=float, default=60.0)
    parser.add_argument("--washout-stable-successes", type=int, default=10)
    parser.add_argument("--washout-timeout", type=float, default=180.0)
    parser.add_argument(
        "--capture-diagnostics",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="capture scoped logs, namespace events, and Zipkin traces for each run",
    )
    parser.add_argument("--chaos-namespace", default="chaos-testing")
    parser.add_argument("--execute", action="store_true", help="apply mutations; without this flag only print the plan")
    args = parser.parse_args()
    if args.replicates < 1:
        parser.error("--replicates must be positive")

    rows = schedule(args.replicates)
    missing = [row["mutation"] for row in rows if not (ROOT / row["mutation"]).is_file()]
    if missing:
        raise SystemExit(f"missing mutation inputs: {missing}")
    plan = {
        "schema_version": 2,
        "tool": "run_p02_formal_batch",
        "mode": "execute" if args.execute else "plan_only",
        "created_at": now(),
        "replicates": args.replicates,
        "run_count": len(rows),
        "output": str(args.output).replace("\\", "/"),
        "protocol": {
            "baseline_count": args.baseline_count,
            "observe_count": args.observe_count,
            "settle_seconds": args.settle_seconds,
            "washout_seconds": args.washout_seconds,
            "washout_stable_successes": args.washout_stable_successes,
            "washout_timeout": args.washout_timeout,
            "capture_diagnostics": args.capture_diagnostics,
        },
        "runs": rows,
    }
    if not args.execute:
        print(json.dumps(plan, indent=2, ensure_ascii=True))
        return 0

    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit("refusing to write into a non-empty formal output directory; choose a new --output")
    existing = [path for row in rows if (path := report_path(output, row)).exists()]
    if existing:
        raise SystemExit(f"refusing to overwrite {len(existing)} existing formal reports; choose a new --output")
    identity = cluster_identity()
    if not identity["context"]:
        raise SystemExit("kubectl current-context is empty")
    plan["cluster"] = identity
    plan["started_at"] = now()
    plan["status"] = "running"
    write_json(output / "batch-manifest.json", plan)

    completed = 0
    for row in rows:
        mutation = ROOT / row["mutation"]
        destination = report_path(output, row)
        gate = check(mutation, args.chaos_namespace)
        write_json(destination.with_suffix(".gate.json"), gate)
        if gate.get("decision") != "ready_for_injection":
            plan["status"] = "failed_closed"
            plan["failure"] = {"run": row, "reason": "execution_gate_blocked", "gate": gate}
            break
        current = cluster_identity()
        if current != identity:
            plan["status"] = "failed_closed"
            plan["failure"] = {"run": row, "reason": "cluster_identity_changed", "current": current}
            break
        destination.parent.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            str(ROOT / "tools/run_p02_podchaos.py"),
            str(mutation),
            "--report", str(destination),
            "--baseline-count", str(args.baseline_count),
            "--observe-count", str(args.observe_count),
            "--arm", row["arm"],
            "--mutation-id", row["mutation_id"],
            "--replicate", str(row["replicate"]),
            "--expected-context", identity["context"],
            "--washout-seconds", str(args.washout_seconds),
            "--washout-stable-successes", str(args.washout_stable_successes),
            "--washout-timeout", str(args.washout_timeout),
        ]
        if args.capture_diagnostics:
            command.append("--capture-diagnostics")
        process = subprocess.run(command, capture_output=True, text=True)
        destination.with_suffix(".stdout.txt").write_text(process.stdout, encoding="utf-8")
        destination.with_suffix(".stderr.txt").write_text(process.stderr, encoding="utf-8")
        if process.returncode != 0:
            plan["status"] = "failed_closed"
            plan["failure"] = {"run": row, "reason": "runner_failed", "return_code": process.returncode}
            break
        completed += 1
        plan["completed_runs"] = completed
        write_json(output / "batch-manifest.json", plan)
        if completed < len(rows):
            time.sleep(max(0.0, args.settle_seconds))
    else:
        plan["status"] = "completed"

    plan["completed_runs"] = completed
    plan["finished_at"] = now()
    write_json(output / "batch-manifest.json", plan)
    print(json.dumps(plan, indent=2, ensure_ascii=True))
    return 0 if plan["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
