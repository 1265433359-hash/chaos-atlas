"""Thin v3 transaction acceptance entry point.

It consumes a frozen, actually approved contract and a verified IsolationManager
lease. It cannot accept base URLs or credential values from an ad-hoc runtime
JSON file, and it never turns a synthetic contract into real evidence.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chaosatlas.isolation.contracts import validate_plan
from chaosatlas.isolation.lease_store import LeaseStore
from chaosatlas.isolation.manager import IsolationManager
from chaosatlas.isolation.providers import KubernetesIsolationProvider, ProviderRegistry
from chaosatlas.oracles.replay import TransactionWorkflowOracle
from chaosatlas.oracles.replay_session import ReplaySession
from chaosatlas.oracles.secret_headers import SecretHeaders
from chaosatlas.oracles.runtime_binding import LeaseRuntime
from chaosatlas.oracles.transaction_contracts import validate_transaction_contract
from chaosatlas.oracles.recovery_ledger import RecoveryLedger
from chaosatlas.workspace import is_within


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _load_fixtures(path: Path | None, specs: dict[str, Any], repository: Path) -> dict[str, Any]:
    values = _read(path) if path else {}
    for name, spec in specs.items():
        if spec.get("type") != "bytes" or name not in values:
            continue
        descriptor = values[name]
        if not isinstance(descriptor, dict) or set(descriptor) != {"source", "path"} or descriptor.get("source") != "file":
            raise ValueError("byte fixture requires an exact external file reference")
        candidate = Path(str(descriptor["path"]))
        candidate = (path.parent / candidate).resolve() if path and not candidate.is_absolute() else candidate.resolve()
        if is_within(candidate, repository) or not candidate.is_file():
            raise ValueError("byte fixture file must exist outside the repository")
        size = candidate.stat().st_size
        if size <= 0 or size > int(spec["max_length"]):
            raise ValueError("byte fixture file exceeds its approved bound")
        values[name] = candidate.read_bytes()
    return values


def run(args: argparse.Namespace) -> dict[str, Any]:
    repository = Path(__file__).resolve().parents[1]
    contract_path = Path(args.contract).resolve()
    evidence_root = Path(args.evidence_root).resolve()
    fixtures_path = Path(args.fixtures).resolve() if args.fixtures else None
    if not is_within(contract_path, repository / "projects"):
        raise ValueError("contract must be an in-project reviewed artifact")
    if is_within(evidence_root, repository) or (fixtures_path and is_within(fixtures_path, repository)):
        raise ValueError("runtime evidence and fixture inputs must stay external")
    contract = _read(contract_path)
    errors = validate_transaction_contract(contract)
    record = (contract.get("approval") or {}).get("record") or {}
    if errors or contract.get("status") != "frozen" or record.get("reviewer") == "synthetic-test-only":
        raise ValueError("only a valid frozen contract with actual human approval may run")
    fixtures = _load_fixtures(fixtures_path, contract["inputs"], repository)
    evidence_root.mkdir(parents=True, exist_ok=False)
    store = LeaseStore(args.lease_store)
    lease = store.load(args.lease_id)
    provider = KubernetesIsolationProvider(name=lease["provider"], level=lease["isolation_level"])
    manager = IsolationManager(store=store, providers=ProviderRegistry([provider]))
    runtime = LeaseRuntime(manager, args.lease_id, service=args.service, port=args.port,
                           project_revision=contract["project_revision"])
    principal_binding = runtime.bind_principal(contract["credential_refs"])
    journal_path = evidence_root / "transaction-journal.jsonl"
    def journal(event: dict[str, Any]) -> None:
        with journal_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(event, ensure_ascii=True, sort_keys=True) + "\n")
    transport = runtime.open()
    resolver = SecretHeaders(runtime, contract["credential_refs"])
    replay = ReplaySession(contract, transport, credential_headers=resolver, fixtures=fixtures,
                           runtime=runtime, ledger=RecoveryLedger(Path(args.lease_store).resolve().parent / "transactions"), journal=journal,
                           synthetic_test_only=False, environment_releaser=runtime.release)
    workflow = TransactionWorkflowOracle(replay)
    prepared = probe = cleanup = None
    try:
        prepared = workflow.prepare_fixture({"run_id": args.run_id})
        probe = workflow.probe("baseline", {"run_id": args.run_id}) if prepared.get("status") == "prepared" else {"status": "not_run"}
    finally:
        cleanup = workflow.cleanup_fixture({"run_id": args.run_id}) if replay._run_id else {"status": "not_required", "cleanup_confirmed": True}
        runtime.close()
    status = "passed" if prepared and prepared.get("status") == "prepared" and probe and probe.get("status") == "pass" and cleanup and cleanup.get("cleanup_confirmed") else "failed"
    summary = {
        "schema_version": "chaosatlas-transaction-acceptance-v2", "status": status,
        "claim_scope": "real_business_transaction", "project_id": contract["project_id"],
        "project_revision": contract["project_revision"], "oracle_id": contract["oracle_id"],
        "contract_sha256": contract["contract_sha256"], "run_id": args.run_id,
        "prepared": prepared, "baseline_probe": probe, "cleanup": cleanup,
        "principal_binding": principal_binding,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    (evidence_root / "acceptance-summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--lease-store", required=True)
    parser.add_argument("--lease-id", required=True)
    parser.add_argument("--service", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--fixtures")
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    try:
        summary = run(args)
    except Exception as exc:
        print(json.dumps({"status": "blocked", "reason_code": type(exc).__name__}, ensure_ascii=True))
        return 2
    print(json.dumps({"status": summary["status"], "project_id": summary["project_id"], "evidence_root": str(Path(args.evidence_root).resolve())}, ensure_ascii=True))
    return 0 if summary["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
