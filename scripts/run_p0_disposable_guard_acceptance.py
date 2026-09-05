"""Validate P0 application and namespace guards inside a disposable Calico cluster."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from chaosatlas.isolation.lease_store import LeaseStore
from chaosatlas.isolation.manager import IsolationManager
from chaosatlas.isolation.planner import IsolationPlanner
from chaosatlas.isolation.providers import KubernetesIsolationProvider, MinikubeIsolationProvider, ProviderRegistry
from chaosatlas.workspace import is_within
from run_isolation_acceptance import _capability, _medusa_blueprint, _redis_target_blueprint, _scan_sensitive


def _runner(kubeconfig: Path):
    def run(args: list[str], *, timeout: int = 60, input_text: str | None = None) -> tuple[int, str, str]:
        try:
            result = subprocess.run(["kubectl", "--kubeconfig", str(kubeconfig), *args], input=input_text, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
            return result.returncode, result.stdout or "", result.stderr or ""
        except subprocess.TimeoutExpired:
            return 124, "", f"TimeoutExpired after {timeout}s"
        except (OSError, subprocess.SubprocessError) as exc:
            return 125, "", f"{type(exc).__name__}: {exc}"
    return run


def _redis_profile(project: str, context: str, parent_lease_id: str, mode: str, workload_name: str) -> dict[str, Any]:
    blueprint = _redis_target_blueprint()
    if workload_name != "l2-medusa-redis":
        encoded = json.dumps(blueprint).replace("l2-medusa-redis", workload_name)
        blueprint = json.loads(encoded)
    return {
        "project_id": project,
        "project_commit": "redis-6-alpine",
        "runtime_contract": {"kube_context": context, "parent_isolation_lease_id": parent_lease_id},
        "isolation": {"synthetic_data_only": True, mode.lower(): {"mode": "ephemeral-app-clone" if mode == "L1" else "ephemeral-target", "ready_timeout_s": 300, "resource_budget": {"cpu": "2", "memory": "2Gi", "pods": 8}, "blueprint": blueprint}},
    }


def _exec(runner, context: str, namespace: str, deployment: str, args: list[str], timeout: int = 15) -> tuple[int, str, str]:
    return runner(["--context", context, "exec", "-n", namespace, f"deployment/{deployment}", "--", *args], timeout=timeout)


def _guard_checks(runner, context: str, target: dict[str, Any], probe: dict[str, Any]) -> dict[str, Any]:
    target_ns, probe_ns = str(target["target_name"]), str(probe["target_name"])
    inside_code, inside_out, inside_err = _exec(runner, context, target_ns, "l2-medusa-redis", ["redis-cli", "-h", "l2-medusa-redis", "ping"])
    before_code, before_out, _ = _exec(runner, context, probe_ns, "outside-probe", ["redis-cli", "ping"])
    outside_code, outside_out, outside_err = _exec(runner, context, probe_ns, "outside-probe", ["redis-cli", "-h", f"l2-medusa-redis.{target_ns}.svc.cluster.local", "ping"], timeout=8)
    after_code, after_out, _ = _exec(runner, context, probe_ns, "outside-probe", ["redis-cli", "ping"])
    over_budget = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "quota-rejection-probe", "namespace": target_ns, "labels": target["owner_labels"]}, "spec": {"restartPolicy": "Never", "containers": [{"name": "probe", "image": "registry.k8s.io/pause:3.10.1", "resources": {"requests": {"cpu": "3", "memory": "16Mi"}, "limits": {"cpu": "3", "memory": "64Mi"}}}]}}
    quota_code, quota_out, quota_err = runner(["--context", context, "create", "--dry-run=server", "-f", "-"], timeout=30, input_text=json.dumps(over_budget))
    checks = {
        "target_redis_ping": inside_code == 0 and "PONG" in inside_out,
        "cross_namespace_denied": outside_code != 0 and "PONG" not in outside_out,
        "outside_probe_healthy_before_after": before_code == 0 and after_code == 0 and "PONG" in before_out and "PONG" in after_out,
        "resource_quota_rejected": quota_code != 0 and "exceeded quota" in (quota_out + quota_err).lower(),
        "outside_probe_exit": outside_code,
        "outside_probe_excerpt": (outside_err or outside_out).strip()[:200],
        "quota_excerpt": (quota_err or quota_out).strip()[:240],
    }
    decisive = ("target_redis_ping", "cross_namespace_denied", "outside_probe_healthy_before_after", "resource_quota_rejected")
    return {"status": "verified" if all(checks[key] for key in decisive) else "failed", "checks": checks, "errors": [] if all(checks[key] for key in decisive) else [inside_err.strip(), "guard effect check failed"]}


def _medusa_health(runner, context: str, lease: dict[str, Any]) -> dict[str, Any]:
    code, stdout, stderr = _exec(runner, context, str(lease["target_name"]), "medusa-backend", ["node", "-e", "fetch('http://127.0.0.1:9000/health').then(async r=>{console.log(r.status,await r.text());process.exit(r.ok?0:2)}).catch(()=>process.exit(3))"], timeout=30)
    okay = code == 0 and "200" in stdout
    return {"status": "verified" if okay else "failed", "checks": {"health_http_200": okay, "response_excerpt": stdout.strip()[:160]}, "errors": [] if okay else [(stderr or stdout).strip()]}


def run(*, repository_root: Path, output_root: Path) -> dict[str, Any]:
    repository_root, output_root = repository_root.resolve(), output_root.resolve()
    if is_within(output_root, repository_root):
        raise ValueError("output must be outside the repository")
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError("output must be empty")
    output_root.mkdir(parents=True, exist_ok=True)
    store = LeaseStore(output_root / "state", coordination_root=output_root / "coordination")
    l3_provider = MinikubeIsolationProvider(root=output_root / "runtime")
    planner = IsolationPlanner()
    parent_manager = IsolationManager(store=store, providers=ProviderRegistry([l3_provider]))
    summary: dict[str, Any] = {"schema_version": "chaosatlas-p0-disposable-guard-acceptance-v1", "started_at": datetime.now(timezone.utc).isoformat(), "fault_injection_performed": False, "business_transaction_executed": False, "stages": [], "errors": []}
    parent = probe = medusa = target = None
    try:
        parent_profile = {"project_id": "p0-calico-parent", "project_commit": "acceptance", "isolation": {"synthetic_data_only": True, "l3": {"mode": "ephemeral-cluster", "resource_budget": {"cpu": 4, "memory": "6144mb", "disk": "20g"}, "blueprint": {"driver": "docker", "container_runtime": "containerd", "cni": "calico", "local_image_preload": ["docker.io/library/redis:6-alpine", "docker.io/library/postgres:15-alpine", "docker.io/chaosatlas/medusa-backend:2.20.1"]}}}}
        parent = parent_manager.prepare(planner.plan(profile=parent_profile, capability=_capability("api_server_delay", "L3")), ttl_minutes=60)
        if parent["state"] != "ready":
            raise RuntimeError(parent.get("last_error") or "Calico parent cluster did not become Ready")
        kubeconfig = next(Path(item["name"]) for item in parent["resources"] if item.get("kind") == "ExternalPath" and str(item.get("name") or "").endswith(".config"))
        context = str(parent["target_name"])
        summary["parent_lease_id"] = parent["lease_id"]
        summary["parent_profile"] = context
        summary["effective_safety_boundary"] = "L3 disposable Minikube parent with Calico-enforced child namespaces"
        runner = _runner(kubeconfig)
        child_manager = IsolationManager(store=store, providers=ProviderRegistry([
            KubernetesIsolationProvider(name="kubernetes-l1", level="L1", runner=runner),
            KubernetesIsolationProvider(name="kubernetes-l2", level="L2", runner=runner),
        ]))

        probe_plan = planner.plan(profile=_redis_profile("p0-outside-probe", context, parent["lease_id"], "L1", "outside-probe"), capability=_capability("pod_kill", "L1"))
        probe = child_manager.prepare(probe_plan, ttl_minutes=45)
        if probe["state"] != "ready":
            raise RuntimeError(probe.get("last_error") or "outside probe did not become Ready")

        medusa_profile = {"project_id": "p0-medusa-calico", "project_commit": "2.20.1", "runtime_contract": {"kube_context": context, "parent_isolation_lease_id": parent["lease_id"]}, "isolation": {"synthetic_data_only": True, "l1": {"mode": "ephemeral-app-clone", "ready_timeout_s": 420, "resource_budget": {"cpu": "3", "memory": "4Gi", "pods": 12}, "blueprint": _medusa_blueprint()}}}
        medusa = child_manager.prepare(planner.plan(profile=medusa_profile, capability=_capability("pod_kill", "L1")), ttl_minutes=45)
        medusa_check = _medusa_health(runner, context, medusa) if medusa["state"] == "ready" else {"status": "failed", "errors": [str(medusa.get("last_error"))]}
        summary["stages"].append({"name": "medusa-clone-on-calico", "state": medusa["state"], "verification": medusa_check})
        medusa = child_manager.release(medusa["lease_id"])

        target_plan = planner.plan(profile=_redis_profile("p0-real-target-calico", context, parent["lease_id"], "L2", "l2-medusa-redis"), capability=_capability("disk_pressure", "L2"), target={"node_id": "medusa-redis"})
        target = child_manager.prepare(target_plan, ttl_minutes=45)
        guard_check = _guard_checks(runner, context, target, probe) if target["state"] == "ready" else {"status": "failed", "errors": [str(target.get("last_error"))]}
        summary["stages"].append({"name": "l2-real-target-calico-guards", "state": target["state"], "verification": guard_check})
        target = child_manager.release(target["lease_id"])
        probe = child_manager.release(probe["lease_id"])
    except BaseException as exc:
        summary["errors"].append(f"{type(exc).__name__}: {exc}")
        if not isinstance(exc, Exception):
            raise
    finally:
        for lease in (target, medusa, probe):
            if lease and lease.get("state") != "released":
                try:
                    IsolationManager(store=store, providers=ProviderRegistry([
                        KubernetesIsolationProvider(name="kubernetes-l1", level="L1", runner=runner),
                        KubernetesIsolationProvider(name="kubernetes-l2", level="L2", runner=runner),
                    ])).recover(str(lease["lease_id"]))
                except Exception as exc:
                    summary["errors"].append(f"child_recovery:{lease.get('lease_id')}:{exc}")
        if parent and parent.get("state") != "released":
            try:
                parent = parent_manager.recover(str(parent["lease_id"]))
            except Exception as exc:
                summary["errors"].append(f"parent_recovery:{parent.get('lease_id')}:{exc}")
        summary["parent_cleanup_state"] = parent.get("state") if parent else None
        summary["sensitive_scan_hits"] = _scan_sensitive(output_root)
        summary["status"] = "verified" if len(summary["stages"]) == 2 and all(stage.get("state") == "ready" and (stage.get("verification") or {}).get("status") == "verified" for stage in summary["stages"]) and summary.get("parent_cleanup_state") == "released" and not summary["errors"] and not summary["sensitive_scan_hits"] else "partial"
        summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        (output_root / "acceptance-summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = run(repository_root=Path(args.root), output_root=Path(args.output))
    print(json.dumps({"status": result["status"], "stages": result["stages"], "parent_cleanup_state": result["parent_cleanup_state"], "summary": str(Path(args.output).resolve())}, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
