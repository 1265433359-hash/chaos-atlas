"""Run the namespace-scoped fresh deployment adapter with an explicit live gate."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any, Callable

try:
    from tools.fresh_deploy import FreshDeploymentAdapter
except ModuleNotFoundError:
    from fresh_deploy import FreshDeploymentAdapter


Runner = Callable[[list[str]], dict[str, Any]]


def kubectl_runner(args: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["kubectl", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"return_code": 1, "stdout": "", "stderr": f"{type(exc).__name__}: {exc}"}
    return {
        "return_code": int(completed.returncode),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def run_fresh_deploy(
    *,
    source_root: Path,
    namespace: str,
    allowed_namespaces: set[str],
    runner: Runner | None = None,
    apply_live: bool = False,
    cleanup: bool = False,
    approve_live: bool = False,
) -> dict[str, Any]:
    if apply_live and cleanup:
        return {"status": "deployment_blocked", "reason": "apply_live and cleanup are mutually exclusive", "live_mutation": False}
    adapter = FreshDeploymentAdapter(
        namespace=namespace,
        allowed_namespaces=allowed_namespaces,
        runner=runner or kubectl_runner,
        allow_live=approve_live,
    )
    if cleanup:
        return adapter.cleanup(Path(source_root))
    if apply_live:
        return adapter.apply_live(Path(source_root))
    return adapter.deploy(Path(source_root))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--allowed-namespace", action="append")
    parser.add_argument("--apply-live", action="store_true")
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--approve-live", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    allowed = set(args.allowed_namespace or [args.namespace])
    result = run_fresh_deploy(
        source_root=args.source_root,
        namespace=args.namespace,
        allowed_namespaces=allowed,
        apply_live=args.apply_live,
        cleanup=args.cleanup,
        approve_live=args.approve_live,
    )
    payload = json.dumps(result, indent=2, ensure_ascii=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result.get("status") in {"dry_run_ready", "deployed", "cleanup_verified"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
