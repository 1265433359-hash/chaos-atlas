"""Run P0 isolation acceptance with explicit evidence-scope labels."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from chaosatlas.isolation.lease_store import LeaseStore
from chaosatlas.isolation.manager import IsolationManager
from chaosatlas.isolation.planner import IsolationPlanner
from chaosatlas.isolation.providers import KubernetesIsolationProvider, MinikubeIsolationProvider, ProviderRegistry
from chaosatlas.workspace import is_within


APP_NAMESPACES = ("chaosatlas-immich", "chaosatlas-erpnext", "chaosatlas-medusa", "chaosatlas-rocketchat")


def _run(args: list[str], timeout: int = 90, *, input_text: str | None = None, cwd: Path | None = None, env: dict[str, str] | None = None) -> tuple[int, str, str]:
    try:
        result = subprocess.run(args, input=input_text, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
        return result.returncode, result.stdout or "", result.stderr or ""
    except subprocess.TimeoutExpired as exc:
        return 124, str(exc.stdout or ""), f"TimeoutExpired after {timeout}s"
    except (OSError, subprocess.SubprocessError) as exc:
        return 125, "", f"{type(exc).__name__}: {exc}"


def _kubectl(context: str, args: list[str], *, timeout: int = 90, input_text: str | None = None) -> tuple[int, str, str]:
    return _run(["kubectl", "--context", context, *args], timeout=timeout, input_text=input_text)


def _kubectl_json(context: str, args: list[str]) -> dict[str, Any]:
    code, stdout, stderr = _kubectl(context, [*args, "-o", "json"])
    if code != 0:
        raise RuntimeError((stderr or stdout).strip() or f"kubectl exited {code}")
    value = json.loads(stdout)
    if not isinstance(value, dict):
        raise RuntimeError("kubectl result is not an object")
    return value


def _snapshot(context: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for namespace in APP_NAMESPACES:
        ns = _kubectl_json(context, ["get", "namespace", namespace])
        pods = _kubectl_json(context, ["get", "pods", "-n", namespace])
        workloads = _kubectl_json(context, ["get", "deployments,statefulsets", "-n", namespace])
        result[namespace] = {
            "namespace_uid": str((ns.get("metadata") or {}).get("uid") or ""),
            "workloads": sorted(({
                "kind": str(item.get("kind") or ""), "name": str((item.get("metadata") or {}).get("name") or ""),
                "generation": int((item.get("metadata") or {}).get("generation") or 0),
                "ready_replicas": int((item.get("status") or {}).get("readyReplicas") or 0),
                "images": [str(container.get("image") or "") for container in (((item.get("spec") or {}).get("template") or {}).get("spec") or {}).get("containers") or []],
            } for item in workloads.get("items") or [] if isinstance(item, dict)), key=lambda item: (item["kind"], item["name"])),
            "pods": sorted(({
                "name": str((item.get("metadata") or {}).get("name") or ""), "uid": str((item.get("metadata") or {}).get("uid") or ""),
                "phase": str((item.get("status") or {}).get("phase") or ""),
                "image_ids": sorted(str(status.get("imageID") or "") for status in (item.get("status") or {}).get("containerStatuses") or []),
            } for item in pods.get("items") or [] if isinstance(item, dict)), key=lambda item: item["name"]),
        }
    return result


def _pause_workload(name: str) -> dict[str, Any]:
    labels = {"app": name}
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": labels},
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "containers": [{
                        "name": name,
                        "image": "registry.k8s.io/pause:3.10.1",
                        "resources": {
                            "requests": {"cpu": "10m", "memory": "16Mi"},
                            "limits": {"cpu": "100m", "memory": "64Mi"},
                        },
                    }],
                },
            },
        },
    }


def _connection_env() -> list[dict[str, Any]]:
    return [
        {"name": "DATABASE_URL", "valueFrom": {"secretKeyRef": {"name": "medusa-runtime-secrets", "key": "database-url"}}},
        {"name": "DB_NAME", "value": "medusa"},
        {"name": "REDIS_URL", "valueFrom": {"configMapKeyRef": {"name": "medusa-test-config", "key": "redis-url"}}},
        {"name": "JWT_SECRET", "valueFrom": {"secretKeyRef": {"name": "medusa-runtime-secrets", "key": "jwt-secret"}}},
        {"name": "COOKIE_SECRET", "valueFrom": {"secretKeyRef": {"name": "medusa-runtime-secrets", "key": "cookie-secret"}}},
    ]


def _medusa_blueprint() -> dict[str, Any]:
    postgres_labels, redis_labels, backend_labels = {"app": "medusa-postgres"}, {"app": "medusa-redis"}, {"app": "medusa-backend"}
    resources: list[dict[str, Any]] = [
        {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "medusa-test-config"}, "data": {"redis-url": "redis://medusa-redis:6379"}},
        {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "medusa-runtime-secrets"}, "runtimeGenerate": {"keys": ["postgres-password", "jwt-secret", "cookie-secret"], "templates": {"database-url": "postgres://medusa:${postgres-password}@medusa-postgres:5432/medusa?sslmode=disable"}}},
        {"apiVersion": "v1", "kind": "Service", "metadata": {"name": "medusa-postgres"}, "spec": {"selector": postgres_labels, "ports": [{"name": "postgres", "port": 5432}]}},
        {"apiVersion": "v1", "kind": "Service", "metadata": {"name": "medusa-redis"}, "spec": {"selector": redis_labels, "ports": [{"name": "redis", "port": 6379}]}},
        {"apiVersion": "v1", "kind": "Service", "metadata": {"name": "medusa-backend"}, "spec": {"selector": backend_labels, "ports": [{"name": "http", "port": 9000, "targetPort": "http"}]}},
        {"apiVersion": "apps/v1", "kind": "StatefulSet", "metadata": {"name": "medusa-postgres"}, "spec": {"serviceName": "medusa-postgres", "replicas": 1, "selector": {"matchLabels": postgres_labels}, "template": {"metadata": {"labels": postgres_labels}, "spec": {"containers": [{"name": "postgres", "image": "docker.io/library/postgres:15-alpine", "env": [{"name": "POSTGRES_DB", "value": "medusa"}, {"name": "POSTGRES_USER", "value": "medusa"}, {"name": "POSTGRES_PASSWORD", "valueFrom": {"secretKeyRef": {"name": "medusa-runtime-secrets", "key": "postgres-password"}}}], "ports": [{"name": "postgres", "containerPort": 5432}], "readinessProbe": {"exec": {"command": ["sh", "-c", "pg_isready -U medusa -d medusa"]}, "initialDelaySeconds": 5, "periodSeconds": 5}, "resources": {"requests": {"cpu": "25m", "memory": "64Mi"}, "limits": {"cpu": "500m", "memory": "512Mi"}}, "volumeMounts": [{"name": "data", "mountPath": "/var/lib/postgresql/data"}]}], "volumes": [{"name": "data", "emptyDir": {}}]}}}},
        {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "medusa-redis"}, "spec": {"replicas": 1, "selector": {"matchLabels": redis_labels}, "template": {"metadata": {"labels": redis_labels}, "spec": {"containers": [{"name": "redis", "image": "docker.io/library/redis:6-alpine", "ports": [{"name": "redis", "containerPort": 6379}], "readinessProbe": {"exec": {"command": ["redis-cli", "ping"]}, "initialDelaySeconds": 2, "periodSeconds": 3}, "resources": {"requests": {"cpu": "10m", "memory": "16Mi"}, "limits": {"cpu": "250m", "memory": "128Mi"}}}]}}}},
        {"apiVersion": "batch/v1", "kind": "Job", "metadata": {"name": "medusa-migrate", "annotations": {"chaosatlas.dev/wait-before-next": "true"}}, "spec": {"backoffLimit": 4, "template": {"metadata": {"labels": {"app": "medusa-migrate"}}, "spec": {"restartPolicy": "OnFailure", "initContainers": [{"name": "wait-for-postgres", "image": "docker.io/library/postgres:15-alpine", "command": ["sh", "-c", "until pg_isready -h medusa-postgres -U medusa -d medusa; do sleep 2; done"]}], "containers": [{"name": "migrate", "image": "docker.io/chaosatlas/medusa-backend:2.20.1", "workingDir": "/app/apps/backend", "command": ["npx", "medusa", "db:migrate"], "env": [*_connection_env(), {"name": "MEDUSA_DB_MIGRATION_CONNECTION_TIMEOUT", "value": "60000"}], "resources": {"requests": {"cpu": "50m", "memory": "128Mi"}, "limits": {"cpu": "1000m", "memory": "1Gi"}}}]}}}},
        {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "medusa-backend"}, "spec": {"replicas": 1, "selector": {"matchLabels": backend_labels}, "template": {"metadata": {"labels": backend_labels}, "spec": {"containers": [{"name": "backend", "image": "docker.io/chaosatlas/medusa-backend:2.20.1", "ports": [{"name": "http", "containerPort": 9000}], "env": [*_connection_env(), {"name": "STORE_CORS", "value": "http://synthetic.invalid"}, {"name": "ADMIN_CORS", "value": "http://synthetic.invalid"}, {"name": "AUTH_CORS", "value": "http://synthetic.invalid"}], "readinessProbe": {"httpGet": {"path": "/health", "port": "http"}, "initialDelaySeconds": 20, "periodSeconds": 5}, "resources": {"requests": {"cpu": "50m", "memory": "128Mi"}, "limits": {"cpu": "1000m", "memory": "1Gi"}}}]}}}},
    ]
    return {"resources": resources}


def _redis_target_blueprint() -> dict[str, Any]:
    labels = {"app": "l2-medusa-redis"}
    return {"resources": [
        {"apiVersion": "v1", "kind": "Service", "metadata": {"name": "l2-medusa-redis"}, "spec": {"selector": labels, "ports": [{"name": "redis", "port": 6379}]}},
        {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "l2-medusa-redis"}, "spec": {"replicas": 1, "selector": {"matchLabels": labels}, "template": {"metadata": {"labels": labels}, "spec": {"containers": [{"name": "redis", "image": "docker.io/library/redis:6-alpine", "ports": [{"name": "redis", "containerPort": 6379}], "readinessProbe": {"exec": {"command": ["redis-cli", "ping"]}, "periodSeconds": 3}, "resources": {"requests": {"cpu": "10m", "memory": "16Mi"}, "limits": {"cpu": "250m", "memory": "128Mi"}}}]}}}},
    ]}


def _capability(fault_id: str, level: str) -> dict[str, Any]:
    return {"fault_id": fault_id, "target_id": "acceptance-target", "required_isolation": level, "capability_status": "canary_required"}


Verifier = Callable[[dict[str, Any]], dict[str, Any]]


def _execute_stage(manager: IsolationManager, name: str, evidence_scope: str, plan: dict[str, Any], verifier: Verifier | None = None) -> dict[str, Any]:
    stage: dict[str, Any] = {"name": name, "evidence_scope": evidence_scope, "plan_id": plan.get("plan_id"), "plan_status": plan.get("status")}
    if plan.get("status") != "ready":
        return {**stage, "status": "blocked", "errors": list(plan.get("blockers") or [])}
    lease = manager.prepare(plan, ttl_minutes=30)
    stage.update({"lease_id": lease["lease_id"], "provider": lease["provider"], "target_name": lease["target_name"], "prepare_state": lease["state"], "runtime_locator": lease.get("runtime_locator")})
    verification: dict[str, Any] = {"status": "verified", "checks": {}, "errors": []}
    if lease["state"] == "ready" and verifier:
        try:
            verification = verifier(lease)
        except Exception as exc:
            verification = {"status": "failed", "checks": {}, "errors": [f"{type(exc).__name__}: {exc}"]}
    released = manager.release(lease["lease_id"])
    stage.update({"verification": verification, "cleanup_state": released["state"], "cleanup_attempts": released["cleanup_attempts"]})
    okay = lease["state"] == "ready" and verification.get("status") == "verified" and released["state"] == "released"
    errors = [] if okay else [str(lease.get("last_error") or released.get("last_error") or "stage did not pass")]
    errors.extend(str(item) for item in verification.get("errors") or [])
    return {**stage, "status": "verified" if okay else "failed", "errors": errors}


def _verify_medusa_clone(context: str, lease: dict[str, Any]) -> dict[str, Any]:
    namespace = str(lease["target_name"])
    code, stdout, stderr = _kubectl(context, ["exec", "-n", namespace, "deployment/medusa-backend", "--", "node", "-e", "fetch('http://127.0.0.1:9000/health').then(async r=>{console.log(r.status,await r.text());process.exit(r.ok?0:2)}).catch(e=>{console.error(e);process.exit(3)})"], timeout=30)
    okay = code == 0 and "200" in stdout
    return {"status": "verified" if okay else "failed", "checks": {"health_http_200": okay, "response_excerpt": stdout.strip()[:160]}, "errors": [] if okay else [(stderr or stdout).strip() or f"health probe exit {code}"]}


def _verify_l2_guards(context: str, lease: dict[str, Any]) -> dict[str, Any]:
    namespace = str(lease["target_name"])
    internal_code, internal_out, internal_err = _kubectl(context, ["exec", "-n", namespace, "deployment/l2-medusa-redis", "--", "redis-cli", "-h", "l2-medusa-redis", "ping"], timeout=15)
    source_before_code, source_before_out, _ = _kubectl(context, ["exec", "-n", "chaosatlas-medusa", "deployment/medusa-redis", "--", "redis-cli", "ping"], timeout=15)
    external_code, external_out, external_err = _kubectl(context, ["exec", "-n", "chaosatlas-medusa", "deployment/medusa-redis", "--", "redis-cli", "-h", f"l2-medusa-redis.{namespace}.svc.cluster.local", "ping"], timeout=8)
    source_after_code, source_after_out, _ = _kubectl(context, ["exec", "-n", "chaosatlas-medusa", "deployment/medusa-redis", "--", "redis-cli", "ping"], timeout=15)
    over_budget = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "quota-rejection-probe", "namespace": namespace, "labels": lease["owner_labels"]}, "spec": {"restartPolicy": "Never", "containers": [{"name": "probe", "image": "registry.k8s.io/pause:3.10.1", "resources": {"requests": {"cpu": "3", "memory": "16Mi"}, "limits": {"cpu": "3", "memory": "64Mi"}}}]}}
    quota_code, quota_out, quota_err = _kubectl(context, ["create", "--dry-run=server", "-f", "-"], timeout=30, input_text=json.dumps(over_budget))
    checks = {
        "real_target_redis_ping": internal_code == 0 and "PONG" in internal_out,
        "cross_namespace_ingress_denied": external_code != 0 and "PONG" not in external_out,
        "quota_rejects_over_budget_pod_server_dry_run": quota_code != 0 and "exceeded quota" in (quota_err + quota_out).lower(),
        "unowned_source_probe_healthy_before_after": source_before_code == 0 and source_after_code == 0 and "PONG" in source_before_out and "PONG" in source_after_out,
        "external_probe_exit": external_code, "external_probe_excerpt": (external_err or external_out).strip()[:160], "quota_probe_excerpt": (quota_err or quota_out).strip()[:240],
    }
    decisive = ("real_target_redis_ping", "cross_namespace_ingress_denied", "quota_rejects_over_budget_pod_server_dry_run", "unowned_source_probe_healthy_before_after")
    okay = all(checks[key] is True for key in decisive)
    errors = [] if okay else ["one or more L2 data-plane/resource guard probes failed"]
    if internal_code != 0:
        errors.append((internal_err or internal_out).strip())
    return {"status": "verified" if okay else "failed", "checks": checks, "errors": errors}


def _cross_process_cli_acceptance(repository_root: Path, output_root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    plan_path, store_root = output_root / "cli-recovery-plan.json", output_root / "cli-store"
    plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    process_env = dict(os.environ)
    process_env["PYTHONPATH"] = os.pathsep.join([str(repository_root), str(repository_root / "src"), process_env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    prepare = [sys.executable, "-m", "chaosatlas.cli", "isolation", "prepare", "--plan", str(plan_path), "--store-root", str(store_root), "--ttl-minutes", "30", "--approve-isolation"]
    prepare_code, prepare_out, prepare_err = _run(prepare, timeout=240, cwd=repository_root, env=process_env)
    try:
        prepared = json.loads(prepare_out)
    except json.JSONDecodeError:
        prepared = {}
    lease_id = str(prepared.get("lease_id") or "")
    recover_code, recover_out, recover_err, recovered = 2, "", "prepare did not return a lease", {}
    if lease_id:
        recover = [sys.executable, "-m", "chaosatlas.cli", "isolation", "recover", "--lease-id", lease_id, "--store-root", str(store_root), "--approve-isolation"]
        recover_code, recover_out, recover_err = _run(recover, timeout=240, cwd=repository_root, env=process_env)
        try:
            recovered = json.loads(recover_out)
        except json.JSONDecodeError:
            recovered = {}
    okay = prepare_code == 0 and recover_code == 0 and prepared.get("state") == "ready" and recovered.get("state") == "released" and prepared.get("runtime_locator") == recovered.get("runtime_locator")
    return {"name": "public-cli-cross-process-recovery", "evidence_scope": "real_lifecycle_cross_process", "status": "verified" if okay else "failed", "lease_id": lease_id or None, "prepare_exit": prepare_code, "recover_exit": recover_code, "runtime_locator_preserved": bool(prepared.get("runtime_locator")) and prepared.get("runtime_locator") == recovered.get("runtime_locator"), "errors": [] if okay else [(prepare_err or recover_err or prepare_out or recover_out).strip()[:500]]}


def _scan_sensitive(root: Path) -> list[str]:
    pattern = re.compile(r'"(?:password|passwd|token|authorization|cookie|api[_-]?key|private[_-]?key)"\s*:\s*"(?!<redacted>)[^"\r\n]+"|-----BEGIN [A-Z ]*PRIVATE KEY-----|\bBearer\s+[A-Za-z0-9._~+/=-]{8,}', re.IGNORECASE)
    return [str(path.relative_to(root)) for path in sorted(root.rglob("*.json")) if pattern.search(path.read_text(encoding="utf-8-sig", errors="replace"))]


def run_acceptance(*, repository_root: Path, output_root: Path, context: str, include_l3: bool = True) -> dict[str, Any]:
    repository_root, output_root = repository_root.resolve(), output_root.resolve()
    if is_within(output_root, repository_root):
        raise ValueError("acceptance output must be outside the repository")
    if output_root.exists() and (not output_root.is_dir() or any(output_root.iterdir())):
        raise ValueError("acceptance output must be an empty directory")
    output_root.mkdir(parents=True, exist_ok=True)
    store = LeaseStore(output_root / "state", coordination_root=output_root / "coordination")
    manager = IsolationManager(store=store, providers=ProviderRegistry([KubernetesIsolationProvider(name="kubernetes-l1", level="L1"), KubernetesIsolationProvider(name="kubernetes-l2", level="L2"), MinikubeIsolationProvider(root=output_root / "runtime")]))
    planner = IsolationPlanner()
    summary: dict[str, Any] = {"schema_version": "chaosatlas-isolation-acceptance-v2", "started_at": datetime.now(timezone.utc).isoformat(), "context": context, "fault_injection_performed": False, "business_transaction_executed": False, "scope_statement": "P0 validates infrastructure lifecycle, selected real workload startup, one real target, and guard effects. It does not validate four complete business transactions or any fault outcome.", "stages": [], "errors": []}
    summary_path = output_root / "acceptance-summary.json"
    try:
        before = _snapshot(context)
        summary["before"] = before
        summary["environment_fidelity"] = {"evidence_scope": "live_inventory_only", "projects": before, "known_replacements": ["P0 Medusa clone uses an emptyDir PostgreSQL database with trust auth and runtime-generated JWT/cookie secrets.", "P0 Medusa clone omits worker/admin UI/ingress and uses synthetic-empty data.", "P0 L2 target contains only the deployed Medusa Redis image and no application backend."], "conclusion_limit": "These samples cannot be generalized to all targets or full business fidelity; P3 approved transaction Oracles remain required."}
        adopted_profile = json.loads((repository_root / "projects" / "chaosatlas-apps" / "immich" / "profile.json").read_text(encoding="utf-8-sig"))
        adopted_plan = planner.plan(profile=adopted_profile, capability=_capability("pod_kill", "L1"), target={"node_id": "acceptance-target"})
        summary["stages"].append(_execute_stage(manager, "l1-adopted-immich", "real_existing_replica_lifecycle_no_business", adopted_plan))
        summary["stages"].append(_cross_process_cli_acceptance(repository_root, output_root, adopted_plan))
        smoke_profile = {"project_id": "acceptance-pause-smoke", "project_commit": "acceptance", "runtime_contract": {"kube_context": context}, "isolation": {"synthetic_data_only": True, "l1": {"mode": "ephemeral-app-clone", "ready_timeout_s": 180, "blueprint": {"resources": [_pause_workload("pause-smoke")]}}}}
        summary["stages"].append(_execute_stage(manager, "l1-pause-infrastructure-smoke", "synthetic_infrastructure_smoke_not_application", planner.plan(profile=smoke_profile, capability=_capability("pod_kill", "L1"))))
        medusa_profile = {"project_id": "medusa-p0-clone", "project_commit": "2.20.1", "runtime_contract": {"kube_context": context}, "isolation": {"synthetic_data_only": True, "l1": {"mode": "ephemeral-app-clone", "ready_timeout_s": 360, "resource_budget": {"cpu": "3", "memory": "4Gi", "pods": 12}, "blueprint": _medusa_blueprint()}}}
        summary["stages"].append(_execute_stage(manager, "l1-medusa-real-application-clone", "real_application_subset_health_no_transaction_oracle", planner.plan(profile=medusa_profile, capability=_capability("pod_kill", "L1")), lambda lease: _verify_medusa_clone(context, lease)))
        l2_profile = {"project_id": "medusa-redis-p0-target", "project_commit": "redis-6-alpine", "runtime_contract": {"kube_context": context}, "isolation": {"synthetic_data_only": True, "l2": {"mode": "ephemeral-target", "ready_timeout_s": 180, "resource_budget": {"cpu": "2", "memory": "2Gi", "pods": 8}, "blueprint": _redis_target_blueprint()}}}
        summary["stages"].append(_execute_stage(manager, "l2-medusa-redis-real-target", "real_target_binary_and_guard_effects_no_business", planner.plan(profile=l2_profile, capability=_capability("disk_pressure", "L2"), target={"node_id": "medusa-redis"}), lambda lease: _verify_l2_guards(context, lease)))
        if include_l3:
            l3_profile = {"project_id": "acceptance-l3-cluster", "project_commit": "acceptance", "isolation": {"synthetic_data_only": True, "l3": {"mode": "ephemeral-cluster", "resource_budget": {"cpu": 2, "memory": "2200mb", "disk": "10g"}, "blueprint": {"driver": "docker", "container_runtime": "containerd"}}}}
            summary["stages"].append(_execute_stage(manager, "l3-empty-minikube", "real_disposable_cluster_lifecycle_no_application", planner.plan(profile=l3_profile, capability=_capability("api_server_delay", "L3"))))
        after = _snapshot(context)
        summary["after"] = after
        summary["source_environment_unchanged"] = before == after
    except Exception as exc:
        summary["errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        for lease in store.list():
            if lease.get("state") != "released":
                try:
                    manager.recover(str(lease["lease_id"]))
                except Exception as exc:
                    summary["errors"].append(f"recovery:{lease.get('lease_id')}:{type(exc).__name__}: {exc}")
        summary["sensitive_scan_hits"] = _scan_sensitive(output_root)
        expected_count = 6 if include_l3 else 5
        stages_verified = len(summary["stages"]) == expected_count and all(item.get("status") == "verified" for item in summary["stages"])
        summary["status"] = "verified" if stages_verified and summary.get("source_environment_unchanged") is True and not summary["sensitive_scan_hits"] and not summary["errors"] else "partial"
        summary["capability_evidence"] = {"implemented": True, "offline_tests": "reported separately by pytest", "real_lifecycle": "verified" if stages_verified else "partial", "real_business": "not_assessed_pending_P3_oracle_approval", "real_fault": "not_run_in_P0"}
        summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", required=True)
    parser.add_argument("--kube-context", default="chaosatlas-apps")
    parser.add_argument("--skip-l3", action="store_true")
    args = parser.parse_args()
    result = run_acceptance(repository_root=Path(args.root), output_root=Path(args.output), context=args.kube_context, include_l3=not args.skip_l3)
    print(json.dumps({"status": result["status"], "stages": result["stages"], "summary": str(Path(args.output).resolve())}, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
