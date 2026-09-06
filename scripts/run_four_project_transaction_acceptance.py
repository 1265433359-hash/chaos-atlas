"""Run approved four-project H4 baseline transactions in fresh disposable leases."""

from __future__ import annotations

import argparse
import binascii
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import struct
import sys
import time
from types import SimpleNamespace
from typing import Any
import zlib

REPOSITORY = Path(__file__).resolve().parents[1]
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

from chaosatlas.isolation.lease_store import LeaseStore
from chaosatlas.isolation.manager import IsolationManager
from chaosatlas.isolation.providers import KubernetesIsolationProvider, ProviderRegistry
from chaosatlas.oracles.identity_bootstrap import BOOTSTRAPPERS, KubernetesIdentityEnvironment
from chaosatlas.oracles.recovery_ledger import RecoveryLedger
from chaosatlas.oracles.transaction_contracts import validate_transaction_contract
from chaosatlas.workspace import is_within, runs_root
from scripts.run_transaction_identity_acceptance import PROJECTS, _plan, _profile, _scan_persisted_values, _write
from scripts.run_transaction_oracle_acceptance import run as run_transaction


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)


def create_unique_png(path: Path) -> dict[str, Any]:
    """Create a tiny unique RGBA fixture, then decode and validate it separately."""
    width, height = 2, 2
    pixels = os.urandom(width * height * 4)
    rows = b"".join(b"\x00" + pixels[index:index + width * 4] for index in range(0, len(pixels), width * 4))
    payload = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(rows))
        + _chunk(b"IEND", b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return verify_png(path)


def verify_png(path: Path) -> dict[str, Any]:
    """Bounded PNG decoder used independently from the fixture encoder."""
    payload = path.read_bytes()
    if not payload.startswith(b"\x89PNG\r\n\x1a\n") or len(payload) > 1048576:
        raise ValueError("invalid bounded PNG signature")
    offset, header, compressed, ended = 8, None, bytearray(), False
    while offset < len(payload):
        if offset + 12 > len(payload):
            raise ValueError("truncated PNG chunk")
        length = struct.unpack(">I", payload[offset:offset + 4])[0]
        if length > 1048576 or offset + 12 + length > len(payload):
            raise ValueError("invalid PNG chunk length")
        kind = payload[offset + 4:offset + 8]
        data = payload[offset + 8:offset + 8 + length]
        expected_crc = struct.unpack(">I", payload[offset + 8 + length:offset + 12 + length])[0]
        if binascii.crc32(kind + data) & 0xFFFFFFFF != expected_crc:
            raise ValueError("invalid PNG chunk checksum")
        if kind == b"IHDR":
            if header is not None or length != 13:
                raise ValueError("invalid PNG header")
            header = struct.unpack(">IIBBBBB", data)
        elif kind == b"IDAT":
            compressed.extend(data)
        elif kind == b"IEND":
            ended = True
            offset += 12 + length
            break
        offset += 12 + length
    if header != (2, 2, 8, 6, 0, 0, 0) or not ended or offset != len(payload):
        raise ValueError("unexpected PNG structure")
    decoded = zlib.decompress(bytes(compressed))
    if len(decoded) != 18 or decoded[0] != 0 or decoded[9] != 0:
        raise ValueError("unexpected decoded PNG raster")
    return {
        "decoder": "stdlib-crc-zlib-rgba8-v1", "width": 2, "height": 2,
        "byte_length": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _contract(approval_dir: Path, project: str) -> tuple[Path, dict[str, Any]]:
    paths = sorted(approval_dir.glob(f"{project}-*-v3.json"))
    if len(paths) != 1:
        raise ValueError(f"exactly one frozen contract required for {project}")
    value = json.loads(paths[0].read_text(encoding="utf-8-sig"))
    errors = validate_transaction_contract(value)
    if errors or value.get("status") != "frozen":
        raise ValueError(f"invalid frozen contract for {project}")
    return paths[0], value


def _fixture_file(project_root: Path, project: str, fixtures: dict[str, Any]) -> tuple[Path, dict[str, Any] | None]:
    directory = project_root / "fixtures"
    directory.mkdir(parents=True, exist_ok=True)
    validation = None
    if project == "immich":
        validation = create_unique_png(directory / "synthetic.png")
        fixtures = {
            "synthetic_png": {"source": "file", "path": "synthetic.png"},
            "fixture_timestamp": datetime.now(timezone.utc).isoformat(),
            "fixture_sha256": validation["sha256"],
        }
    path = directory / "fixtures.json"
    _write(path, fixtures)
    return path, validation


def _transaction_command(*, contract: Path, store: Path, lease_id: str, service: str,
                         port: int, fixtures: Path, evidence: Path, run_id: str,
                         scenario: str, crash_marker: Path | None = None) -> list[str]:
    command = [
        sys.executable, str(REPOSITORY / "scripts" / "run_transaction_oracle_acceptance.py"),
        "--contract", str(contract), "--lease-store", str(store),
        "--lease-id", lease_id, "--service", service, "--port", str(port),
        "--fixtures", str(fixtures), "--evidence-root", str(evidence),
        "--run-id", run_id, "--scenario", scenario,
    ]
    if crash_marker is not None:
        command.extend(["--crash-marker", str(crash_marker)])
    return command


def _terminate_process_tree(process: subprocess.Popen[str]) -> int:
    if os.name == "nt":
        killed = subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True, text=True, timeout=30, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if killed.returncode != 0 and process.poll() is None:
            raise RuntimeError("external process-tree termination failed")
    elif process.poll() is None:
        process.terminate()
    return process.wait(timeout=30)


def _journal_write_count(path: Path) -> int:
    if not path.is_file():
        return 0
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if value.get("event") == "request" and value.get("method") != "GET":
            count += 1
    return count


def _cross_process_recovery(*, contract: Path, store: Path, lease_id: str, service: str,
                            port: int, fixtures: Path, project_root: Path,
                            run_id: str) -> dict[str, Any]:
    crash_root = project_root / "crash"
    recovery_root = project_root / "recovery"
    marker = crash_root / "crash-window.json"
    environment = dict(os.environ)
    environment["PYTHONPYCACHEPREFIX"] = str(project_root / "pycache")
    process = subprocess.Popen(
        _transaction_command(
            contract=contract, store=store, lease_id=lease_id, service=service,
            port=port, fixtures=fixtures, evidence=crash_root, run_id=run_id,
            scenario="crash-after-response", crash_marker=marker,
        ),
        cwd=str(REPOSITORY), env=environment, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    deadline = time.monotonic() + 120
    while not marker.is_file():
        if process.poll() is not None:
            output = process.stdout.read(2000) if process.stdout else ""
            raise RuntimeError("termination window was not reached: " + output[:500])
        if time.monotonic() >= deadline:
            _terminate_process_tree(process)
            raise TimeoutError("termination window evidence timed out")
        time.sleep(0.25)
    marker_value = json.loads(marker.read_text(encoding="utf-8"))
    worker_pid = marker_value.get("process_id")
    if type(worker_pid) is not int or worker_pid <= 0 or process.poll() is not None:
        _terminate_process_tree(process)
        raise RuntimeError("termination marker process identity mismatch")
    crash_exit = _terminate_process_tree(process)
    if process.stdout:
        process.stdout.close()
    before = RecoveryLedger(store.parent / "transactions").load(run_id)
    states_before = {key: value["state"] for key, value in before["operations"].items()}
    if before.get("lifecycle") != "active" or "outcome_unknown" not in states_before.values():
        raise RuntimeError("external termination did not preserve an unknown write outcome")
    recovered = subprocess.run(
        _transaction_command(
            contract=contract, store=store, lease_id=lease_id, service=service,
            port=port, fixtures=fixtures, evidence=recovery_root, run_id=run_id,
            scenario="recover",
        ),
        cwd=str(REPOSITORY), env=environment, capture_output=True, text=True,
        timeout=300, check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    summary_path = recovery_root / "acceptance-summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}
    crash_writes = _journal_write_count(crash_root / "transaction-journal.jsonl")
    recovery_writes = _journal_write_count(recovery_root / "transaction-journal.jsonl")
    observation = {
        "schema_version": "chaosatlas-cross-process-recovery-acceptance-v1",
        "status": "passed" if (
            crash_exit != 0 and recovered.returncode == 0
            and summary.get("status") == "passed"
            and crash_writes == 1 and recovery_writes == 0
        ) else "failed",
        "external_termination_confirmed": crash_exit != 0,
        "launcher_process_id": process.pid,
        "worker_process_id": worker_pid,
        "pre_recovery_lifecycle": before["lifecycle"],
        "pre_recovery_operation_states": states_before,
        "recovery_exit_code": recovered.returncode,
        "write_requests_before_termination": crash_writes,
        "write_requests_during_recovery": recovery_writes,
        "server_fault_injection_performed": False,
        "recovery_summary": summary,
    }
    _write(project_root / "cross-process-recovery-summary.json", observation)
    return observation


def run(*, repository: Path, approval_dir: Path, output: Path, context: str,
        projects: list[str], scenario: str = "baseline") -> dict[str, Any]:
    repository, approval_dir, output = repository.resolve(), approval_dir.resolve(), output.resolve()
    if scenario not in {"baseline", "response-loss", "process-recovery"}:
        raise ValueError("unsupported four-project acceptance scenario")
    external = runs_root().resolve()
    if not is_within(approval_dir, repository / "projects"):
        raise ValueError("approval directory must be under repository projects")
    if is_within(output, repository) or (output != external and external not in output.parents):
        raise ValueError(f"output must be under external runs root: {external}")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("output must be an empty directory")
    output.mkdir(parents=True, exist_ok=True)
    store = LeaseStore(output / "state")
    manager = IsolationManager(
        store=store,
        providers=ProviderRegistry([KubernetesIsolationProvider(name="kubernetes-l2", level="L2")]),
    )
    result: dict[str, Any] = {
        "schema_version": "chaosatlas-four-project-transaction-acceptance-v1",
        "started_at": datetime.now(timezone.utc).isoformat(), "context": context,
        "claim_scope": {
            "baseline": "real_business_transaction_and_oracle_self_check",
            "response-loss": "real_client_response_loss_recovery",
            "process-recovery": "real_cross_process_recovery",
        }[scenario],
        "scenario": scenario, "server_fault_injection_performed": False,
        "fault_injection_performed": False, "projects": [],
    }
    for project in projects:
        item: dict[str, Any] = {"project_id": project, "status": "failed", "errors": []}
        lease = None
        environment = None
        try:
            contract_path, contract = _contract(approval_dir, project)
            profile, revision = _profile(repository, project, context)
            if revision != contract["project_revision"]:
                raise ValueError("profile revision differs from frozen contract")
            plan = _plan(profile)
            if plan.get("status") != "ready":
                raise ValueError("transaction isolation plan is blocked")
            lease = manager.prepare(plan, ttl_minutes=90)
            item.update({"lease_id": lease["lease_id"], "namespace": lease["target_name"]})
            if lease.get("state") != "ready":
                raise RuntimeError("disposable application lease was not Ready")
            spec = PROJECTS[project]
            environment = KubernetesIdentityEnvironment(
                manager, lease["lease_id"], service=spec["service"], port=spec["port"],
            )
            environment.open()
            identity, fixtures = BOOTSTRAPPERS[project](environment)
            environment.close()
            environment = None
            fixture_path, fixture_validation = _fixture_file(output / project, project, fixtures)
            run_id = f"h4-{project}-{lease['lease_id'].removeprefix('lease-')}"
            if scenario == "process-recovery":
                transaction = _cross_process_recovery(
                    contract=contract_path, store=output / "state", lease_id=lease["lease_id"],
                    service=spec["service"], port=spec["port"], fixtures=fixture_path,
                    project_root=output / project, run_id=run_id,
                )
            else:
                transaction = run_transaction(SimpleNamespace(
                    contract=str(contract_path), lease_store=str(output / "state"),
                    lease_id=lease["lease_id"], service=spec["service"], port=spec["port"],
                    fixtures=str(fixture_path), evidence_root=str(output / project / "transaction"),
                    run_id=run_id, scenario=scenario, crash_marker=None,
                ))
            lease = manager.status(lease["lease_id"])
            item.update({
                "status": "verified" if transaction.get("status") == "passed" else "failed",
                "contract_sha256": contract["contract_sha256"], "oracle_id": contract["oracle_id"],
                "identity": identity, "fixture_validation": fixture_validation,
                "transaction_summary": transaction, "cleanup_state": lease.get("state"),
            })
        except Exception as exc:
            item["errors"].append({"reason_code": type(exc).__name__, "message": str(exc)[:300]})
        finally:
            if environment is not None:
                environment.close()
            if lease is not None:
                try:
                    current = manager.status(lease["lease_id"])
                    if current.get("state") != "released":
                        current = manager.recover(lease["lease_id"])
                    item["cleanup_state"] = current.get("state")
                    attempts = int(current.get("cleanup_attempts") or 0)
                    repeated = manager.release(lease["lease_id"])
                    item["duplicate_cleanup"] = {
                        "status": "verified" if (
                            repeated.get("state") == "released"
                            and int(repeated.get("cleanup_attempts") or 0) == attempts
                        ) else "failed",
                        "state": repeated.get("state"),
                        "cleanup_attempts_unchanged": int(repeated.get("cleanup_attempts") or 0) == attempts,
                    }
                except Exception as exc:
                    item["errors"].append({"reason_code": "cleanup_" + type(exc).__name__})
            if item.get("cleanup_state") != "released" or (item.get("duplicate_cleanup") or {}).get("status") != "verified":
                item["status"] = "failed"
            _write(output / project / "h4-project-summary.json", item)
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
    parser.add_argument("--root", type=Path, default=REPOSITORY)
    parser.add_argument("--approval-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--context", default="chaosatlas-apps")
    parser.add_argument("--project", action="append", choices=tuple(PROJECTS), dest="projects")
    parser.add_argument(
        "--scenario", choices=("baseline", "response-loss", "process-recovery"),
        default="baseline",
    )
    parser.add_argument("--approve-live", action="store_true")
    args = parser.parse_args(argv)
    if not args.approve_live:
        parser.error("--approve-live is required for real business transactions")
    summary = run(
        repository=args.root, approval_dir=args.approval_dir, output=args.output,
        context=args.context, projects=args.projects or list(PROJECTS), scenario=args.scenario,
    )
    print(json.dumps({
        "status": summary["status"],
        "project_statuses": {item["project_id"]: item["status"] for item in summary["projects"]},
        "evidence_root": str(args.output.resolve()),
    }, ensure_ascii=True))
    return 0 if summary["status"] == "verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
