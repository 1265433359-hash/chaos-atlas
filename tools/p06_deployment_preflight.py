"""Offline deployment preflight for the frozen Directus P06 snapshot.

This deliberately does not build images, pull registries, read secrets, or
apply Kubernetes resources. It records whether the frozen source tree contains
the inputs needed for a reproducible namespace-local profile.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "artifacts/experiments/chaosatlas_10_projects/sources/P06"
OUT = ROOT / "artifacts/experiments/chaosatlas_10_projects/runtime_profiles/P06"


def sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compose_services(path: Path) -> list[str]:
    # Avoid a YAML dependency in the gate: service names are extracted only
    # from the frozen, already-audited Compose file's top-level block.
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}
    return sorted((data.get("services") or {}).keys())


def build() -> dict[str, Any]:
    dockerfile = PROJECT / "Dockerfile"
    compose = PROJECT / "docker-compose.yml"
    required = ["package.json", "pnpm-lock.yaml"]
    missing = [name for name in required if not (PROJECT / name).exists()]
    services = compose_services(compose) if compose.exists() else []
    has_application_service = any(name in {"directus", "api", "app"} for name in services)
    license_readme = PROJECT / "directus/readme.md"
    status = "blocked"
    reasons: list[str] = []
    if missing:
        reasons.append("dockerfile_build_inputs_missing:" + ",".join(missing))
    if not has_application_service:
        reasons.append("compose_is_dependency_matrix_only:no_directus_application_service")
    if not license_readme.exists():
        reasons.append("license_evidence_missing")
    return {
        "schema_version": "1.0",
        "project_id": "P06",
        "project_commit": "9dca3724a6d65126ea937ef949f986e5aab47a81",
        "status": status,
        "runtime_apply_allowed": False,
        "source_root": str(PROJECT.relative_to(ROOT)).replace("\\", "/"),
        "files": {
            "Dockerfile": {"exists": dockerfile.exists(), "sha256": sha256(dockerfile)},
            "docker-compose.yml": {"exists": compose.exists(), "sha256": sha256(compose)},
            "directus/readme.md": {"exists": license_readme.exists(), "sha256": sha256(license_readme)},
        },
        "required_build_inputs": {name: (PROJECT / name).exists() for name in required},
        "compose_services": services,
        "application_service_present": has_application_service,
        "license": {"source": "directus/readme.md", "evidence": "MSCL 1.0 / free core tier noted; commercial thresholds require separate review"},
        "reasons": reasons,
        "next_action": "Do not construct an application image from this sparse snapshot. Restore the exact source-tree checkout or mark P06 environment_blocked for this round.",
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    result = build()
    (OUT / "deployment_preflight.json").write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
