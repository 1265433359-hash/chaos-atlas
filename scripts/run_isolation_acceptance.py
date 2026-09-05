"""Run fault-free real lifecycle acceptance for the unified IsolationManager."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from chaosatlas.isolation.lease_store import LeaseStore
from chaosatlas.isolation.manager import IsolationManager
from chaosatlas.isolation.planner import IsolationPlanner
from chaosatlas.isolation.providers import KubernetesIsolationProvider, MinikubeIsolationProvider, ProviderRegistry
from chaosatlas.workspace import is_within


APP_NAMESPACES = (
    "chaosatlas-immich",
    "chaosatlas-erpnext",
    "chaosatlas-medusa",
    "chaosatlas-rocketchat",
)


def _run(args: list[str], timeout: int = 90) -> tuple[int, str, str]:
    try:
        result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
        return result.returncode, result.stdout or "", result.stderr or ""
    except (OSError, subprocess.SubprocessError) as exc:
        return 124, "", f"{type(exc).__name__}: {exc}"


def _kubectl_json(context: str, args: list[str]) -> dict[str, Any]:
    code, stdout, stderr = _run(["kubectl", "--context", context, *args, "-o", "json"])
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
        result[namespace] = {
            "namespace_uid": str((ns.get("metadata") or {}).get("uid") or ""),
            "pods": sorted((
                {
                    "name": str((item.get("metadata") or {}).get("name") or ""),
                    "uid": str((item.get("metadata") or {}).get("uid") or ""),
                    "restart_count": sum(int(status.get("restartCount") or 0) for status in (item.get("status") or {}).get("containerStatuses") or []),
                }
                for item in pods.get("items") or []
                if isinstance(item, dict)
            ), key=lambda item: item["name"]),
        }
    return result


def _workload(name: str) -> dict[str, Any]:
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
                        "volumeMounts": [{"name": "chaosatlas-test", "mountPath": "/chaosatlas-test"}],
                    }],
                    "volumes": [{"name": "chaosatlas-test", "emptyDir": {}}],
                },
            },
        },
    }


def _capability(fault_id: str, level: str) -> dict[str, Any]:
    return {"fault_id": fault_id, "target_id": "acceptance-target", "required_isolation": level, "capability_status": "canary_required"}


def _execute_stage(manager: IsolationManager, name: str, plan: dict[str, Any]) -> dict[str, Any]:
    stage: dict[str, Any] = {"name": name, "plan_id": plan.get("plan_id"), "plan_status": plan.get("status")}
    if plan.get("status") != "ready":
        return {**stage, "status": "blocked", "errors": list(plan.get("blockers") or [])}
    lease = manager.prepare(plan, ttl_minutes=30)
    stage.update({"lease_id": lease["lease_id"], "provider": lease["provider"], "target_name": lease["target_name"], "prepare_state": lease["state"]})
    if lease["state"] != "ready":
        return {**stage, "status": "failed", "cleanup_state": lease["state"], "errors": [str(lease.get("last_error") or "prepare did not reach Ready")]}
    released = manager.release(lease["lease_id"])
    stage.update({"cleanup_state": released["state"], "cleanup_attempts": released["cleanup_attempts"]})
    return {**stage, "status": "verified" if released["state"] == "released" else "failed", "errors": [] if released["state"] == "released" else [str(released.get("last_error") or "cleanup not verified")]}


def _scan_sensitive(root: Path) -> list[str]:
    pattern = re.compile(r'"(?:password|passwd|token|authorization|cookie|api[_-]?key|private[_-]?key)"\s*:\s*"(?!<redacted>)[^"\r\n]+"|-----BEGIN [A-Z ]*PRIVATE KEY-----|\bBearer\s+[A-Za-z0-9._~+/=-]{8,}', re.IGNORECASE)
    hits = []
    for path in sorted(root.rglob("*.json")):
        if pattern.search(path.read_text(encoding="utf-8-sig", errors="replace")):
            hits.append(str(path.relative_to(root)))
    return hits


def run_acceptance(*, repository_root: Path, output_root: Path, context: str) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    output_root = output_root.resolve()
    if is_within(output_root, repository_root):
        raise ValueError("acceptance output must be outside the repository")
    if output_root.exists() and (not output_root.is_dir() or any(output_root.iterdir())):
        raise ValueError("acceptance output must be an empty directory")
    output_root.mkdir(parents=True, exist_ok=True)
    store = LeaseStore(output_root / "state")
    manager = IsolationManager(store=store, providers=ProviderRegistry([
        KubernetesIsolationProvider(name="kubernetes-l1", level="L1"),
        KubernetesIsolationProvider(name="kubernetes-l2", level="L2"),
        MinikubeIsolationProvider(root=output_root / "runtime"),
    ]))
    planner = IsolationPlanner()
    summary: dict[str, Any] = {
        "schema_version": "chaosatlas-isolation-acceptance-v1",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "context": context,
        "fault_injection_performed": False,
        "stages": [],
        "errors": [],
    }
    summary_path = output_root / "acceptance-summary.json"
    try:
        before = _snapshot(context)
        summary["before"] = before

        adopted_profile_path = repository_root / "projects" / "chaosatlas-apps" / "immich" / "profile.json"
        adopted_profile = json.loads(adopted_profile_path.read_text(encoding="utf-8-sig"))
        adopted_plan = planner.plan(profile=adopted_profile, capability=_capability("pod_kill", "L1"), target={"node_id": "acceptance-target"})
        summary["stages"].append(_execute_stage(manager, "l1-adopted", adopted_plan))

        l1_profile = {
            "project_id": "acceptance-l1-clone",
            "project_commit": "acceptance",
            "runtime_contract": {"kube_context": context},
            "isolation": {"synthetic_data_only": True, "l1": {"mode": "ephemeral-app-clone", "ready_timeout_s": 180, "blueprint": {"resources": [_workload("l1-clone")]}}},
        }
        summary["stages"].append(_execute_stage(manager, "l1-ephemeral", planner.plan(profile=l1_profile, capability=_capability("pod_kill", "L1"))))

        l2_profile = {
            "project_id": "acceptance-l2-sandbox",
            "project_commit": "acceptance",
            "runtime_contract": {"kube_context": context},
            "isolation": {"synthetic_data_only": True, "l2": {"mode": "ephemeral-target", "ready_timeout_s": 180, "blueprint": {"resources": [
                {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "generated-test-secret"}, "type": "Opaque"},
                _workload("l2-sandbox"),
            ]}}},
        }
        summary["stages"].append(_execute_stage(manager, "l2-sandbox", planner.plan(profile=l2_profile, capability=_capability("disk_pressure", "L2"))))

        l3_profile = {
            "project_id": "acceptance-l3-cluster",
            "project_commit": "acceptance",
            "isolation": {"synthetic_data_only": True, "l3": {"mode": "ephemeral-cluster", "resource_budget": {"cpu": 2, "memory": "2200mb", "disk": "10g"}, "blueprint": {"driver": "docker", "container_runtime": "containerd"}}},
        }
        summary["stages"].append(_execute_stage(manager, "l3-minikube", planner.plan(profile=l3_profile, capability=_capability("api_server_delay", "L3"))))

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
        stages_verified = len(summary["stages"]) == 4 and all(item.get("status") == "verified" for item in summary["stages"])
        summary["status"] = "verified" if stages_verified and summary.get("source_environment_unchanged") is True and not summary["sensitive_scan_hits"] and not summary["errors"] else "partial"
        summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", required=True)
    parser.add_argument("--kube-context", default="chaosatlas-apps")
    args = parser.parse_args()
    result = run_acceptance(repository_root=Path(args.root), output_root=Path(args.output), context=args.kube_context)
    print(json.dumps({"status": result["status"], "stages": result["stages"], "summary": str(Path(args.output).resolve())}, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
