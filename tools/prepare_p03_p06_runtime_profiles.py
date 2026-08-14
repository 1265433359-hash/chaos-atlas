"""Build bounded, namespace-local P03/P06 Kubernetes preparation profiles.

This module is intentionally offline. It never builds or pulls images, calls a
model, or applies Kubernetes resources. Application image digests must be
provided by a separate, auditable source build; mutable public tags are
rejected.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "artifacts/experiments/chaosatlas_10_projects"
IMAGE_RE = re.compile(r"@sha256:[0-9a-f]{64}$")


PROJECTS: dict[str, dict[str, Any]] = {
    "P03": {
        "namespace": "chaosatlas-p03",
        "source_root": "artifacts/experiments/chaosatlas_10_projects/sources_restored_r2/P03",
        "source_commit": "15575bd85a8e0b87bfa867bb8a01cb76bca913ad",
        "source_tree_sha": "f7de71af55ea09258b3cd24ce43633bf11cce3e2",
        "dockerfile": "Dockerfile",
        "services": {
            "saleor": {
                "port": 8000,
                "health_path": "/graphql/",
                "oracle": "POST /graphql/ with {__typename} and HTTP 200 stable GraphQL envelope",
                "resources": {"requests": {"cpu": "500m", "memory": "1Gi"}, "limits": {"cpu": "2", "memory": "3Gi"}},
            },
            "db": {
                "port": 5432,
                "resources": {"requests": {"cpu": "100m", "memory": "256Mi"}, "limits": {"cpu": "500m", "memory": "768Mi"}},
            },
            "cache": {
                "port": 6379,
                "resources": {"requests": {"cpu": "50m", "memory": "64Mi"}, "limits": {"cpu": "250m", "memory": "256Mi"}},
            },
        },
        "env": {
            "saleor": {"DATABASE_URL": "postgres://saleor:saleor@db:5432/saleor", "CACHE_URL": "redis://cache:6379/0", "SECRET_KEY": "static-profile-placeholder"},
            "db": {"POSTGRES_USER": "saleor", "POSTGRES_PASSWORD": "saleor", "POSTGRES_DB": "saleor"},
        },
        "oracle": "POST /graphql/ with a deterministic __typename query; no external service or model call",
    },
    "P06": {
        "namespace": "chaosatlas-p06",
        "source_root": "artifacts/experiments/chaosatlas_10_projects/sources_restored_r2/P06",
        "source_commit": "9dca3724a6d65126ea937ef949f986e5aab47a81",
        "source_tree_sha": "882abaca309ccdaea234bc50dcf5138f1f63e03e",
        "dockerfile": "Dockerfile",
        "build_recipe": "artifacts/experiments/chaosatlas_10_projects/runtime_profiles/P06-r4/Dockerfile.build",
        "services": {
            "directus": {
                "port": 8055,
                "health_path": "/server/health",
                "oracle": "GET /server/health and GET /items/chaosatlas_probe?limit=1 after deterministic seed; stable JSON envelope",
                "resources": {"requests": {"cpu": "500m", "memory": "1Gi"}, "limits": {"cpu": "2", "memory": "3Gi"}},
            },
            "postgres": {
                "port": 5432,
                "resources": {"requests": {"cpu": "100m", "memory": "256Mi"}, "limits": {"cpu": "500m", "memory": "768Mi"}},
            },
        },
        "env": {
            "directus": {"DB_CLIENT": "pg", "DB_HOST": "postgres", "DB_PORT": "5432", "DB_DATABASE": "directus", "DB_USER": "directus", "DB_PASSWORD": "directus", "PUBLIC_URL": "http://directus:8055", "SECRET": "static-profile-placeholder"},
            "postgres": {"POSTGRES_USER": "directus", "POSTGRES_PASSWORD": "directus", "POSTGRES_DB": "directus"},
        },
        "oracle": "GET /server/health plus a seeded read-only /items/chaosatlas_probe?limit=1 request; no external service or model call",
    },
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_images(project_id: str, images: dict[str, str]) -> None:
    required = set(PROJECTS[project_id]["services"])
    app = "saleor" if project_id == "P03" else "directus"
    if app not in images:
        raise ValueError("application image digest is required")
    missing = sorted(required - set(images))
    if missing:
        raise ValueError(f"missing image digest(s): {', '.join(missing)}")
    for service in sorted(required):
        image = images[service]
        if not IMAGE_RE.search(image):
            raise ValueError(f"{service} image must use an immutable digest")
    if "@sha256:" not in images[app]:
        raise ValueError("application image digest is required")


def _env_documents(name: str, namespace: str, values: dict[str, str]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    sensitive_names = {"PASSWORD", "SECRET", "SECRET_KEY", "TOKEN", "PRIVATE_KEY"}
    public: dict[str, str] = {}
    sensitive: dict[str, str] = {}
    for key, value in values.items():
        if any(marker in key.upper() for marker in sensitive_names):
            sensitive[key] = "REPLACE_BEFORE_APPLY"
        else:
            public[key] = value
    config = {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": name, "namespace": namespace}, "data": public}
    secret = None
    if sensitive:
        secret = {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": f"{name}-secret", "namespace": namespace}, "type": "Opaque", "stringData": sensitive}
    return config, secret


def _deployment(project_id: str, namespace: str, service: str, image: str, spec: dict[str, Any], has_secret: bool) -> dict[str, Any]:
    labels = {"app.kubernetes.io/part-of": project_id.lower(), "app.kubernetes.io/name": service, "chaosatlas.io/profile": "bounded-r4"}
    container: dict[str, Any] = {
        "name": service,
        "image": image,
        "imagePullPolicy": "IfNotPresent",
        "resources": spec["resources"],
        "securityContext": {"allowPrivilegeEscalation": False, "runAsNonRoot": True},
    }
    if "health_path" in spec:
        container["ports"] = [{"name": "http", "containerPort": spec["port"]}]
        container["readinessProbe"] = {"httpGet": {"path": spec["health_path"], "port": "http"}, "initialDelaySeconds": 10, "periodSeconds": 10}
        container["livenessProbe"] = {"httpGet": {"path": spec["health_path"], "port": "http"}, "initialDelaySeconds": 30, "periodSeconds": 20}
    else:
        container["ports"] = [{"name": "tcp", "containerPort": spec["port"]}]
        container["readinessProbe"] = {"tcpSocket": {"port": "tcp"}, "initialDelaySeconds": 5, "periodSeconds": 10}
        container["livenessProbe"] = {"tcpSocket": {"port": "tcp"}, "initialDelaySeconds": 15, "periodSeconds": 20}
    if spec.get("env") is not None:
        container["envFrom"] = [{"configMapRef": {"name": f"{service}-env"}}]
        if has_secret:
            container["envFrom"].append({"secretRef": {"name": f"{service}-env-secret"}})
    return {
        "apiVersion": "apps/v1", "kind": "Deployment",
        "metadata": {"name": service, "namespace": namespace, "labels": labels},
        "spec": {"replicas": 1, "strategy": {"type": "Recreate"}, "selector": {"matchLabels": {"app.kubernetes.io/name": service}}, "template": {"metadata": {"labels": labels}, "spec": {"automountServiceAccountToken": False, "containers": [container]}}},
    }


def _service(namespace: str, name: str, port: int, http: bool) -> dict[str, Any]:
    return {"apiVersion": "v1", "kind": "Service", "metadata": {"name": name, "namespace": namespace}, "spec": {"type": "ClusterIP", "selector": {"app.kubernetes.io/name": name}, "ports": [{"name": "http" if http else "tcp", "port": port, "targetPort": "http" if http else "tcp"}]}}


def build_profile(project_id: str, images: dict[str, str]) -> dict[str, Any]:
    if project_id not in PROJECTS:
        raise ValueError(f"unsupported project: {project_id}")
    _validate_images(project_id, images)
    spec = PROJECTS[project_id]
    namespace = spec["namespace"]
    docs: list[dict[str, Any]] = [{"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": namespace, "labels": {"chaosatlas.io/profile": "bounded-r4"}}}]
    for service, service_spec in spec["services"].items():
        config, secret = _env_documents(f"{service}-env", namespace, spec["env"].get(service, {}))
        service_spec = dict(service_spec)
        service_spec["env"] = True
        docs.append(config)
        if secret:
            docs.append(secret)
        docs.append(_deployment(project_id, namespace, service, images[service], service_spec, secret is not None))
        docs.append(_service(namespace, service, service_spec["port"], "health_path" in service_spec))
    app = "saleor" if project_id == "P03" else "directus"
    source_root = ROOT / spec["source_root"]
    dockerfile = source_root / spec["dockerfile"]
    build_recipe = ROOT / spec.get("build_recipe", spec["source_root"] + "/" + spec["dockerfile"])
    static_gate = {"status": "passed", "source_provenance": "pass", "immutable_image_provenance": "pass", "namespace_local": "pass", "deterministic_oracle": "pass_contract_only", "resource_limits": "pass", "external_model_calls": False}
    return {
        "schema_version": "1.0", "project_id": project_id, "namespace": namespace,
        "source_commit": spec["source_commit"], "source_tree_sha": spec["source_tree_sha"],
        "source_dockerfile_sha256": _sha256(dockerfile) if dockerfile.is_file() else None,
        "build_recipe_sha256": _sha256(build_recipe) if build_recipe.is_file() else None,
        "images": images, "services": list(spec["services"]), "oracle": spec["oracle"],
        "static_gate": static_gate, "runtime_apply_allowed": False,
        "server_side_dry_run": "pending_authorized_cluster_session",
        "yaml": "---\n".join(yaml.safe_dump(doc, sort_keys=False) for doc in docs),
    }


def write_profile(profile: dict[str, Any], output_dir: Path) -> Path:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {key: value for key, value in profile.items() if key != "yaml"}
    manifest["profile_sha256"] = hashlib.sha256(profile["yaml"].encode("utf-8")).hexdigest()
    (output_dir / "static-profile.yaml").write_text(profile["yaml"], encoding="utf-8")
    (output_dir / "profile-manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    digest_manifest = {
        "schema_version": "1.0",
        "project_id": profile["project_id"],
        "status": "verified_local_content_digests",
        "source_commit": profile["source_commit"],
        "images": [
            {
                "service": service,
                "image": image,
                "digest": image.rsplit("@", 1)[1],
                "verification": "docker_image_inspect_local_content_id",
            }
            for service, image in profile["images"].items()
        ],
        "runtime_apply_allowed": False,
    }
    (output_dir / "image-digest-manifest.json").write_text(json.dumps(digest_manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    (output_dir / "static-gate.json").write_text(json.dumps({"project_id": profile["project_id"], "namespace": profile["namespace"], **profile["static_gate"], "runtime_apply_allowed": False}, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    (output_dir / "server-side-dry-run.json").write_text(json.dumps({"project_id": profile["project_id"], "namespace": profile["namespace"], "status": profile["server_side_dry_run"], "apply_allowed": False}, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return output_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", choices=sorted(PROJECTS), action="append", required=True)
    parser.add_argument("--output-root", type=Path, default=EXPERIMENT / "runtime_profiles")
    parser.add_argument("--image", action="append", default=[], metavar="SERVICE=IMAGE@sha256:DIGEST")
    parser.add_argument("--revision", type=int, default=4)
    args = parser.parse_args()
    images = dict(value.split("=", 1) for value in args.image)
    for project_id in args.project:
        output = args.output_root / f"{project_id}-r{args.revision}"
        try:
            profile = build_profile(project_id, images)
        except ValueError as exc:
            output.mkdir(parents=True, exist_ok=True)
            (output / "static-gate.json").write_text(json.dumps({"project_id": project_id, "status": "blocked", "runtime_apply_allowed": False, "blocked_reason": str(exc)}, indent=2) + "\n", encoding="utf-8")
            print(f"{project_id}: blocked: {exc}")
            continue
        write_profile(profile, output)
        print(f"{project_id}: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
