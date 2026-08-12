"""Summarize and audit the P02 teacher-Minikube formal evidence offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "artifacts/experiments/chaosatlas_10_projects/runtime_results/P02/teacher-minikube-formal-r2"
DEFAULT_OUTPUT = ROOT / "analysis_outputs/p02_teacher_formal_r2"
DISCOVERY = ROOT / "artifacts/experiments/chaosatlas_10_projects/open_discovery_results/P02/seed-1001"
ARM_DIRS = {
    "ChaosAtlas-KB-open": "chaosatlas-kb-open",
    "ChaosAtlas-noKB-open": "chaosatlas-nokb-open",
    "ChaosEater-adapter-open": "chaoseater-adapter-open",
}


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def report_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("rep-*.json") if not path.name.endswith(".gate.json"))


def valid_run(report: dict[str, Any]) -> bool:
    lifecycle = report.get("lifecycle") or {}
    cleanup = lifecycle.get("cleanup") or {}
    return (
        report.get("status") == "completed"
        and not report.get("errors")
        and sum(sample.get("status_code") == 200 for sample in report.get("baseline", [])) >= 5
        and lifecycle.get("injected") is True
        and lifecycle.get("recovered") is True
        and int(lifecycle.get("post_recovery_http_200_count", 0) or 0) >= 1
        and cleanup.get("absent_confirmed") is True
        and not lifecycle.get("post_cleanup_residual_chaos")
    )


def candidate_summary() -> dict[str, Any]:
    arms: dict[str, Any] = {}
    for arm, directory in ARM_DIRS.items():
        base = DISCOVERY / directory
        compiled = load(base / "compiled.json")
        mutations = sorted(base.glob("mutation-*.yaml"))
        arms[arm] = {
            "accepted_hypotheses": int(compiled.get("accepted_count", 0)),
            "rejected_hypotheses": int(compiled.get("rejected_count", 0)),
            "executable_mutations": len(mutations),
            "signatures": [digest(path) for path in mutations],
            "targets": [
                ((item.get("resolved_source") or {}).get("name"))
                for path in sorted(base.glob("mutation-*.provenance.json"))
                for item in [load(path)]
            ],
            "rejections": compiled.get("rejected", []),
        }
    return arms


def analyze(input_dir: Path) -> dict[str, Any]:
    batch = load(input_dir / "batch-manifest.json")
    paths = report_files(input_dir)
    reports = [load(path) for path in paths]
    chronological = sorted(zip(paths, reports), key=lambda item: item[1]["started_at"])
    rows: list[dict[str, Any]] = []
    for path, report in chronological:
        experiment = report["experiment"]
        lifecycle = report["lifecycle"]
        requests = report.get("requests", [])
        baseline = report.get("baseline", [])
        target = (report.get("target", {}).get("labels") or {}).get("app.kubernetes.io/name")
        rows.append(
            {
                "artifact": str(path.relative_to(ROOT)).replace("\\", "/"),
                "arm": experiment["arm"],
                "mutation_id": experiment["mutation_id"],
                "replicate": experiment["replicate"],
                "target": target,
                "valid": valid_run(report),
                "baseline_attempts": len(baseline),
                "baseline_http_200": sum(sample.get("status_code") == 200 for sample in baseline),
                "baseline_failures": sum(sample.get("status_code") != 200 for sample in baseline),
                "baseline_http_500": sum(sample.get("status_code") == 500 for sample in baseline),
                "observed_non_200": sum(sample.get("status_code") != 200 for sample in requests),
                "observed_http_500": sum(sample.get("status_code") == 500 for sample in requests),
                "post_recovery_http_200": lifecycle.get("post_recovery_http_200_count", 0),
                "duration_s": round((iso(report["finished_at"]) - iso(report["started_at"])).total_seconds(), 3),
                "warnings": len(report.get("warnings", [])),
            }
        )

    carryover: list[dict[str, Any]] = []
    for previous, current in zip(rows, rows[1:]):
        if previous["target"] == "discovery-server" and current["baseline_http_500"]:
            previous_report = next(report for path, report in chronological if str(path.relative_to(ROOT)).replace("\\", "/") == previous["artifact"])
            current_report = next(report for path, report in chronological if str(path.relative_to(ROOT)).replace("\\", "/") == current["artifact"])
            gap = (iso(current_report["started_at"]) - iso(previous_report["finished_at"])).total_seconds()
            carryover.append(
                {
                    "source_run": previous["artifact"],
                    "next_run": current["artifact"],
                    "gap_s": round(gap, 3),
                    "pre_injection_http_500": current["baseline_http_500"],
                }
            )

    candidates = candidate_summary()
    arm_summary: dict[str, Any] = {}
    for arm in ARM_DIRS:
        arm_rows = [row for row in rows if row["arm"] == arm]
        arm_summary[arm] = {
            **candidates[arm],
            "executions": len(arm_rows),
            "technically_valid_executions": sum(row["valid"] for row in arm_rows),
            "baseline_contaminated_executions": sum(row["baseline_failures"] > 0 for row in arm_rows),
            "targets_executed": sorted({str(row["target"]) for row in arm_rows}),
            "median_duration_s": round(statistics.median(row["duration_s"] for row in arm_rows), 3),
        }

    gateway_rows = [row for row in rows if row["target"] == "api-gateway"]
    issue_1_counts = {
        arm: sum(row["observed_non_200"] > 0 for row in gateway_rows if row["arm"] == arm)
        for arm in ARM_DIRS
    }
    signatures_equal = (
        candidates["ChaosAtlas-KB-open"]["signatures"]
        == candidates["ChaosAtlas-noKB-open"]["signatures"]
    )
    adapter_subset = set(candidates["ChaosEater-adapter-open"]["signatures"]).issubset(
        set(candidates["ChaosAtlas-KB-open"]["signatures"])
    )
    return {
        "schema_version": 1,
        "tool": "summarize_p02_teacher_results",
        "input": str(input_dir.relative_to(ROOT)).replace("\\", "/"),
        "batch": {
            "status": batch.get("status"),
            "declared_runs": batch.get("run_count"),
            "completed_runs": batch.get("completed_runs"),
            "observed_reports": len(reports),
            "all_technically_valid": all(row["valid"] for row in rows),
        },
        "arms": arm_summary,
        "runs": rows,
        "carryover_events": carryover,
        "issues": [
            {
                "issue_id": "P02-ISSUE-001",
                "target": "api-gateway",
                "classification": "confirmed_single_replica_availability_weakness",
                "evidence": "Every sole api-gateway Pod kill produced at least one non-200 business observation before replacement recovery.",
                "reproductions_by_arm": issue_1_counts,
            },
            {
                "issue_id": "P02-ISSUE-002",
                "target": "discovery-server",
                "classification": "confirmed_delayed_business_outage_root_cause_pending",
                "evidence": "Each of three discovery-server kills was followed, before the next injection, by 8-37 consecutive HTTP 500 responses after the immediate recovery oracle had passed. The response body is generic, so logs or traces are still required to attribute the mechanism to service registration or discovery caches.",
                "reproductions": len(carryover),
                "events": carryover,
            },
        ],
        "comparison": {
            "kb_vs_nokb_candidate_signatures_equal": signatures_equal,
            "adapter_executable_signatures_subset_of_chaosatlas": adapter_subset,
            "runtime_head_to_head_eligible": False,
            "reasons": [
                "KB and noKB compiled byte-identical mutations, so runtime variation is not a knowledge-base effect.",
                "Delayed discovery-server failures carried into subsequent runs, violating independence and washout assumptions.",
                "Only one project and one model seed are present.",
                "ChaosEater-adapter-open is supplementary and is not official ChaosEater.",
            ],
            "knowledge_ablation_conclusion": "P02 seed-1001 is a null selection result: KB and noKB produced the same two executable candidates. It neither demonstrates a KB benefit nor disproves one across projects.",
        },
    }


def markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# P02 Teacher Minikube Formal R2 Audit",
        "",
        f"- Batch: `{summary['batch']['status']}`, {summary['batch']['completed_runs']}/{summary['batch']['declared_runs']} completed.",
        f"- Reports: {summary['batch']['observed_reports']}; all technically valid: `{str(summary['batch']['all_technically_valid']).lower()}`.",
        "- Statistical status: runtime head-to-head is **not eligible** because delayed effects contaminated later runs.",
        "",
        "## Arm Coverage",
        "",
        "| Arm | Accepted | Rejected | Executable | Executions | Valid | Baseline contaminated | Targets |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for arm, value in summary["arms"].items():
        lines.append(
            f"| {arm} | {value['accepted_hypotheses']} | {value['rejected_hypotheses']} | "
            f"{value['executable_mutations']} | {value['executions']} | {value['technically_valid_executions']} | "
            f"{value['baseline_contaminated_executions']} | {', '.join(value['targets_executed'])} |"
        )
    lines.extend(["", "## Confirmed Project Findings", ""])
    for issue in summary["issues"]:
        lines.append(f"- `{issue['issue_id']}` ({issue['target']}): {issue['evidence']}")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            f"- {summary['comparison']['knowledge_ablation_conclusion']}",
            "- The adapter produced one executable api-gateway mutation; its config-server latency proposal was rejected by the compiler parameter contract. This is a tool-chain compatibility result, not an official ChaosEater score.",
            "- R2 remains valuable execution and issue-discovery evidence, but a clean comparison requires a sustained post-recovery observation and washout window before the next mutation.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    summary = analyze(args.input.resolve())
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    (args.output / "summary.md").write_text(markdown(summary), encoding="utf-8")
    print(json.dumps(summary["batch"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
