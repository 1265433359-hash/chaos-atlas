"""Run bounded statistical repetitions for the wrap-up of project 1.

Reuses the existing runner + real mutations; validates each run and writes
a machine-readable summary to stat_repeat/summary.json.
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAT = ROOT / "artifacts/train-ticket/runtime/stat_repeat"

EXPERIMENTS = [
    # (id, mutation, service, port, path, repeats)
    ("station-100ms", "network-station/station-network-delay-candidate-r1.yaml", "ts-station-service", 12345, "/api/v1/stationservice/stations/id/shanghai", 2),
    ("station-500ms", "network-station/station-network-delay-candidate-r2.yaml", "ts-station-service", 12345, "/api/v1/stationservice/stations/id/shanghai", 3),
    ("basic-cpu-r1", "stress-basic/basic-stress-cpu-candidate-r1.yaml", "ts-basic-service", 15680, "/api/v1/basicservice/basic/shanghai", 3),
]


def run_one(mutation: Path, report: Path, service: str, port: int, path: str) -> dict:
    cmd = [
        sys.executable, str(ROOT / "tools/run_chaos_experiment.py"),
        str(mutation),
        "--report", str(report),
        "--service", service,
        "--remote-port", str(port),
        "--local-port", str(18000 + port),
        "--request-path", path,
        "--request-count", "10",
        "--request-interval", "0.5",
        "--warmup-count", "3",
        "--warmup-interval", "0.5",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if not report.exists():
        return {"error": f"no report written; rc={proc.returncode}; stderr={proc.stderr[-400:]}"}
    data = json.loads(report.read_text(encoding="utf-8"))
    return data


def summarize(run: dict) -> dict:
    reqs = run.get("requests", [])
    lat = [x.get("latency_ms") for x in reqs if x.get("latency_ms") is not None]
    statuses = sorted({x.get("status_code") for x in reqs})
    return {
        "classification": run.get("result_classification"),
        "injected": bool(run.get("lifecycle", {}).get("injected")),
        "recovered": bool(run.get("lifecycle", {}).get("recovered")),
        "cleanup_absent": bool((run.get("lifecycle", {}).get("cleanup") or {}).get("resource_absent_after_delete")),
        "request_count": len(reqs),
        "statuses": statuses,
        "median_latency_ms": round(statistics.median(lat), 3) if lat else None,
        "p95_latency_ms": round(sorted(lat)[int(len(lat) * 0.95) - 1], 3) if len(lat) >= 20 else (
            round(sorted(lat)[-1], 3) if lat else None),
        "errors": run.get("errors", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="run only this experiment id")
    args = parser.parse_args()
    STAT.mkdir(parents=True, exist_ok=True)
    results: dict[str, list[dict]] = {}
    for exp_id, mut_rel, service, port, path, repeats in EXPERIMENTS:
        if args.only and args.only != exp_id:
            continue
        results[exp_id] = []
        for rep in range(1, repeats + 1):
            report = STAT / f"{exp_id}-rep{rep}.json"
            if report.exists():
                print(f"[skip] {exp_id} rep{rep} already exists")
                data = json.loads(report.read_text(encoding="utf-8"))
            else:
                print(f"[run ] {exp_id} rep{rep} ...", flush=True)
                data = run_one(ROOT / "artifacts/train-ticket/runtime/generated_mutations" / mut_rel,
                               report, service, port, path)
                if "error" in data:
                    print(f"  ERROR: {data['error']}", flush=True)
                    results[exp_id].append(data)
                    continue
            results[exp_id].append(summarize(data))
            s = results[exp_id][-1]
            print(f"  -> {s.get('classification')} median={s.get('median_latency_ms')} "
                  f"injected={s.get('injected')} cleanup={s.get('cleanup_absent')}", flush=True)
    STAT.joinpath("summary.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("summary written:", STAT / "summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
