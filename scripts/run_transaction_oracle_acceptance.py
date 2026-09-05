"""Run one approved transaction Oracle against a real HTTP origin."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chaosatlas.oracles.replay import TransactionReplayer, UrllibHttpTransport


SYNTHETIC_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDAT\x08\xd7c\xf8\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _outside_repository(path: Path, repository_root: Path) -> bool:
    try:
        path.resolve().relative_to(repository_root.resolve())
        return False
    except ValueError:
        return True


def run(args: argparse.Namespace) -> dict[str, Any]:
    repository_root = Path(__file__).resolve().parents[1]
    evidence_root = Path(args.evidence_root).resolve()
    runtime_input_path = Path(args.runtime_input).resolve()
    if not _outside_repository(evidence_root, repository_root) or not _outside_repository(runtime_input_path, repository_root):
        raise ValueError("runtime inputs and evidence must stay outside the repository")
    if evidence_root.exists() and any(evidence_root.iterdir()):
        raise ValueError("evidence root must be new or empty")
    evidence_root.mkdir(parents=True, exist_ok=True)

    contract = _read_object(Path(args.contract).resolve())
    runtime_input = _read_object(runtime_input_path)
    headers_by_ref = runtime_input.get("headers_by_ref")
    if not isinstance(headers_by_ref, dict):
        raise ValueError("runtime input requires headers_by_ref")
    fixtures = dict(runtime_input.get("fixtures") or {})
    fixtures.setdefault("synthetic_png", SYNTHETIC_PNG)
    fixtures.setdefault("fixture_sha256", hashlib.sha256(SYNTHETIC_PNG).hexdigest())
    fixtures.setdefault("fixture_timestamp", datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"))

    journal_path = evidence_root / "transaction-journal.jsonl"

    def append_journal(event: dict[str, Any]) -> None:
        with journal_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, ensure_ascii=True, sort_keys=True) + "\n")

    replayer = TransactionReplayer(
        contract,
        UrllibHttpTransport(args.base_url),
        credential_headers=lambda reference: dict(headers_by_ref.get(reference) or {}),
        fixtures=fixtures,
        journal=append_journal,
    )
    prepared: dict[str, Any] = {"status": "not_run"}
    probe: dict[str, Any] = {"status": "not_run"}
    cleanup: dict[str, Any]
    try:
        prepared = replayer.prepare(run_id=args.run_id)
        if prepared.get("status") == "prepared":
            probe = replayer.probe("baseline")
    except Exception as exc:
        probe = {"status": "failed", "error_type": type(exc).__name__}
    finally:
        cleanup = prepared.get("cleanup") if isinstance(prepared.get("cleanup"), dict) else replayer.cleanup()
    status = "passed" if prepared.get("status") == "prepared" and probe.get("status") == "pass" and cleanup.get("cleanup_confirmed") else "failed"
    summary = {
        "schema_version": "chaosatlas-transaction-acceptance-v1",
        "status": status,
        "claim_scope": "real_business_transaction",
        "project_id": contract["project_id"],
        "project_revision": contract["project_revision"],
        "oracle_id": contract["oracle_id"],
        "contract_sha256": contract["contract_sha256"],
        "run_id": args.run_id,
        "base_origin": UrllibHttpTransport(args.base_url).base_url,
        "prepared": prepared,
        "baseline_probe": probe,
        "cleanup": cleanup,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    summary_path = evidence_root / "acceptance-summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    serialized_evidence = "\n".join(path.read_text(encoding="utf-8") for path in evidence_root.glob("*.json*"))
    secret_values = [str(value) for headers in headers_by_ref.values() if isinstance(headers, dict) for value in headers.values() if len(str(value)) >= 8]
    if any(value in serialized_evidence for value in secret_values):
        summary["status"] = "failed_sensitive_evidence"
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--runtime-input", required=True)
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    try:
        summary = run(args)
    except Exception as exc:
        print(json.dumps({"status": "blocked", "error_type": type(exc).__name__}, ensure_ascii=True))
        return 2
    print(json.dumps({"status": summary["status"], "project_id": summary["project_id"], "evidence_root": str(Path(args.evidence_root).resolve())}, ensure_ascii=True))
    return 0 if summary["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
