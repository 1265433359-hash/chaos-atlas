from __future__ import annotations

import json
from pathlib import Path

from tools.run_same_pool_runtime_batch import (
    build_runner_command,
    report_path_for_unit,
    run_batch,
)


def _write_plan(path: Path) -> None:
    payload = {
        "schema_version": "chaosatlas-same-pool-runtime-plan-v1",
        "total_unique_candidates": 2,
        "total_runtime_units": 3,
        "candidates": [],
        "units": [
            {
                "project_id": "online-boutique",
                "candidate_id": "online-boutique:checkoutservice:pod_kill:abc123",
                "replicate": 1,
                "mutation_path": "mutations/ob.yaml",
            },
            {
                "project_id": "online-boutique",
                "candidate_id": "online-boutique:checkoutservice:pod_kill:abc123",
                "replicate": 2,
                "mutation_path": "mutations/ob.yaml",
            },
            {
                "project_id": "opentelemetry-demo",
                "candidate_id": "opentelemetry-demo:cart:network_delay:def456",
                "replicate": 1,
                "mutation_path": "mutations/otel.yaml",
            },
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_report_path_uses_windows_safe_candidate_directory(tmp_path: Path) -> None:
    unit = {
        "project_id": "online-boutique",
        "candidate_id": "online-boutique:checkoutservice:pod_kill:abc123",
        "replicate": 2,
    }

    report = report_path_for_unit(tmp_path, unit)

    assert report == tmp_path / "online-boutique" / "online-boutique__checkoutservice__pod_kill__abc123" / "rep-2.json"
    assert ":" not in str(report.relative_to(tmp_path))


def test_build_runner_command_selects_project_specific_runner(tmp_path: Path) -> None:
    unit = {
        "project_id": "opentelemetry-demo",
        "candidate_id": "opentelemetry-demo:cart:network_delay:def456",
        "replicate": 1,
        "mutation_path": "mutations/otel.yaml",
    }
    report = tmp_path / "rep-1.json"

    command = build_runner_command(unit, report, python_executable="python")

    assert command[:3] == ["python", "tools/run_otel_two_arm.py", "mutations/otel.yaml"]
    assert command[command.index("--report") + 1] == str(report)
    assert command[command.index("--arm") + 1] == "same-pool-fair"
    assert command[command.index("--seed") + 1] == "0"
    assert command[command.index("--hypothesis-id") + 1] == unit["candidate_id"]
    assert command[command.index("--replicate") + 1] == "1"
    assert command[command.index("--client") + 1] == "artifacts/opentelemetry-demo/otel_client.py"


def test_run_batch_skips_completed_reports_and_records_progress(tmp_path: Path) -> None:
    plan = tmp_path / "runtime-plan.json"
    _write_plan(plan)
    output = tmp_path / "runtime-results"
    completed = output / "online-boutique" / "online-boutique__checkoutservice__pod_kill__abc123" / "rep-1.json"
    completed.parent.mkdir(parents=True, exist_ok=True)
    completed.write_text(json.dumps({"status": "completed"}), encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(command: list[str]) -> int:
        calls.append(command)
        report = Path(command[command.index("--report") + 1])
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps({"status": "completed"}), encoding="utf-8")
        return 0

    result = run_batch(plan_path=plan, output_root=output, project="online-boutique", python_executable="python", run_command=fake_run)

    assert result["status"] == "completed"
    assert result["skipped_units"] == 1
    assert result["completed_units"] == 1
    assert len(calls) == 1
    progress = json.loads((output / "batch-progress.json").read_text(encoding="utf-8"))
    assert [record["status"] for record in progress["records"]] == ["skipped_completed", "completed"]
