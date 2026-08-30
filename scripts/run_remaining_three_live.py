"""Run the remaining DNS and API-server canaries with explicit safety gates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from scripts.runtime_env import runtime_env


def _run(command: list[str], *, cwd: Path) -> int:
    print("+", " ".join(command))
    return subprocess.run(command, cwd=str(cwd), check=False, env=runtime_env()).returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--context", required=True)
    parser.add_argument("--approve-live", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    profile = args.profile.resolve()
    output = args.output.resolve()
    if not args.approve_live:
        parser.error("--approve-live is required for live canaries")
    if not profile.is_file():
        parser.error(f"profile not found: {profile}")
    payload = json.loads(profile.read_text(encoding="utf-8-sig"))
    policy = payload.get("namespace_policy") or {}
    allowed = {str(item) for item in policy.get("allowed_namespaces") or []}
    if not policy.get("isolation_required") or not any(item.startswith("chaosatlas-run-") for item in allowed):
        parser.error("profile must require a chaosatlas-run-* isolated namespace")
    output.mkdir(parents=True, exist_ok=True)
    python = sys.executable
    common = [python, str(repo / "tools" / "chaosatlas.py"), "run", "--profile", str(profile), "--mode", "live", "--approve-live", "--kube-context", args.context]
    runs = [
        ("dns_failure", "dns-failure-live", "server:deployment:remaining-eight-canary:resource-canary:dns_failure"),
        ("dns_delay", "dns-delay-live", "server:deployment:remaining-eight-canary:resource-canary:dns_delay"),
        ("api_server_delay", "api-server-delay-live", "server:deployment:remaining-eight-canary:resource-canary:api_server_delay"),
    ]
    statuses: dict[str, int] = {}
    for fault, name, candidate in runs:
        command = [*common, "--candidate-id", candidate, "--output", str(output / name), "--seed", "20260828"]
        statuses[fault] = _run(command, cwd=repo)
    (output / "remaining-three-exit-codes.json").write_text(json.dumps(statuses, indent=2) + "\n", encoding="utf-8")
    return 0 if all(code == 0 for code in statuses.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
