"""Run the Dify Docker Compose E2E fault matrix through ChaosAtlas contracts."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    _repo_root_path = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(_repo_root_path))
    sys.path.insert(0, str(_repo_root_path / "src"))

from chaosatlas.workspace import default_run_output
from tools.docker_compose_adapter import DockerComposeAdapter, redact_text
from tools.project_onboarding import validate_project_profile


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _repo_root(profile_path: Path) -> Path:
    resolved = profile_path.resolve()
    for parent in resolved.parents:
        if (parent / "AGENTS.md").is_file():
            return parent
    return resolved.parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=Path("projects/dify-docker/profile.json"))
    parser.add_argument("--output", type=Path, default=default_run_output("dify-docker-e2e"))
    parser.add_argument("--compose-dir", type=Path, help="external Dify Compose directory required for live execution")
    parser.add_argument("--service", action="append", dest="services", choices=("api", "nginx", "worker", "redis", "sandbox", "plugin_daemon"))
    parser.add_argument("--approve-live", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    args = parser.parse_args(argv)
    try:
        profile = json.loads(args.profile.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "method_invalid", "errors": [str(exc)]}, ensure_ascii=True))
        return 2
    checked = validate_project_profile(profile)
    if not checked["valid"]:
        print(json.dumps({"status": "method_invalid", "errors": checked["errors"]}, ensure_ascii=True))
        return 2
    runtime = profile["runtime_contract"]
    repo = _repo_root(args.profile)
    live_compose_root = args.compose_dir or os.environ.get("CHAOSATLAS_DIFY_COMPOSE_ROOT")
    if args.approve_live and not live_compose_root:
        print(json.dumps({"status": "environment_blocked", "errors": ["live execution requires --compose-dir or CHAOSATLAS_DIFY_COMPOSE_ROOT"]}, ensure_ascii=True))
        return 3
    compose_dir = Path(live_compose_root).expanduser().resolve() if live_compose_root else (repo / runtime["compose_directory"]).resolve()
    allowed = set(runtime["allowed_services"])
    services = args.services or list(runtime["allowed_services"])
    if any(service not in allowed for service in services):
        print(json.dumps({"status": "method_invalid", "errors": ["requested service is outside profile allowlist"]}, ensure_ascii=True))
        return 2
    adapter = DockerComposeAdapter(
        compose_dir=compose_dir,
        compose_file=runtime["compose_file"],
        project_name=runtime.get("project_name"),
        allowed_services=allowed,
        expected_compose_sha256=(runtime.get("live_compose_sha256") if args.approve_live else runtime.get("compose_sha256")),
    )
    args.output.mkdir(parents=True, exist_ok=True)
    preflight = adapter.preflight()
    _write(args.output / "preflight.json", preflight)
    if preflight["status"] != "ready_for_injection":
        print(json.dumps({"status": "environment_blocked", "errors": preflight["errors"]}, ensure_ascii=True))
        return 3
    if not args.approve_live:
        plan = {"schema_version": "chaosatlas-compose-e2e-plan-v1", "status": "ready_for_injection", "services": services, "fault_family": "container_kill", "approval_required": True}
        _write(args.output / "plan.json", plan)
        print(json.dumps(plan, ensure_ascii=True))
        return 0

    started = _now()
    runs: list[dict] = []
    for index, service in enumerate(services, start=1):
        run_dir = args.output / f"{index:02d}-{service}"
        try:
            result = adapter.run_service_canary(service)
        except Exception as exc:
            result = {"status": "environment_blocked", "service": service, "errors": [redact_text(str(exc))]}
        _write(run_dir / "run.json", result)
        runs.append({"service": service, "status": result.get("status"), "classification": result.get("classification"), "attestation": result.get("attestation")})
        if result.get("status") != "live_completed" and not args.continue_on_error:
            break
    completed = sum(1 for item in runs if item.get("status") == "live_completed")
    failed = [item for item in runs if item.get("status") != "live_completed"]
    summary = {
        "schema_version": "chaosatlas-compose-e2e-summary-v1",
        "status": "live_completed" if runs and not failed else "partial" if completed else "failed",
        "started_at": started,
        "finished_at": _now(),
        "project_id": profile["project_id"],
        "runtime": "docker_compose",
        "fault_family": "container_kill",
        "requested_services": services,
        "runs": runs,
        "completed_count": completed,
        "failed_count": len(failed),
        "claim_scope": "dify-compose-services",
        "promotion_allowed": False,
    }
    _write(args.output / "summary.json", summary)
    print(json.dumps({"status": summary["status"], "output": str(args.output), "completed": completed, "failed": len(failed)}, ensure_ascii=True))
    return 0 if summary["status"] == "live_completed" else 4


if __name__ == "__main__":
    raise SystemExit(main())
