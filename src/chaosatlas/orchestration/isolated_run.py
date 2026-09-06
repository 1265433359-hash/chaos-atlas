"""Owned isolation lifecycle around one unified live RunEngine invocation."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Callable

from chaosatlas.isolation.lease_store import LeaseStore
from chaosatlas.isolation.manager import IsolationManager
from chaosatlas.isolation.planner import IsolationPlanner
from chaosatlas.isolation.providers import KubernetesIsolationProvider, MinikubeIsolationProvider, ProviderRegistry


Executor = Callable[[Path, Path, str | None], dict[str, Any]]


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _read_object(path: Path, label: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def resolve_isolation_profile(profile_path: Path, fault_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve one declared fault route and its local, non-secret blueprint."""
    profile_path = Path(profile_path).expanduser().resolve()
    profile = _read_object(profile_path, "project profile")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,79}", fault_id):
        raise ValueError("isolation fault id is invalid")
    isolation = profile.get("isolation") if isinstance(profile.get("isolation"), dict) else {}
    routes = isolation.get("fault_routes") if isinstance(isolation.get("fault_routes"), dict) else {}
    raw_route = routes.get(fault_id)
    if isinstance(raw_route, str):
        route: dict[str, Any] = {"level": raw_route}
    elif isinstance(raw_route, dict):
        route = deepcopy(raw_route)
    else:
        raise ValueError(f"profile does not declare an isolation route for {fault_id}")
    level = str(route.get("level") or "")
    if level not in {"L1", "L2", "L3"}:
        raise ValueError("isolation route level must be L1, L2 or L3")
    route["level"] = level
    config = isolation.get(level.lower()) if isinstance(isolation.get(level.lower()), dict) else {}
    blueprint = config.get("blueprint")
    blueprint_ref = config.get("blueprint_ref")
    if blueprint is not None and blueprint_ref is not None:
        raise ValueError("isolation config cannot declare both blueprint and blueprint_ref")
    if blueprint_ref is not None:
        if not isinstance(blueprint_ref, str) or not blueprint_ref or Path(blueprint_ref).is_absolute():
            raise ValueError("blueprint_ref must be a relative JSON path")
        base = profile_path.parent.resolve()
        blueprint_path = (base / blueprint_ref).resolve()
        if base != blueprint_path.parent and base not in blueprint_path.parents:
            raise ValueError("blueprint_ref escapes the project profile directory")
        if blueprint_path.suffix.lower() != ".json" or not blueprint_path.is_file():
            raise ValueError("blueprint_ref must identify an existing JSON file")
        blueprint = _read_object(blueprint_path, "isolation blueprint")
        config = {**deepcopy(config), "blueprint": blueprint}
        config.pop("blueprint_ref", None)
        profile = deepcopy(profile)
        profile["isolation"][level.lower()] = config
        route["blueprint_ref"] = str(blueprint_path)
        route["blueprint_sha256"] = hashlib.sha256(blueprint_path.read_bytes()).hexdigest()
    if not isinstance(config.get("blueprint"), dict) and level in {"L1", "L2"}:
        raise ValueError(f"{level} isolation route requires a blueprint or blueprint_ref")
    return profile, route


def materialize_runtime_profile(
    profile: dict[str, Any],
    *,
    fault_id: str,
    route: dict[str, Any],
    plan: dict[str, Any],
    lease: dict[str, Any],
) -> dict[str, Any]:
    """Bind a project contract to exactly one owned lease."""
    runtime = deepcopy(profile)
    namespace = str(lease.get("target_name") or "")
    locator = lease.get("runtime_locator") if isinstance(lease.get("runtime_locator"), dict) else {}
    kube_context = str(locator.get("kube_context") or plan.get("kube_context") or "") or None
    if not namespace:
        raise ValueError("ready isolation lease is missing its target name")
    runtime["namespace_policy"] = {
        "allowed_namespaces": [namespace],
        "isolation_required": True,
        "disposable": True,
        "cluster_profile": kube_context,
    }
    runtime["runtime_contract"] = {
        "backend": str(route.get("backend") or "kubernetes_api"),
        "kube_context": kube_context,
        "supported_fault_families": [fault_id],
        "isolation_lease_id": str(lease.get("lease_id") or ""),
        "isolation_plan_id": str(plan.get("plan_id") or ""),
    }
    runtime["fault_support"] = {
        fault_id: {
            "status": "supported",
            "reason": "bound to an owned Ready disposable isolation lease",
        }
    }
    runtime["isolation"] = {
        "synthetic_data_only": True,
        str(route["level"]).lower(): {"mode": str(plan.get("mode") or "ephemeral-target")},
    }
    return runtime


