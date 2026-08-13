"""Build offline, fail-closed preparation evidence for selected projects.

The command deliberately avoids Docker, kubectl, registry access, secrets, and
model calls. It only inspects local source snapshots and writes a new evidence
directory without overwriting an existing non-empty directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "artifacts/experiments/chaosatlas_10_projects"

PROJECTS: dict[str, dict[str, Any]] = {
    "P03": {
        "commit": "15575bd85a8e0b87bfa867bb8a01cb76bca913ad",
        "tree": "f7de71af55ea09258b3cd24ce43633bf11cce3e2",
        "file_count": 4664,
        "deployment_assets": [
            "Dockerfile",
            ".worktree-container/docker-compose.yml",
            ".devcontainer/docker-compose.yml",
            "socket.yml",
        ],
        "required_files": [
            ".devcontainer/common.env",
            ".devcontainer/backend.env",
            "pyproject.toml",
            "uv.lock",
            "manage.py",
        ],
        "oracle": {
            "status": "contract_only",
            "health": "HTTP health endpoint",
            "business_request": "deterministic GraphQL catalog query",
            "success_contract": "HTTP 200 with stable GraphQL response shape",
            "external_dependencies": ["mailpit", "postgres", "valkey"],
        },
    },
    "P06": {
        "commit": "9dca3724a6d65126ea937ef949f986e5aab47a81",
        "tree": "882abaca309ccdaea234bc50dcf5138f1f63e03e",
        "file_count": 4529,
        "deployment_assets": ["Dockerfile", "docker-compose.yml", "directus/readme.md"],
        "required_files": ["package.json", "pnpm-lock.yaml"],
        "oracle": {
            "status": "contract_only",
            "health": "GET /server/health",
            "business_request": "deterministic read-only schema/items request",
            "success_contract": "HTTP 200 with stable JSON envelope",
            "external_dependencies": ["one selected database profile"],
        },
    },
    "P08": {
        "commit": "107634b7e3229bb69d53674cb9ebc67bc1ed02a8",
        "tree": "8942eb9ca4169c8eab7434b8066b5c1718cf1206",
        "file_count": 13540,
        "deployment_assets": [
            "Dockerfile",
            "deploy/docker/docker-compose.yml",
            "deploy/helm/Chart.yaml",
            "deploy/helm/README.md",
        ],
        "required_files": [],
        "oracle": {
            "status": "contract_only",
            "health": "GET /api/v1/health",
            "business_request": "deterministic local API request after server readiness",
            "success_contract": "HTTP 200 with stable health/API response; no external model call",
            "external_dependencies": [],
        },
    },
}


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def choose_output_dir(parent: Path, base_name: str) -> Path:
    """Return a new path, preserving every existing non-empty directory."""

    candidate = parent / base_name
    if not candidate.exists() or not any(candidate.iterdir()):
        return candidate
    match = re.match(r"^(.*?)-r(\d+)$", base_name)
    if match:
        stem, revision = match.group(1), int(match.group(2))
    else:
        stem, revision = base_name, 1
    while True:
        revision += 1
        candidate = parent / f"{stem}-r{revision}"
        if not candidate.exists() or not any(candidate.iterdir()):
            return candidate


def _source_root(project_id: str) -> Path:
    restored = EXPERIMENT / "sources_restored_r2" / project_id
    frozen = EXPERIMENT / "sources" / project_id
    return restored if restored.exists() else frozen


def _compose_text(source_root: Path, project_id: str) -> tuple[Path | None, str]:
    candidates = {
        "P03": [source_root / ".worktree-container/docker-compose.yml"],
        "P06": [source_root / "docker-compose.yml"],
        "P08": [source_root / "deploy/docker/docker-compose.yml"],
    }[project_id]
    for path in candidates:
        if path.is_file():
            return path, path.read_text(encoding="utf-8-sig")
    return None, ""


def _compose_services(text: str) -> list[str]:
    services: list[str] = []
    in_services = False
    for line in text.splitlines():
        if re.match(r"^\s*services\s*:\s*$", line):
            in_services = True
            continue
        if in_services and line and not line.startswith((" ", "\t")):
            break
        if in_services:
            match = re.match(r"^\s{2}([A-Za-z0-9_.-]+)\s*:\s*$", line)
            if match:
                services.append(match.group(1))
    return sorted(set(services))


def _compose_images(text: str) -> list[str]:
    return re.findall(r"^\s*image\s*:\s*([^\s#]+)", text, flags=re.MULTILINE)


def _immutable(images: list[str]) -> bool:
    return bool(images) and all("@sha256:" in image for image in images)


def _source_manifest(project_id: str, source_root: Path) -> dict[str, Any]:
    meta = PROJECTS[project_id]
    files = {name: (source_root / name).is_file() for name in meta["required_files"]}
    assets = {name: (source_root / name).is_file() for name in meta["deployment_assets"]}
    try:
        display_root = str(source_root.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        display_root = str(source_root)
    return {
        "schema_version": "1.0",
        "project_id": project_id,
        "source_root": display_root,
        "source_commit": meta["commit"],
        "source_tree_sha": meta["tree"],
        "git_file_count": meta["file_count"],
        "source_status": "complete" if source_root.exists() and all(assets.values()) else "incomplete",
        "deployment_assets": assets,
        "required_files": files,
    }


def _static_gates(
    project_id: str,
    source: dict[str, Any],
    compose_path: Path | None,
    images: list[str],
    services: list[str],
) -> tuple[dict[str, Any], list[str]]:
    reasons: list[str] = []
    source_ok = source["source_status"] == "complete" and all(source["deployment_assets"].values())
    image_ok = _immutable(images)
    namespace_ok = True
    forbidden_ok = not any(
        re.search(r"nginx|sandbox|agent-backend|plugin-daemon|ssrf-proxy|external-model", value, re.I)
        for value in services + images
    )
    required_ok = source_ok
    health_ok = project_id in {"P03", "P06", "P08"}
    oracle_ok = False
    resource_ok = False
    external_ok = project_id != "P03" or not any("external" in value.lower() for value in services)

    if not source_ok:
        reasons.append("source_restore_incomplete")
    if not image_ok:
        reasons.append("immutable_image_provenance_missing")
    if not oracle_ok:
        reasons.append("deterministic_oracle_unverified")
    if not resource_ok:
        reasons.append("resource_limits_unverified")
    if not external_ok:
        reasons.append("external_dependency_unverified")
    if project_id == "P08":
        reasons.append("resource_pilot_required_very_high")
    if compose_path is None:
        reasons.append("deployment_profile_missing")

    def gate(status: str, evidence: Any = None, reason: str | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {"status": status}
        if evidence is not None:
            result["evidence"] = evidence
        if reason:
            result["reason"] = reason
        return result

    gates = {
        "source_provenance": gate("pass" if source_ok else "blocked", source),
        "immutable_image_provenance": gate("pass" if image_ok else "blocked", images),
        "namespace_local": gate("pass", f"chaosatlas-{project_id.lower()}"),
        "forbidden_high_blast_radius_services": gate("pass" if forbidden_ok else "blocked", services),
        "required_resources": gate("pass" if required_ok else "blocked", source["deployment_assets"]),
        "health_readiness_contract": gate("pass", PROJECTS[project_id]["oracle"]["health"]),
        "deterministic_oracle": gate("pass" if oracle_ok else "blocked", PROJECTS[project_id]["oracle"]),
        "resource_limits": gate("pass" if resource_ok else "blocked"),
        "external_dependencies": gate("pass" if external_ok else "blocked", PROJECTS[project_id]["oracle"]["external_dependencies"]),
        "runtime_apply_allowed": gate("blocked", False, "all required gates must pass and namespace authorization is required"),
    }
    return gates, reasons


def build_project_preparation(
    project_id: str,
    output_dir: Path,
    *,
    source_root: Path | None = None,
) -> dict[str, Any]:
    if project_id not in PROJECTS:
        raise ValueError(f"unsupported project: {project_id}")
    source_root = source_root or _source_root(project_id)
    compose_path, compose_text = _compose_text(source_root, project_id)
    services = _compose_services(compose_text)
    images = _compose_images(compose_text)
    source = _source_manifest(project_id, source_root)
    gates, reasons = _static_gates(project_id, source, compose_path, images, services)
    profile_hash = sha256(compose_path) if compose_path else None
    oracle = dict(PROJECTS[project_id]["oracle"])
    oracle.update(
        {
            "project_id": project_id,
            "namespace": f"chaosatlas-{project_id.lower()}",
            "external_model_calls": False,
            "verification": "offline_contract_only",
        }
    )
    status = "passed" if not reasons else "blocked"
    result = {
        "schema_version": "1.0",
        "project_id": project_id,
        "namespace": f"chaosatlas-{project_id.lower()}",
        "gate_status": status,
        "runtime_apply_allowed": False,
        "blocked_reasons": sorted(set(reasons)),
        "source": source,
        "deployment": {
            "compose_path": str(compose_path.relative_to(ROOT)).replace("\\", "/")
            if compose_path and compose_path.is_relative_to(ROOT)
            else None,
            "compose_sha256": profile_hash,
            "services": services,
            "images": images,
        },
        "static_gates": gates,
        "oracle_contract": oracle,
        "runtime_status": "not_started",
        "cleanup_status": "not_applicable",
        "global_chaos_residual_status": "not_checked_environment_blocked",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "source-manifest.json": source,
        "profile-manifest.json": {
            "schema_version": "1.0",
            "project_id": project_id,
            "namespace": result["namespace"],
            "status": "generated_preparation_only",
            "source_commit": PROJECTS[project_id]["commit"],
            "deployment_profile": "offline_preparation",
            "compose_sha256": profile_hash,
            "images": images,
            "runtime_apply_allowed": False,
        },
        "profile-preflight.json": {
            "project_id": project_id,
            "namespace": result["namespace"],
            "ok": status == "passed",
            "apply_allowed": False,
            "checks": [
                {"name": name, "ok": value["status"] == "pass", "status": value["status"]}
                for name, value in gates.items()
            ],
            "blocked_reasons": result["blocked_reasons"],
        },
        "oracle-contract.json": oracle,
        "server-side-dry-run.json": {
            "project_id": project_id,
            "namespace": result["namespace"],
            "status": "not_run_environment_and_runtime_blocked",
            "apply_allowed": False,
            "reason": "kubectl server-side dry-run requires an accessible authorized cluster session",
        },
        "static-gate.json": {
            "schema_version": "1.0",
            "project_id": project_id,
            "namespace": result["namespace"],
            "status": status,
            "runtime_apply_allowed": False,
            "gates": gates,
            "blocked_reasons": result["blocked_reasons"],
        },
        "image-digest-manifest.json": {
            "project_id": project_id,
            "registry_queries_performed": False,
            "images": [{"image": image, "digest": None, "status": "unverified"} for image in images],
            "status": "blocked" if images and not _immutable(images) else "not_required",
        },
        "preparation-report.json": result,
    }
    for name, data in files.items():
        (output_dir / name).write_text(
            json.dumps(data, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
    if project_id in {"P03", "P06"}:
        recovery = {
            "schema_version": "1.0",
            "project_id": project_id,
            "project_commit": PROJECTS[project_id]["commit"],
            "tree_sha": PROJECTS[project_id]["tree"],
            "tree_sha_verified_in_current_git": False,
            "source_tree_present": source["source_status"] == "complete",
            "complete_blob_set_present": False,
            "source_restore_status": "blocked_incomplete",
            "missing_required_files": [
                name for name, present in source["required_files"].items() if not present
            ],
            "runtime_apply_allowed": False,
            "reason_code": "source_unrecoverable_offline",
            "next_action": "provide offline source bundle or complete local Git object set",
        }
        (output_dir / "source-restore-gate.json").write_text(
            json.dumps(recovery, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        (output_dir / "offline-recovery-profile.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "project_id": project_id,
                    "status": "blocked",
                    "namespace": result["namespace"],
                    "deployment_profile": "not_generated_until_source_restore",
                    "runtime_apply_allowed": False,
                    "oracle_contract": oracle,
                    "blocked_reasons": result["blocked_reasons"],
                },
                indent=2,
                ensure_ascii=True,
            )
            + "\n",
            encoding="utf-8",
        )
    else:
        bounded = {
            "schema_version": "1.0",
            "project_id": "P08",
            "namespace": result["namespace"],
            "status": "preparation_only_blocked",
            "source_commit": PROJECTS["P08"]["commit"],
            "image": {
                "repository": "index.docker.io/appsmith/appsmith-ce",
                "digest": None,
                "required": True,
                "status": "unverified",
            },
            "replicas": 1,
            "resources": {
                "requests": {"cpu": "500m", "memory": "3000Mi"},
                "limits": {"cpu": "2", "memory": "4Gi"},
            },
            "health": {
                "path": "/api/v1/health",
                "port": 80,
                "readiness_required": True,
                "liveness_required": True,
            },
            "external_model_calls": False,
            "runtime_apply_allowed": False,
            "blocked_reasons": result["blocked_reasons"],
        }
        (output_dir / "bounded-profile.json").write_text(
            json.dumps(bounded, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        (output_dir / "verification-checklist.md").write_text(
            "\n".join(
                [
                    "# P08 Pre-runtime Verification Checklist",
                    "",
                    "- [ ] Verify `index.docker.io/appsmith/appsmith-ce` with an immutable digest from an approved registry path.",
                    "- [ ] Confirm the digest provenance is recorded without changing the frozen source commit.",
                    "- [ ] Render a namespace-local profile with one replica and bounded requests/limits.",
                    "- [ ] Confirm `/api/v1/health` readiness and liveness against the deployed image.",
                    "- [ ] Verify a fixed, read-only deterministic API oracle with stable response shape.",
                    "- [ ] Run server-side dry-run using an authorized Kubernetes session.",
                    "- [ ] Obtain explicit authorization for `chaosatlas-p08` before apply.",
                    "- [ ] Keep runtime serial with no other project in the cluster.",
                    "- [ ] After every injection, verify recovery, delete the Chaos object, and confirm global no-residual-Chaos.",
                    "",
                    "Current status: blocked. This checklist is preparation evidence only.",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", choices=sorted(PROJECTS), action="append", required=True)
    parser.add_argument("--output-root", type=Path, default=EXPERIMENT / "runtime_profiles")
    args = parser.parse_args()
    summaries = []
    for project_id in args.project:
        base = args.output_root / f"{project_id}-r2"
        output = choose_output_dir(args.output_root, base.name)
        summaries.append(
            {
                "project_id": project_id,
                "output_dir": str(output),
                "result": build_project_preparation(project_id, output),
            }
        )
    print(json.dumps(summaries, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
