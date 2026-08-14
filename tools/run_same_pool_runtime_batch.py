"""Run deduplicated same-candidate-pool runtime units through project runners."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
ARM = "same-pool-fair"
SEED = 0

RUNNERS = {
    "online-boutique": {
        "script": "tools/run_online_boutique_two_arm.py",
        "extra": ["--client-script", "artifacts/online-boutique/ob_client.py"],
    },
    "opentelemetry-demo": {
        "script": "tools/run_otel_two_arm.py",
        "extra": ["--client", "artifacts/opentelemetry-demo/otel_client.py"],
    },
    "sock-shop": {
        "script": "tools/run_sock_shop_two_arm.py",
        "extra": [],
    },
}


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object expected: {path}")
    return value


def safe_path_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "__", value)


def report_path_for_unit(output_root: Path, unit: dict[str, Any]) -> Path:
    project = str(unit["project_id"])
    candidate = safe_path_component(str(unit["candidate_id"]))
    replicate = int(unit["replicate"])
    return Path(output_root) / project / candidate / f"rep-{replicate}.json"


def build_runner_command(unit: dict[str, Any], report: Path, *, python_executable: str = sys.executable) -> list[str]:
    project = str(unit["project_id"])
    if project not in RUNNERS:
        raise ValueError(f"unsupported project: {project}")
    runner = RUNNERS[project]
    command = [
        python_executable,
        runner["script"],
        str(unit["mutation_path"]),
        "--report",
        str(report),
        "--arm",
        ARM,
        "--seed",
        str(SEED),
        "--hypothesis-id",
        str(unit["candidate_id"]),
        "--replicate",
        str(int(unit["replicate"])),
    ]
    command.extend(runner["extra"])
    return command


def _default_run_command(command: list[str]) -> int:
    completed = subprocess.run(command, cwd=ROOT)
    return int(completed.returncode)


def _report_completed(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        return _load_json(path).get("status") == "completed"
    except (OSError, json.JSONDecodeError, ValueError):
        return False


def _load_units(plan_path: Path, project: str | None) -> list[dict[str, Any]]:
    plan = _load_json(plan_path)
    units = plan.get("units")
    if not isinstance(units, list):
        raise ValueError("runtime plan missing units list")
    selected = [unit for unit in units if project is None or unit.get("project_id") == project]
    if project is not None and project not in RUNNERS:
        raise ValueError(f"unsupported project: {project}")
    return selected


def run_batch(
    *,
    plan_path: Path,
    output_root: Path,
    project: str | None = None,
    limit: int | None = None,
    python_executable: str = sys.executable,
    run_command: Callable[[list[str]], int] = _default_run_command,
) -> dict[str, Any]:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    units = _load_units(Path(plan_path), project)
    if limit is not None:
        units = units[:limit]

    records: list[dict[str, Any]] = []
    status = "completed"
    for unit in units:
        report = report_path_for_unit(output_root, unit)
        command = build_runner_command(unit, report, python_executable=python_executable)
        record = {
            "project_id": unit["project_id"],
            "candidate_id": unit["candidate_id"],
            "replicate": unit["replicate"],
            "mutation_path": unit["mutation_path"],
            "report_path": str(report).replace("\\", "/"),
            "command": command,
        }
        if _report_completed(report):
            records.append({**record, "status": "skipped_completed", "return_code": 0})
            continue
        if report.exists():
            records.append({**record, "status": "existing_non_completed_report", "return_code": None})
            status = "stopped_on_failure"
            break

        report.parent.mkdir(parents=True, exist_ok=True)
        return_code = run_command(command)
        completed = _report_completed(report)
        unit_status = "completed" if return_code == 0 and completed else "failed"
        records.append({**record, "status": unit_status, "return_code": return_code})
        if unit_status != "completed":
            status = "stopped_on_failure"
            break

    result = {
        "schema_version": "chaosatlas-same-pool-runtime-batch-v1",
        "status": status,
        "plan_path": str(Path(plan_path)).replace("\\", "/"),
        "output_root": str(output_root).replace("\\", "/"),
        "project": project,
        "planned_units": len(units),
        "completed_units": sum(1 for item in records if item["status"] == "completed"),
        "skipped_units": sum(1 for item in records if item["status"] == "skipped_completed"),
        "failed_units": sum(1 for item in records if item["status"] in {"failed", "existing_non_completed_report"}),
        "records": records,
        "human_review": "pending",
        "knowledge_base_updated": False,
    }
    (output_root / "batch-progress.json").write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--project", choices=sorted(RUNNERS))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--python-executable", default=sys.executable)
    args = parser.parse_args()
    result = run_batch(
        plan_path=args.plan,
        output_root=args.output_root,
        project=args.project,
        limit=args.limit,
        python_executable=args.python_executable,
    )
    print(json.dumps({key: result[key] for key in ("status", "planned_units", "completed_units", "skipped_units", "failed_units")}, ensure_ascii=True))
    return 0 if result["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
