"""Initialize and verify lease-scoped synthetic identities without business transactions."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from chaosatlas.isolation.lease_store import LeaseStore
from chaosatlas.isolation.manager import IsolationManager
from chaosatlas.isolation.planner import IsolationPlanner
from chaosatlas.isolation.providers import KubernetesIsolationProvider, ProviderRegistry
from chaosatlas.oracles.identity_bootstrap import BOOTSTRAPPERS, KubernetesIdentityEnvironment
from chaosatlas.oracles.runtime_binding import LeaseRuntime
from chaosatlas.workspace import is_within, runs_root


PROJECTS = {
    "immich": {"service": "immich-server", "port": 2283},
    "medusa": {"service": "medusa-backend", "port": 9000},
    "rocketchat": {"service": "rocketchat-rocketchat", "port": 80},
    "erpnext": {"service": "erpnext", "port": 8080},
}


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _credential_references(repository: Path, project: str) -> tuple[list[dict[str, Any]], str]:
    drafts = sorted((repository / "projects" / "chaosatlas-apps" / project / "oracle-drafts").glob("*-v3.json"))
    if len(drafts) != 1:
        raise ValueError("exactly one v3 review draft is required")
    contract = _read(drafts[0])
    return list(contract.get("credential_refs") or []), str(contract.get("contract_sha256") or "")


def _profile(repository: Path, project: str, context: str) -> tuple[dict[str, Any], str]:
    project_root = repository / "projects" / "chaosatlas-apps" / project
    source = _read(project_root / "profile.json")
    revision = str(source.get("project_commit") or "")
    blueprint = _read(project_root / "isolation" / "l2-blueprint.json")
    return {
        "project_id": project,
        "project_commit": revision,
        "runtime_contract": {"kube_context": context},
        "isolation": {
            "synthetic_data_only": True,
            "l2": {
                "mode": "ephemeral-target",
                "ready_timeout_s": 600,
                "cleanup_timeout_s": 180,
                "resource_budget": {"cpu": "8", "memory": "12Gi", "pods": "40"},
                "blueprint": blueprint,
            },
        },
    }, revision


def _plan(profile: dict[str, Any]) -> dict[str, Any]:
    return IsolationPlanner().plan(profile=profile, capability={
        "fault_id": "transaction_identity_bootstrap",
        "required_isolation": "L2",
        "capability_status": "supported",
    })


def _scan_persisted_values(root: Path) -> list[str]:
    pattern = re.compile(
        r'"(?:password|passwd|token|authorization|cookie|api[_-]?key)"\s*:\s*"'
        r'(?!<redacted>|Aa1!\$\{|(?:postgres|mongodb)://[^"$]*\$\{)[^"\r\n]+"'
        r'|-----BEGIN [A-Z ]*PRIVATE KEY-----|\bBearer\s+[A-Za-z0-9._~+/=-]{8,}',
        re.IGNORECASE,
    )
    hits = []
    for path in sorted(root.rglob("*.json")):
        if pattern.search(path.read_text(encoding="utf-8-sig", errors="replace")):
            hits.append(str(path.relative_to(root)))
    return hits


def run(*, repository: Path, output: Path, context: str, projects: list[str]) -> dict[str, Any]:
    repository, output = repository.resolve(), output.resolve()
    external = runs_root().resolve()
    if is_within(output, repository) or (output != external and external not in output.parents):
        raise ValueError(f"output must be under external runs root: {external}")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("output must be an empty directory")
    output.mkdir(parents=True, exist_ok=True)
    store = LeaseStore(output / "state")
    provider = KubernetesIsolationProvider(name="kubernetes-l2", level="L2")
    manager = IsolationManager(store=store, providers=ProviderRegistry([provider]))
    result: dict[str, Any] = {
        "schema_version": "chaosatlas-transaction-identity-acceptance-v1",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "context": context,
        "claim_scope": "real_disposable_identity_initialization_and_cleanup_only",
        "business_transaction_executed": False,
        "fault_injection_performed": False,
        "credential_values_persisted": False,
        "projects": [],
    }
    for project in projects:
        item: dict[str, Any] = {"project_id": project, "status": "failed", "errors": []}
        lease = None
        environment = None
        try:
            profile, revision = _profile(repository, project, context)
            plan = _plan(profile)
            if plan.get("status") != "ready":
                raise ValueError("identity isolation plan is blocked")
            references, contract_hash = _credential_references(repository, project)
            lease = manager.prepare(plan, ttl_minutes=90)
            item.update({"lease_id": lease.get("lease_id"), "namespace": lease.get("target_name")})
            if lease.get("state") != "ready":
                raise RuntimeError("disposable application lease was not Ready")
            spec = PROJECTS[project]
            environment = KubernetesIdentityEnvironment(
                manager, str(lease["lease_id"]), service=spec["service"], port=spec["port"],
            )
            environment.open()
            identity, fixtures = BOOTSTRAPPERS[project](environment)
            environment.close()
            environment = None
            runtime = LeaseRuntime(
                manager, str(lease["lease_id"]), service=spec["service"], port=spec["port"],
                project_revision=revision,
            )
            binding = runtime.bind_principal(references)
            if binding.get("principal_id") != identity.get("principal_id"):
                raise ValueError("bootstrap principal differs from runtime principal binding")
            audit = runtime.release()
            lease = manager.status(str(lease["lease_id"]))
            item.update({
                "status": "verified",
                "project_revision": revision,
                "review_contract_sha256": contract_hash,
                "identity": identity,
                "runtime_principal_binding": binding,
                "fixtures": fixtures,
                "cleanup_audit_sha256": audit.get("audit_sha256"),
                "cleanup_state": lease.get("state"),
            })
        except Exception as exc:
            item["errors"].append({"reason_code": type(exc).__name__, "message": str(exc)[:300]})
        finally:
            if environment is not None:
                environment.close()
            if lease and lease.get("state") != "released":
                try:
                    lease = manager.recover(str(lease["lease_id"]))
                except Exception as exc:
                    item["errors"].append({"reason_code": "cleanup_" + type(exc).__name__})
            item["cleanup_state"] = lease.get("state") if lease else item.get("cleanup_state")
            if item.get("cleanup_state") != "released":
                item["status"] = "failed"
            _write(output / project / "identity-acceptance.json", item)
            result["projects"].append(item)
    result["persisted_sensitive_value_hits"] = _scan_persisted_values(output)
    result["credential_values_persisted"] = bool(result["persisted_sensitive_value_hits"])
    result["status"] = "verified" if (
        len(result["projects"]) == len(projects)
        and all(item.get("status") == "verified" for item in result["projects"])
        and not result["credential_values_persisted"]
    ) else "partial"
    result["completed_at"] = datetime.now(timezone.utc).isoformat()
    _write(output / "acceptance-summary.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--context", default="chaosatlas-apps")
    parser.add_argument("--project", action="append", choices=tuple(PROJECTS), dest="projects")
    parser.add_argument("--approve-live", action="store_true")
    args = parser.parse_args(argv)
    if not args.approve_live:
        parser.error("--approve-live is required for real identity initialization")
    summary = run(
        repository=args.root, output=args.output, context=args.context,
        projects=args.projects or list(PROJECTS),
    )
    print(json.dumps({
        "status": summary["status"], "project_statuses": {
            item["project_id"]: item["status"] for item in summary["projects"]
        }, "evidence_root": str(args.output.resolve()),
    }, ensure_ascii=True))
    return 0 if summary["status"] == "verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
