"""Generate the P09 namespace-local minimal Kubernetes profile.

This generator intentionally does not contact a cluster or mutate the source
checkout. Image references are supplied as immutable digest references.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[5]
PROJECT = ROOT / "artifacts/experiments/chaosatlas_10_projects/sources_restored/P09"
PROJECT_R2 = ROOT / "artifacts/experiments/chaosatlas_10_projects/sources_restored_r2/P09"


def select_project() -> tuple[Path, Path]:
    for project in (PROJECT, PROJECT_R2):
        compose = project / "docker/docker-compose.yaml"
        if compose.exists():
            return project, compose
    return PROJECT, PROJECT / "docker/docker-compose.yaml"

SERVICES = ("init-permissions", "api", "worker", "worker-beat", "web", "postgres", "redis")
FORBIDDEN = ("agent-backend", "plugin-daemon", "sandbox", "ssrf-proxy", "nginx", "vector databases")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def labels(name: str) -> dict[str, str]:
    return {"app.kubernetes.io/part-of": "chaosatlas-p09", "app.kubernetes.io/name": name, "chaosatlas.io/profile": "minimal"}


def env_config() -> dict[str, str]:
    return {
        "DB_TYPE": "postgresql", "DB_HOST": "postgres", "DB_PORT": "5432", "DB_USERNAME": "postgres", "DB_DATABASE": "dify",
        "REDIS_HOST": "redis", "REDIS_PORT": "6379", "REDIS_DB": "0", "REDIS_USE_SSL": "false",
        "CELERY_BROKER_URL": "redis://redis:6379/1", "EVENT_BUS_REDIS_URL": "redis://redis:6379/1",
        "VECTOR_STORE": "opendal", "OPENDAL_SCHEME": "fs", "OPENDAL_FS_ROOT": "storage",
        "ETL_TYPE": "dify", "DIFY_BIND_ADDRESS": "0.0.0.0", "DIFY_PORT": "5001",
        "MODE": "api", "MIGRATION_ENABLED": "true", "DEBUG": "false", "FLASK_DEBUG": "false",
        "MARKETPLACE_ENABLED": "false", "ENABLE_COLLABORATION_MODE": "false", "ALLOW_REGISTER": "false",
        "ALLOW_CREATE_WORKSPACE": "false", "ENABLE_WEBSITE_JINAREADER": "false", "ENABLE_WEBSITE_FIRECRAWL": "false",
        "ENABLE_WEBSITE_WATERCRAWL": "false", "CODE_EXECUTION_ENDPOINT": "", "SSRF_PROXY_HTTP_URL": "",
        "SSRF_PROXY_HTTPS_URL": "", "AGENT_BACKEND_BASE_URL": "", "PLUGIN_REMOTE_INSTALL_HOST": "",
        "PLUGIN_REMOTE_INSTALL_PORT": "0", "PLUGIN_DIFY_INNER_API_KEY": "", "DIFY_AGENT_API_TOKEN": "",
        "OPENAI_API_BASE": "", "OPENAI_API_KEY": "", "CONSOLE_API_URL": "http://web:3000",
        "SERVER_CONSOLE_API_URL": "http://api:5001", "APP_API_URL": "http://api:5001",
    }


def container(name: str, image: str, env: dict[str, str] | None = None, ports: list[dict[str, Any]] | None = None,
              command: list[str] | None = None, probes: dict[str, Any] | None = None, volume: bool = False) -> dict[str, Any]:
    c: dict[str, Any] = {"name": name, "image": image, "imagePullPolicy": "IfNotPresent", "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": False}}
    if env is not None:
        c["envFrom"] = [{"configMapRef": {"name": "p09-env"}}, {"secretRef": {"name": "p09-secrets"}}]
        c["env"] = [{"name": k, "value": v} for k, v in sorted(env.items())]
    if ports:
        c["ports"] = ports
    if command:
        c["command"] = command
    if probes:
        c.update(probes)
    if volume:
        c["volumeMounts"] = [{"name": "app-storage", "mountPath": "/app/api/storage"}]
    return c


def deployment(name: str, c: dict[str, Any], volume: bool = False, replicas: int = 1) -> dict[str, Any]:
    pod: dict[str, Any] = {"automountServiceAccountToken": False, "containers": [c]}
    if volume:
        pod["volumes"] = [{"name": "app-storage", "persistentVolumeClaim": {"claimName": "p09-app-storage"}}]
    return {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": name, "namespace": "chaosatlas-p09", "labels": labels(name)},
            "spec": {"replicas": replicas, "selector": {"matchLabels": {"app.kubernetes.io/name": name}}, "strategy": {"type": "Recreate"},
                     "template": {"metadata": {"labels": labels(name)}, "spec": pod}}}


def service(name: str, port: int, target: int) -> dict[str, Any]:
    return {"apiVersion": "v1", "kind": "Service", "metadata": {"name": name, "namespace": "chaosatlas-p09", "labels": labels(name)},
            "spec": {"type": "ClusterIP", "selector": {"app.kubernetes.io/name": name}, "ports": [{"name": "http" if port == 5001 else "tcp", "port": port, "targetPort": target}]}}


def generate(digests: dict[str, str]) -> list[dict[str, Any]]:
    ns = {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "chaosatlas-p09", "labels": {"chaosatlas.io/profile": "minimal"}}}
    pvc = {"apiVersion": "v1", "kind": "PersistentVolumeClaim", "metadata": {"name": "p09-app-storage", "namespace": "chaosatlas-p09"}, "spec": {"accessModes": ["ReadWriteOnce"], "resources": {"requests": {"storage": "1Gi"}}}}
    cm = {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "p09-env", "namespace": "chaosatlas-p09"}, "data": env_config()}
    secret = {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "p09-secrets", "namespace": "chaosatlas-p09"}, "type": "Opaque",
              "stringData": {"DB_PASSWORD": "REPLACE_BEFORE_APPLY", "POSTGRES_PASSWORD": "REPLACE_BEFORE_APPLY", "REDIS_PASSWORD": "REPLACE_BEFORE_APPLY", "SECRET_KEY": "REPLACE_BEFORE_APPLY"}}
    docs: list[dict[str, Any]] = [ns, pvc, cm, secret]
    init = container("init-permissions", digests["busybox"], command=["sh", "-c", "mkdir -p /app/api/storage && chown -R 1001:1001 /app/api/storage && touch /app/api/storage/.init_permissions"], volume=True)
    docs.append({"apiVersion": "batch/v1", "kind": "Job", "metadata": {"name": "init-permissions", "namespace": "chaosatlas-p09", "labels": labels("init-permissions")},
                 "spec": {"backoffLimit": 2, "template": {"metadata": {"labels": labels("init-permissions")}, "spec": {"restartPolicy": "OnFailure", "automountServiceAccountToken": False,
                 "containers": [init], "volumes": [{"name": "app-storage", "persistentVolumeClaim": {"claimName": "p09-app-storage"}}]}}}})
    api_probe = {"readinessProbe": {"httpGet": {"path": "/health", "port": 5001}, "initialDelaySeconds": 30, "periodSeconds": 10}, "livenessProbe": {"httpGet": {"path": "/health", "port": 5001}, "initialDelaySeconds": 60, "periodSeconds": 20}}
    api = container("api", digests["dify-api"], {"MODE": "api"}, [{"name": "http", "containerPort": 5001}], probes=api_probe, volume=True)
    worker = container("worker", digests["dify-api"], {"MODE": "worker"}, volume=True)
    beat = container("worker-beat", digests["dify-api"], {"MODE": "beat"}, volume=True)
    web = container("web", digests["dify-web"], {"SERVER_CONSOLE_API_URL": "http://api:5001"}, [{"name": "http", "containerPort": 3000}], probes={"readinessProbe": {"tcpSocket": {"port": 3000}, "initialDelaySeconds": 20, "periodSeconds": 10}})
    for name, c in (("api", api), ("worker", worker), ("worker-beat", beat), ("web", web)):
        docs.append(deployment(name, c, volume=name != "web"))
    pg = container("postgres", digests["postgres"], {"POSTGRES_USER": "postgres", "POSTGRES_DB": "dify"}, ports=[{"name": "postgres", "containerPort": 5432}], command=["postgres", "-c", "max_connections=100"], probes={"readinessProbe": {"exec": {"command": ["pg_isready", "-U", "postgres", "-d", "dify"]}, "periodSeconds": 5}})
    redis = container("redis", digests["redis"], {}, ports=[{"name": "redis", "containerPort": 6379}], command=["redis-server", "--appendonly", "yes"], probes={"readinessProbe": {"exec": {"command": ["redis-cli", "ping"]}, "periodSeconds": 5}})
    docs.extend([deployment("postgres", pg, replicas=1), service("postgres", 5432, 5432), deployment("redis", redis, replicas=1), service("redis", 6379, 6379), service("api", 5001, 5001), service("web", 3000, 3000)])
    return docs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=Path(__file__).parent / "minimal-profile.yaml")
    ap.add_argument("--digest", action="append", default=[], metavar="NAME=IMAGE@DIGEST")
    args = ap.parse_args()
    digests = {k: v for item in args.digest for k, _, v in [item.partition("=")] if _ and v}
    required = {"busybox", "dify-api", "dify-web", "postgres", "redis"}
    missing = required - set(digests)
    if missing:
        raise SystemExit("missing immutable image references: " + ", ".join(sorted(missing)))
    invalid = {k: v for k, v in digests.items() if "@sha256:" not in v or len(v.rsplit("@sha256:", 1)[-1]) != 64}
    if invalid:
        raise SystemExit("image references must be digest-pinned: " + ", ".join(f"{k}={v}" for k, v in sorted(invalid.items())))
    project, compose = select_project()
    if not compose.exists():
        raise SystemExit("missing P09 source: docker/docker-compose.yaml")
    docs = generate(digests)
    args.output.write_text("---\n".join(yaml.safe_dump(x, sort_keys=False) for x in docs), encoding="utf-8")
    manifest = {"schema_version": "1.0", "project_id": "P09", "namespace": "chaosatlas-p09", "status": "generated_dry_run_only", "source_root": str(project.relative_to(ROOT)).replace("\\", "/"), "source_commit": "cd0e88c680dec24dcd423b880302104f13d28462", "compose_sha256": sha256(compose), "included_services": list(SERVICES), "excluded_services": list(FORBIDDEN), "images": digests, "resource_count": len(docs), "runtime_apply_allowed": False}
    (args.output.parent / "profile_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (args.output.parent / "runtime.env.example").write_text("\n".join(f"{k}={v}" for k, v in sorted(env_config().items())) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
