"""Persistent isolation lifecycle coordinator."""

from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from chaosatlas.isolation.contracts import transition_lease, validate_plan, with_hash
from chaosatlas.isolation.lease_store import LeaseStore
from chaosatlas.isolation.providers import ProviderRegistry


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(lease_id: str, status: str, checks: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    return with_hash({"schema_version": "chaosatlas-isolation-audit-v1", "lease_id": lease_id, "status": status, "checked_at": _now().isoformat(), "checks": deepcopy(checks), "errors": [str(item) for item in errors if item]}, "audit_sha256")


class IsolationManager:
    def __init__(self, *, store: LeaseStore, providers: ProviderRegistry) -> None:
        self.store = store
        self.providers = providers

    def _new_lease(self, plan: dict[str, Any], ttl_minutes: int) -> dict[str, Any]:
        if self.store.active(project_id=str(plan["project_id"])):
            raise RuntimeError(f"project already has an active isolation lease: {plan['project_id']}")
        if plan["provider"] == "minikube-l3" and self.store.active(provider="minikube-l3"):
            raise RuntimeError("an L3 Minikube isolation lease is already active")
        if ttl_minutes < 1 or ttl_minutes > 240:
            raise ValueError("ttl_minutes must be between 1 and 240")
        lease_id = f"lease-{uuid.uuid4().hex[:16]}"
        suffix = lease_id.removeprefix("lease-")[:10]
        project = "".join(character for character in str(plan["project_id"]).lower() if character.isalnum() or character == "-")[:24].strip("-") or "project"
        target_name = f"ca-{plan['effective_isolation'].lower()}-{project}-{suffix}"
        created = _now()
        lease = {
            "schema_version": "chaosatlas-environment-lease-v1",
            "lease_id": lease_id,
            "plan_id": plan["plan_id"],
            "project_id": plan["project_id"],
            "provider": plan["provider"],
            "isolation_level": plan["effective_isolation"],
            "state": "planned",
            "created_at": created.isoformat(),
            "expires_at": (created + timedelta(minutes=ttl_minutes)).isoformat(),
            "owner_labels": {"chaosatlas.dev/managed": "true", "chaosatlas.dev/lease-id": lease_id, "chaosatlas.dev/project": str(plan["project_id"])},
            "target_name": target_name,
            "plan": deepcopy(plan),
            "resources": [],
            "external_profiles": [],
            "cleanup_attempts": 0,
            "last_error": None,
        }
        return with_hash(lease, "lease_sha256")

    def prepare(self, plan: dict[str, Any], *, ttl_minutes: int = 60) -> dict[str, Any]:
        errors = validate_plan(plan)
        if errors or plan.get("status") != "ready":
            raise ValueError("isolation plan is not executable: " + "; ".join([*errors, *list(plan.get("blockers") or [])]))
        provider = self.providers.get(str(plan["provider"]))
        if not provider.supports(plan):
            raise ValueError(f"isolation provider does not support plan: {plan['provider']}")
        with self.store.creation_lock():
            lease = self._new_lease(plan, ttl_minutes)
            self.store.save(lease, require_new=True)
        lease = transition_lease(lease, "preparing")
        self.store.save(lease)

        def mutate(action: str, payload: dict[str, Any]) -> None:
            nonlocal lease
            lease = self.store.load(lease["lease_id"])
            if action == "register_resource":
                lease["resources"].append(deepcopy(payload))
            elif action == "update_resource_uid":
                match = next((item for item in lease["resources"] if item.get("kind") == payload.get("kind") and item.get("namespace") == payload.get("namespace") and item.get("name") == payload.get("name")), None)
                if match is None:
                    raise ValueError("resource UID update has no registered identity")
                match["actual_uid"] = payload.get("actual_uid")
            elif action == "register_profile":
                lease["external_profiles"].append(deepcopy(payload))
            elif action == "update_profile":
                match = next((item for item in lease["external_profiles"] if item.get("provider") == payload.get("provider") and item.get("name") == payload.get("name")), None)
                if match is None:
                    raise ValueError("profile update has no registered identity")
                match["state"] = payload.get("state")
            else:
                raise ValueError(f"unknown lease mutation: {action}")
            lease = with_hash(lease, "lease_sha256")
            self.store.save(lease)

        try:
            preflight_errors = provider.preflight(plan)
            if preflight_errors:
                raise RuntimeError("; ".join(preflight_errors))
            provider.prepare(plan, lease, mutate)
            lease = self.store.load(lease["lease_id"])
            ready = provider.verify_ready(plan, lease)
            audit = _audit(lease["lease_id"], "ready_verified" if ready.get("status") == "verified" else "ready_blocked", ready.get("checks") or {}, list(ready.get("errors") or []))
            self.store.save_audit(audit, "ready")
            if ready.get("status") != "verified":
                raise RuntimeError("; ".join(ready.get("errors") or ["environment is not Ready"]))
            lease = transition_lease(lease, "ready")
            self.store.save(lease)
            return lease
        except Exception as exc:
            lease = self.store.load(lease["lease_id"])
            lease["last_error"] = f"{type(exc).__name__}: {exc}"
            lease = with_hash(lease, "lease_sha256")
            if lease["state"] == "preparing":
                lease = transition_lease(lease, "prepare_failed")
            self.store.save(lease)
            return self.release(lease["lease_id"])

    def status(self, lease_id: str) -> dict[str, Any]:
        return self.store.load(lease_id)

    def release(self, lease_id: str) -> dict[str, Any]:
        lease = self.store.load(lease_id)
        if lease["state"] == "released":
            return lease
        provider = self.providers.get(str(lease["provider"]))
        if lease["state"] != "releasing":
            lease = transition_lease(lease, "releasing")
        lease["cleanup_attempts"] = int(lease.get("cleanup_attempts") or 0) + 1
        lease = with_hash(lease, "lease_sha256")
        self.store.save(lease)
        try:
            cleanup = provider.cleanup(lease["plan"], lease)
        except Exception as exc:
            cleanup = {"status": "blocked", "reason": f"{type(exc).__name__}: {exc}"}
        try:
            absence = provider.verify_absent(lease["plan"], lease) if cleanup.get("status") == "released" else {"confirmed": False, "errors": [cleanup.get("reason") or "cleanup blocked"]}
        except Exception as exc:
            absence = {"confirmed": False, "errors": [f"{type(exc).__name__}: {exc}"]}
        errors = [*list(cleanup.get("errors") or []), *list(absence.get("errors") or [])]
        verified = cleanup.get("status") == "released" and absence.get("confirmed") is True
        lease = self.store.load(lease_id)
        lease = transition_lease(lease, "released" if verified else "cleanup_failed")
        if not verified:
            lease["last_error"] = "; ".join(str(item) for item in errors if item) or str(cleanup.get("reason") or "cleanup not verified")
            lease = with_hash(lease, "lease_sha256")
        self.store.save(lease)
        audit = _audit(lease_id, "cleanup_verified" if verified else "cleanup_failed", {"cleanup": cleanup, "absence": absence}, errors)
        self.store.save_audit(audit, f"cleanup-{lease['cleanup_attempts']}")
        return lease

    def recover(self, lease_id: str) -> dict[str, Any]:
        return self.release(lease_id)

    def reap_expired(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        current = now or _now()
        results = []
        for lease in self.store.list():
            if lease.get("state") == "released":
                continue
            expires = datetime.fromisoformat(str(lease["expires_at"]))
            if expires <= current:
                if lease["state"] not in {"expired", "releasing", "cleanup_failed", "prepare_failed"}:
                    lease = transition_lease(lease, "expired")
                    self.store.save(lease)
                results.append(self.release(lease["lease_id"]))
        return results
