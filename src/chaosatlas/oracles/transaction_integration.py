"""Lease-bound transaction Oracle integration for the unified RunEngine."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import threading
from typing import Any

from chaosatlas.isolation.manager import IsolationManager
from chaosatlas.oracles.identity_bootstrap import BOOTSTRAPPERS, KubernetesIdentityEnvironment
from chaosatlas.oracles.runtime_binding import LeaseRuntime
from chaosatlas.oracles.secret_headers import SecretHeaders
from chaosatlas.oracles.synthetic_fixtures import build_project_fixtures
from chaosatlas.oracles.transaction_contracts import validate_transaction_contract
from chaosatlas.oracles.transaction_factory import TransactionOracleDependencies
from chaosatlas.workspace import is_within


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def load_approved_contract(approval_dir: Path, project_id: str) -> tuple[Path, dict[str, Any]]:
    """Resolve exactly one human-approved contract from one explicit batch."""
    approval_dir = Path(approval_dir).expanduser().resolve()
    projects_root = (REPOSITORY_ROOT / "projects").resolve()
    if not is_within(approval_dir, projects_root):
        raise ValueError("Oracle approval directory must be inside repository projects")
    batch = _read_object(approval_dir / "approval-batch.json")
    paths = sorted(approval_dir.glob(f"{project_id}-*-v3.json"))
    if len(paths) != 1:
        raise ValueError(f"exactly one approved v3 transaction contract required for {project_id}")
    contract = _read_object(paths[0])
    record = (contract.get("approval") or {}).get("record") or {}
    errors = validate_transaction_contract(contract)
    expected_hash = (batch.get("frozen_hashes") or {}).get(contract.get("oracle_id"))
    if (
        errors
        or contract.get("status") != "frozen"
        or record.get("decision") != "approved"
        or record.get("reviewer") in {None, "", "synthetic-test-only"}
        or expected_hash != contract.get("contract_sha256")
    ):
        raise ValueError("transaction contract is not part of the exact approved batch")
    return paths[0], contract


def bind_transaction_oracle_profile(
    profile: dict[str, Any], approval_dir: Path,
) -> dict[str, Any]:
    """Replace the probe-only Oracle with its exact frozen transaction identity."""
    runtime = deepcopy(profile)
    project_id = str(runtime.get("project_id") or "")
    _path, contract = load_approved_contract(approval_dir, project_id)
    if str(runtime.get("project_commit") or "") != contract["project_revision"]:
        raise ValueError("project profile revision differs from approved transaction contract")
    oracles = [item for item in runtime.get("business_oracles") or [] if isinstance(item, dict)]
    if len(oracles) != 1:
        raise ValueError("transaction integration requires exactly one project business Oracle")
    existing = oracles[0]
    scope = contract["runtime_scope"]
    if str(existing.get("service") or "") != scope["service"]:
        raise ValueError("profile service differs from approved transaction scope")
    existing.update({
        "id": contract["oracle_id"],
        "kind": "transaction_http",
        "approved_oracle_id": contract["oracle_id"],
        "approved_contract_sha256": contract["contract_sha256"],
        "approved_source_revision": scope["source_revision"],
        "approved_image_digest": scope["image_digest"],
        "success_contract": "frozen_transaction_v3",
    })
    runtime["business_oracles"] = [existing]
    return runtime


class LeaseTransactionDependencyFactory:
    """Build explicit transaction dependencies for one already-created lease."""

    def __init__(
        self,
        *,
        manager: IsolationManager,
        lease_id: str,
        approval_dir: Path,
        project_id: str,
    ) -> None:
        if not isinstance(manager, IsolationManager):
            raise ValueError("transaction integration requires the public IsolationManager")
        self.manager = manager
        self.lease_id = str(lease_id)
        self.approval_dir = Path(approval_dir).expanduser().resolve()
        self.project_id = str(project_id)

    def __call__(
        self,
        oracle: dict[str, Any],
        namespace: str,
        kube_context: str | None,
        output_root: Path,
    ) -> TransactionOracleDependencies:
        contract_path, contract = load_approved_contract(self.approval_dir, self.project_id)
        if (
            oracle.get("approved_oracle_id") != contract["oracle_id"]
            or oracle.get("approved_contract_sha256") != contract["contract_sha256"]
            or oracle.get("approved_image_digest") != contract["runtime_scope"]["image_digest"]
            or oracle.get("service") != contract["runtime_scope"]["service"]
        ):
            raise ValueError("runtime Oracle differs from the exact approved transaction contract")
        lease = self.manager.status(self.lease_id)
        locator = lease.get("runtime_locator") or {}
        if (
            lease.get("state") != "ready"
            or lease.get("target_name") != namespace
            or str(locator.get("kube_context") or "") != str(kube_context or "")
            or lease.get("project_id") != self.project_id
        ):
            raise ValueError("transaction dependencies differ from the ready isolation lease")

        service = str(oracle["service"])
        port = int(oracle["remote_port"])
        bootstrap_environment = KubernetesIdentityEnvironment(
            self.manager, self.lease_id, service=service, port=port,
        )
        try:
            bootstrap_environment.open()
            identity, bootstrap_fixtures = BOOTSTRAPPERS[self.project_id](bootstrap_environment)
        finally:
            bootstrap_environment.close()

        runtime = LeaseRuntime(
            self.manager,
            self.lease_id,
            service=service,
            port=port,
            project_revision=contract["project_revision"],
        )
        principal_binding = runtime.bind_principal(contract["credential_refs"])
        if principal_binding.get("principal_id") != identity.get("principal_id"):
            raise ValueError("bootstrap principal differs from lease runtime binding")
        fixture_root = Path(output_root).resolve() / "transaction-fixtures"
        fixtures, fixture_validation = build_project_fixtures(
            self.project_id, fixture_root, bootstrap_fixtures,
        )
        evidence = {
            "schema_version": "chaosatlas-transaction-runtime-binding-v1",
            "project_id": self.project_id,
            "lease_id": self.lease_id,
            "namespace": namespace,
            "kube_context": kube_context,
            "oracle_id": contract["oracle_id"],
            "contract_sha256": contract["contract_sha256"],
            "contract_ref": str(contract_path.relative_to(REPOSITORY_ROOT)).replace("\\", "/"),
            "principal_binding": principal_binding,
            "fixture_validation": fixture_validation,
            "credential_values_persisted": False,
        }
        binding_path = Path(output_root).resolve() / "transaction-runtime-binding.json"
        binding_path.parent.mkdir(parents=True, exist_ok=True)
        binding_path.write_text(
            json.dumps(evidence, indent=2, ensure_ascii=True, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        journal_path = Path(output_root).resolve() / "transaction-journal.jsonl"
        journal_lock = threading.Lock()

        def journal(event: dict[str, Any]) -> None:
            with journal_lock, journal_path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(event, ensure_ascii=True, sort_keys=True) + "\n")

        resolver = SecretHeaders(runtime, contract["credential_refs"])

        def release_environment() -> bool:
            audit = runtime.release()
            return audit.get("status") == "cleanup_verified"

        return TransactionOracleDependencies(
            runtime=runtime,
            contract=contract,
            fixtures=fixtures,
            credential_headers=resolver,
            # Keep the durable ledger at the isolation run root. Candidate
            # child paths plus a bounded 63-character action id can exceed
            # the legacy Windows MAX_PATH limit before the first lock opens.
            ledger_root=self.manager.store.root.parent / "transaction-state",
            journal=journal,
            synthetic_test_only=False,
            environment_releaser=release_environment,
        )