def _default_manager(state_root: Path) -> IsolationManager:
    store = LeaseStore(state_root, coordination_root=state_root / "coordination")
    providers = ProviderRegistry([
        KubernetesIsolationProvider(name="kubernetes-l1", level="L1"),
        KubernetesIsolationProvider(name="kubernetes-l2", level="L2"),
        MinikubeIsolationProvider(root=state_root / "runtime"),
    ])
    return IsolationManager(store=store, providers=providers)


def run_isolated_live(
    *,
    profile_path: Path,
    output_root: Path,
    fault_id: str,
    ttl_minutes: int,
    execute: Executor,
    manager: IsolationManager | None = None,
) -> dict[str, Any]:
    """Prepare, bind, execute and always release one isolated live run."""
    output_root = Path(output_root).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    lifecycle_path = output_root / "isolation-lifecycle.json"
    lifecycle: dict[str, Any] = {
        "schema_version": "chaosatlas-isolated-run-v1",
        "fault_id": fault_id,
        "status": "preparing",
        "injection_performed": False,
        "cleanup_state": "not_started",
        "errors": [],
    }
    lease: dict[str, Any] | None = None
    inner: dict[str, Any] = {"status": "environment_blocked"}
    active_manager = manager or _default_manager(output_root / "isolation-state")
    try:
        profile, route = resolve_isolation_profile(profile_path, fault_id)
        capability = {
            "fault_id": fault_id,
            "target_id": None,
            "required_isolation": route["level"],
            "capability_status": "canary_required",
        }
        plan = IsolationPlanner().plan(profile=profile, capability=capability)
        _write_json(output_root / "isolation-plan.json", plan)
        lifecycle.update({"plan_id": plan.get("plan_id"), "plan_status": plan.get("status")})
        if plan.get("status") != "ready":
            lifecycle["status"] = "environment_blocked"
            lifecycle["errors"] = list(plan.get("blockers") or ["isolation plan is not ready"])
            return {"status": "environment_blocked", "isolation": lifecycle}
        lease = active_manager.prepare(plan, ttl_minutes=ttl_minutes)
        lifecycle.update({
            "lease_id": lease.get("lease_id"),
            "prepare_state": lease.get("state"),
            "target_name": lease.get("target_name"),
            "provider": lease.get("provider"),
        })
        if lease.get("state") != "ready":
            lifecycle["status"] = "environment_blocked"
            lifecycle["errors"] = [str(lease.get("last_error") or "isolation lease did not become Ready")]
            return {"status": "environment_blocked", "isolation": lifecycle}
        runtime_profile = materialize_runtime_profile(
            profile,
            fault_id=fault_id,
            route=route,
            plan=plan,
            lease=lease,
        )
        runtime_profile_path = output_root / "runtime-profile.json"
        _write_json(runtime_profile_path, runtime_profile)
        lifecycle["runtime_profile_sha256"] = hashlib.sha256(runtime_profile_path.read_bytes()).hexdigest()
        lifecycle["status"] = "running"
        _write_json(lifecycle_path, lifecycle)
        context = str((lease.get("runtime_locator") or {}).get("kube_context") or plan.get("kube_context") or "") or None
        inner = execute(runtime_profile_path, output_root / "run", context)
        lifecycle["injection_performed"] = int(inner.get("executed_count") or 0) > 0
        lifecycle["inner_status"] = inner.get("status")
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        lifecycle["errors"].append(f"{type(exc).__name__}: {exc}")
        inner = {"status": "method_invalid", "error": str(exc)}
    finally:
        if lease is not None and lease.get("state") != "released":
            try:
                lease = active_manager.release(str(lease["lease_id"]))
            except Exception as exc:  # cleanup evidence must survive an executor failure
                lifecycle["errors"].append(f"cleanup:{type(exc).__name__}: {exc}")
        lifecycle["cleanup_state"] = lease.get("state") if lease else "not_required"
        cleanup_ok = lease is None or lease.get("state") == "released"
        inner_ok = str(inner.get("status") or "") in {"completed", "live_completed"}
        lifecycle["status"] = "verified" if inner_ok and cleanup_ok and not lifecycle["errors"] else "partial" if inner_ok else str(inner.get("status") or "failed")
        _write_json(lifecycle_path, lifecycle)
    result = dict(inner)
    result["isolation"] = lifecycle
    if lifecycle["cleanup_state"] not in {"released", "not_required"}:
        result["status"] = "partial" if inner_ok else "failed"
    return result
