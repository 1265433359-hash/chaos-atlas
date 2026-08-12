"""Offline deployment preflight for the frozen Saleor P03 snapshot."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "artifacts/experiments/chaosatlas_10_projects/sources/P03"
OUT = ROOT / "artifacts/experiments/chaosatlas_10_projects/runtime_profiles/P03"


def sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def build() -> dict[str, Any]:
    compose = PROJECT / ".worktree-container/docker-compose.yml"
    data = yaml.safe_load(compose.read_text(encoding="utf-8-sig")) if compose.exists() else {}
    services = sorted((data or {}).get("services", {}).keys())
    required = [".devcontainer/common.env", ".devcontainer/backend.env", "pyproject.toml", "uv.lock", "manage.py"]
    missing = [name for name in required if not (PROJECT / name).exists()]
    reasons = []
    if missing:
        reasons.append("frozen_build_inputs_missing:" + ",".join(missing))
    if "saleor" not in services:
        reasons.append("application_service_missing")
    return {
        "schema_version": "1.0",
        "project_id": "P03",
        "project_commit": "15575bd85a8e0b87bfa867bb8a01cb76bca913ad",
        "status": "blocked" if reasons else "needs_runtime_gate",
        "runtime_apply_allowed": False,
        "source_root": str(PROJECT.relative_to(ROOT)).replace("\\", "/"),
        "compose_file_sha256": sha256(compose),
        "compose_services": services,
        "required_inputs": {name: (PROJECT / name).exists() for name in required},
        "reasons": reasons,
        "next_action": "Restore the exact Saleor source checkout including env and lock/build files before image construction; do not synthesize missing files for the formal experiment.",
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    result = build()
    (OUT / "deployment_preflight.json").write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
