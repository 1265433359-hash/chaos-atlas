"""Run guarded Kubernetes API fault canaries on disposable Medusa clones.

The harness uses IsolationManager for one owned disposable L3 parent and a fresh
L2 Medusa clone per fault, then delegates every fault lifecycle to the unified
ChaosAtlas RunEngine. Runtime artifacts stay under the external runs root.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from chaosatlas.isolation.lease_store import LeaseStore
from chaosatlas.isolation.manager import IsolationManager
from chaosatlas.isolation.planner import IsolationPlanner
from chaosatlas.isolation.providers import KubernetesIsolationProvider, MinikubeIsolationProvider, ProviderRegistry
from chaosatlas.workspace import is_within, runs_root
from scripts.run_isolation_acceptance import _capability, _medusa_blueprint, _scan_sensitive
from scripts.runtime_env import runtime_env


FAULTS = ("secret_rotation", "image_pull_failure", "pod_unschedulable")


def _runner(kubeconfig: Path):
    def run(args: list[str], *, timeout: int = 60, input_text: str | None = None) -> tuple[int, str, str]:
        try:
            result = subprocess.run(
                ["kubectl", "--kubeconfig", str(kubeconfig), *args],
                input=input_text,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
            return result.returncode, result.stdout or "", result.stderr or ""
        except subprocess.TimeoutExpired:
            return 124, "", f"TimeoutExpired after {timeout}s"
        except (OSError, subprocess.SubprocessError) as exc:
            return 125, "", f"{type(exc).__name__}: {exc}"

    return run


def _runtime_profile(*, namespace: str, context: str, family: str, project_revision: str) -> dict[str, Any]:
    if family not in FAULTS:
        raise ValueError(f"unsupported disposable Kubernetes API canary: {family}")
    defaults: dict[str, Any] = {}
    if family == "secret_rotation":
        defaults = {"secret_name": "medusa-runtime-secrets", "key": "jwt-secret"}
    elif family == "image_pull_failure":
        defaults = {"image": "chaosatlas.invalid/not-found:test"}
    else:
        defaults = {"node_selector_key": "chaosatlas.invalid/never", "node_selector_value": "true"}
    return {
        "schema_version": "chaosatlas-project-profile-v1",
        "project_id": "medusa",
        "project_commit": project_revision,
        "revision_kind": "digest",
        "source": {
            "manifest_roots": ["projects/chaosatlas-apps/k8s"],
            "source_roots": ["projects/chaosatlas-apps/medusa/medusa", "projects/chaosatlas-apps/k8s"],
        },
        "namespace_policy": {
            "allowed_namespaces": [namespace],
            "isolation_required": True,
            "disposable": True,
            "cluster_profile": context,
        },
        "isolation": {"synthetic_data_only": True, "l2": {"mode": "ephemeral-target"}},
        "business_oracles": [{
            "id": "medusa-disposable-health",
            "kind": "http",
            "service": "medusa-backend",
            "remote_port": 9000,
            "entrypoint": "/health",
            "expected_status": 200,
            "expected_body": "OK",
            "success_contract": "http_200_body_contains_OK",
            "timeout_s": 5,
            "count": 3,
            "baseline_retry_window_s": 30,
            "observation_window_s": 30,
            "probe_retry_interval_s": 1,
        }],
        "observability": {"logs": {"provider": "kubectl", "required": True}, "events": {"provider": "kubectl", "required": True}},
        "recovery": {"deadline_s": 180, "require_business_probe": True, "require_cleanup": True},
        "cleanup": {"owner": "chaosatlas", "must_be_empty": True},
        "sensitive_data_policy": {"redact_fields": ["password", "secret", "token", "authorization", "cookie"], "allow_redacted_placeholders": True},
        "runtime_contract": {"backend": "kubernetes_api", "kube_context": context, "supported_fault_families": [family]},
        "fault_support": {family: {"status": "supported", "reason": "owned disposable L2 canary target"}},
        "fault_defaults": {family: defaults},
    }


def _summarize_run(run_root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"verified": False, "status": "missing", "attestation_valid": False, "mechanism": None, "errors": []}
    try:
        batch = json.loads((run_root / "batch_summary.json").read_text(encoding="utf-8-sig"))
        item = (batch.get("results") or [None])[0]
        item_root = Path(str(item.get("output"))) if isinstance(item, dict) and item.get("output") else None
        if item_root is None:
            raise ValueError("batch summary has no result output")
        summary = json.loads((item_root / "summary.json").read_text(encoding="utf-8-sig"))
        evidence_files = sorted((item_root / "runtime" / "business").glob("*.json"))
        if not evidence_files:
            raise ValueError("runtime business evidence is missing")
        evidence = json.loads(evidence_files[0].read_text(encoding="utf-8-sig"))
        mechanism_files = sorted((item_root / "runtime" / "kubernetes" / "mechanism").glob("*.json"))
        mechanism_evidence = json.loads(mechanism_files[0].read_text(encoding="utf-8-sig")) if mechanism_files else {}
        attestation = evidence.get("attestation") if isinstance(evidence.get("attestation"), dict) else {}
        injection = evidence.get("injection") if isinstance(evidence.get("injection"), dict) else {}
        confirmation = mechanism_evidence.get("injection_confirmation") if isinstance(mechanism_evidence.get("injection_confirmation"), dict) else (injection.get("confirmation") if isinstance(injection.get("confirmation"), dict) else {})
        recovery = evidence.get("recovery") if isinstance(evidence.get("recovery"), dict) else {}
        cleanup = evidence.get("cleanup") if isinstance(evidence.get("cleanup"), dict) else {}
        result.update({
            "status": str(summary.get("status") or "unknown"),
            "run_id": summary.get("run_id"),
            "item_output": str(item_root),
            "evidence_ref": str(evidence_files[0]),
            "attestation_valid": attestation.get("valid") is True,
            "mechanism": confirmation.get("mechanism"),
            "injection_confirmed": confirmation.get("confirmed") is True or mechanism_evidence.get("injection_confirmed") is True,
            "recovery_confirmed": recovery.get("confirmed") is True,
            "cleanup_confirmed": bool(cleanup.get("confirmed") or cleanup.get("verified")),
        })
        result["verified"] = all((
            result["status"] == "live_completed",
            result["attestation_valid"],
            result["injection_confirmed"],
            result["recovery_confirmed"],
            result["cleanup_confirmed"],
        ))
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        result["errors"].append(f"{type(exc).__name__}: {exc}")
    return result


def _child_profile(context: str, parent_lease_id: str, revision: str) -> dict[str, Any]:
    return {
        "project_id": "medusa-kubernetes-api-canary",
        "project_commit": revision,
        "runtime_contract": {"kube_context": context, "parent_isolation_lease_id": parent_lease_id},
        "isolation": {
            "synthetic_data_only": True,
            "l2": {
                "mode": "ephemeral-target",
                "ready_timeout_s": 420,
                "resource_budget": {"cpu": "3", "memory": "4Gi", "pods": 12},
                "blueprint": _medusa_blueprint(),
            },
        },
    }


def run(*, repository_root: Path, output_root: Path, families: list[str], runtime_proxy: str | None = None) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    output_root = output_root.resolve()
    external = runs_root().resolve()
    if is_within(output_root, repository_root) or (output_root != external and external not in output_root.parents):
        raise ValueError(f"output must be under external runs root: {external}")
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError("output must be empty")
    invalid = sorted(set(families) - set(FAULTS))
    if invalid:
        raise ValueError("unsupported faults: " + ", ".join(invalid))
    output_root.mkdir(parents=True, exist_ok=True)
    source_profile = json.loads((repository_root / "projects" / "chaosatlas-apps" / "medusa" / "profile.json").read_text(encoding="utf-8"))
    revision = str(source_profile["project_commit"])
    store = LeaseStore(output_root / "state", coordination_root=output_root / "coordination")
    parent_manager = IsolationManager(store=store, providers=ProviderRegistry([MinikubeIsolationProvider(root=output_root / "runtime")]))
    planner = IsolationPlanner()
    summary: dict[str, Any] = {
        "schema_version": "chaosatlas-kubernetes-api-disposable-canary-v1",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "project_id": "medusa",
        "project_revision": revision,
        "claim_scope": "mechanism_and_health_oracle_only",
        "effective_safety_boundary": "owned disposable L3 Minikube parent with per-fault L2 child namespaces",
        "business_transaction_executed": False,
        "faults": [],
        "errors": [],
    }
    parent = child = None
    child_manager: IsolationManager | None = None
    try:
        parent_blueprint: dict[str, Any] = {
            "driver": "docker",
            "container_runtime": "docker" if runtime_proxy else "containerd",
            "local_image_preload": [
                "docker.io/library/redis:6-alpine",
                "docker.io/library/postgres:15-alpine",
                "docker.io/chaosatlas/medusa-backend:2.20.1",
            ],
        }
        if runtime_proxy:
            parent_blueprint["runtime_proxy"] = {
                "HTTP_PROXY": runtime_proxy,
                "HTTPS_PROXY": runtime_proxy,
                "NO_PROXY": "127.0.0.1,localhost,10.0.0.0/8,192.168.0.0/16,.svc,.cluster.local",
            }
        parent_profile = {
            "project_id": "medusa-kubernetes-api-parent",
            "project_commit": revision,
            "isolation": {
                "synthetic_data_only": True,
                "l3": {
                    "mode": "ephemeral-cluster",
                    "resource_budget": {"cpu": 4, "memory": "6144mb", "disk": "20g"},
                    "blueprint": parent_blueprint,
                },
            },
        }
        parent = parent_manager.prepare(planner.plan(profile=parent_profile, capability=_capability("api_server_delay", "L3")), ttl_minutes=90)
        if parent.get("state") != "ready":
            raise RuntimeError(parent.get("last_error") or "disposable parent was not Ready")
        kubeconfig = next(Path(item["name"]) for item in parent["resources"] if item.get("kind") == "ExternalPath" and str(item.get("name") or "").endswith(".config"))
        context = str(parent["target_name"])
        runner = _runner(kubeconfig)
        child_manager = IsolationManager(store=store, providers=ProviderRegistry([KubernetesIsolationProvider(name="kubernetes-l2", level="L2", runner=runner)]))
        for family in families:
            record: dict[str, Any] = {"fault_id": family, "verified": False, "errors": []}
            try:
                plan = planner.plan(profile=_child_profile(context, str(parent["lease_id"]), revision), capability=_capability(family, "L2"))
                child = child_manager.prepare(plan, ttl_minutes=60)
                record["lease_id"] = child.get("lease_id")
                record["namespace"] = child.get("target_name")
                if child.get("state") != "ready":
                    raise RuntimeError(child.get("last_error") or "disposable Medusa clone was not Ready")
                fault_root = output_root / family
                fault_root.mkdir(parents=True, exist_ok=True)
                profile_path = fault_root / "profile.json"
                profile_path.write_text(json.dumps(_runtime_profile(namespace=str(child["target_name"]), context=context, family=family, project_revision=revision), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                run_root = fault_root / "run"
                env = runtime_env()
                env["KUBECONFIG"] = str(kubeconfig)
                command = [
                    sys.executable, str(repository_root / "tools" / "chaosatlas.py"), "run",
                    "--profile", str(profile_path), "--mode", "live", "--approve-live",
                    "--kube-context", context, "--output", str(run_root), "--seed", "20260906",
                    "--candidate-id", f"server:deployment:medusa:medusa-backend:{family}",
                ]
                completed = subprocess.run(command, cwd=str(repository_root), env=env, check=False)
                record["run_exit_code"] = completed.returncode
                record.update(_summarize_run(run_root))
            except Exception as exc:
                record["errors"].append(f"{type(exc).__name__}: {exc}")
            finally:
                if child and child.get("state") != "released" and child_manager is not None:
                    try:
                        child = child_manager.release(str(child["lease_id"]))
                    except Exception as exc:
                        record["errors"].append(f"child_release:{type(exc).__name__}: {exc}")
                record["lease_cleanup_state"] = child.get("state") if child else None
                record["verified"] = bool(record.get("verified") and record.get("run_exit_code") == 0 and record.get("lease_cleanup_state") == "released" and not record["errors"])
                summary["faults"].append(record)
                child = None
    except BaseException as exc:
        summary["errors"].append(f"{type(exc).__name__}: {exc}")
        if not isinstance(exc, Exception):
            raise
    finally:
        if child and child_manager is not None and child.get("state") != "released":
            try:
                child_manager.recover(str(child["lease_id"]))
            except Exception as exc:
                summary["errors"].append(f"child_recovery:{type(exc).__name__}: {exc}")
        if parent and parent.get("state") != "released":
            try:
                parent = parent_manager.recover(str(parent["lease_id"]))
            except Exception as exc:
                summary["errors"].append(f"parent_recovery:{type(exc).__name__}: {exc}")
        summary["parent_cleanup_state"] = parent.get("state") if parent else None
        summary["sensitive_scan_hits"] = _scan_sensitive(output_root)
        summary["fault_injection_performed"] = any(bool(item.get("injection_confirmed")) for item in summary["faults"])
        summary["status"] = "verified" if len(summary["faults"]) == len(families) and all(item.get("verified") for item in summary["faults"]) and summary["parent_cleanup_state"] == "released" and not summary["errors"] and not summary["sensitive_scan_hits"] else "partial"
        summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        (output_root / "acceptance-summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fault", action="append", choices=FAULTS, dest="faults")
    parser.add_argument("--runtime-proxy", help="credential-free proxy origin reachable from the Minikube node")
    parser.add_argument("--approve-live", action="store_true")
    args = parser.parse_args(argv)
    if not args.approve_live:
        parser.error("--approve-live is required")
    result = run(repository_root=args.root, output_root=args.output, families=args.faults or list(FAULTS), runtime_proxy=args.runtime_proxy)
    print(json.dumps({"status": result["status"], "faults": result["faults"], "parent_cleanup_state": result["parent_cleanup_state"], "summary": str(args.output.resolve())}, ensure_ascii=False))
    return 0 if result["status"] == "verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
