"""Offline preflight for the Dify P09 reduced runtime profile."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "artifacts/experiments/chaosatlas_10_projects/sources/P09"
OUT = ROOT / "artifacts/experiments/chaosatlas_10_projects/runtime_profiles/P09"
COMPOSE = PROJECT / "docker/docker-compose.yaml"

CORE = ["init_permissions", "api", "worker", "worker_beat", "web", "db_postgres", "redis"]
FORBIDDEN_EXTERNAL = {"agent_backend", "sandbox", "plugin_daemon", "ssrf_proxy", "nginx"}


def sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def build() -> dict[str, Any]:
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8-sig")) if COMPOSE.exists() else {}
    services = compose.get("services") or {}
    missing_env = [name for name in ("docker/.env", "docker/middleware.env") if not (PROJECT / name).exists()]
    mutable_images: list[dict[str, str]] = []
    for name, service in services.items():
        image = str((service or {}).get("image") or "")
        if image.endswith(":latest") or ":latest" in image:
            mutable_images.append({"service": str(name), "image": image})
    reasons: list[str] = []
    if missing_env:
        reasons.append("required_env_missing:" + ",".join(missing_env))
    if mutable_images:
        reasons.append("mutable_images_require_digest_pinning")
    if not all(name in services for name in CORE):
        reasons.append("core_profile_service_missing")
    if any(name in services for name in FORBIDDEN_EXTERNAL):
        reasons.append("external_or_high_blast_radius_services_present_and_must_be_disabled")
    return {
        "schema_version": "1.0",
        "project_id": "P09",
        "project_commit": "cd0e88c680dec24dcd423b880302104f13d28462",
        "status": "blocked" if reasons else "needs_runtime_gate",
        "runtime_apply_allowed": False,
        "source_root": str(PROJECT.relative_to(ROOT)).replace("\\", "/"),
        "compose_sha256": sha256(COMPOSE),
        "all_service_count": len(services),
        "core_profile": CORE,
        "external_or_high_blast_radius_services": sorted(name for name in services if name in FORBIDDEN_EXTERNAL),
        "mutable_images": mutable_images,
        "required_env": {name: (PROJECT / name).exists() for name in ("docker/.env", "docker/middleware.env")},
        "model_policy": "No external LLM/model endpoint. Use deterministic local mock or exclude model workflow from oracle.",
        "reasons": reasons,
        "next_action": "Create a reviewed, digest-pinned namespace-local reduced profile from CORE only; do not apply the full generated Compose.",
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    result = build()
    (OUT / "deployment_preflight.json").write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
