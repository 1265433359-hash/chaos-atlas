"""Assemble a fail-closed P5 evidence package from approved plans and real runs."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

if __package__ in (None, ""):
    _root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(_root / "src"))
    sys.path.insert(0, str(_root))

from chaosatlas.experiments.p5 import (
    build_experiment_plan,
    build_p5_report,
    summarize_cost,
    validate_canary_evidence,
)
from chaosatlas.oracles.transaction_integration import load_approved_contract
from chaosatlas.workspace import is_within, runs_root


PROJECTS = ("immich", "medusa", "rocketchat", "erpnext")
_SENSITIVE_VALUE = re.compile(
    r'"(?:password|passwd|token|authorization|cookie|api[_-]?key)"\s*:\s*"'
    r'(?!<redacted>|[^"\r\n]*\$\{[A-Za-z0-9_-]+\}|(?:postgres|mongodb)://[^"$]*\$\{)[^"\r\n]+"'
    r'|-----BEGIN [A-Z ]*PRIVATE KEY-----|\bBearer\s+[A-Za-z0-9._~+/=-]{8,}',
    re.IGNORECASE,
)


def _load(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig").strip()
    if text.endswith(r"\n"):
        text = text[:-2].rstrip()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    path.write_text(body, encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _object_sha(value: dict[str, Any]) -> str:
    body = {key: item for key, item in value.items() if key not in {"created_at", "report_sha256"}}
    encoded = json.dumps(body, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _pairs(values: list[str], name: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        key, separator, item = value.partition("=")
        if not separator or key not in PROJECTS or not item.strip() or key in result:
            raise ValueError(f"invalid {name}: {value}")
        result[key] = item.strip()
    return result


def _sensitive_hits(root: Path) -> list[str]:
    hits: list[str] = []
    for path in sorted(root.rglob("*.json")):
        if _SENSITIVE_VALUE.search(path.read_text(encoding="utf-8-sig", errors="replace")):
            hits.append(str(path.relative_to(root)).replace("\\", "/"))
    return hits


def _child_root(run_root: Path, batch: dict[str, Any]) -> Path:
    rows = batch.get("results")
    if isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict):
        reported = Path(str(rows[0].get("output") or ""))
        if reported.is_dir():
            return reported
    candidates = list((run_root / "run" / "runs").glob("c-*"))
    if len(candidates) != 1:
        raise ValueError(f"exactly one child run required: {run_root}")
    return candidates[0]


def _source(path: Path) -> dict[str, str]:
    return {"path": str(path.resolve()), "sha256": _sha(path)}


def _load_canary(project_id: str, run_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    run_root = run_root.resolve()
    batch_path = run_root / "run" / "batch_summary.json"
    isolation_path = run_root / "isolation-lifecycle.json"
    batch = _load(batch_path)
    child = _child_root(run_root, batch)
    paths = {
        "batch_summary": batch_path,
        "isolation_lifecycle": isolation_path,
        "baseline_result": child / "baseline.json",
        "execute_result": child / "execute.json",
        "observe_result": child / "observe.json",
        "cleanup_report": child / "cleanup_report.json",
        "transaction_binding": child / "transaction-runtime-binding.json",
        "hypotheses": child / "hypotheses.json",
        "candidate_selection": child / "candidate_selection.json",
        "stop_decision": child / "stop_decision.json",
        "rca_report": child / "rca_report.json",
        "knowledge_consumption": child / "knowledge_consumption.json",
    }
    hits = _sensitive_hits(run_root)
    documents = {name: _load(path) for name, path in paths.items()}
    validation_names = {
        "batch_summary", "isolation_lifecycle", "baseline_result", "execute_result",
        "observe_result", "cleanup_report", "transaction_binding",
    }
    evidence = validate_canary_evidence(
        project_id=project_id,
        source_ref=str(run_root),
        sensitive_review="passed" if not hits else "failed",
        **{name: value for name, value in documents.items() if name in validation_names},
    )
    evidence["sensitive_value_hits"] = hits
    evidence["source_artifacts"] = {name: _source(path) for name, path in paths.items()}
    if not evidence["evidence_valid"]:
        raise ValueError(f"real canary rejected for {project_id}: {evidence['rejected_reason_codes']}")
    return evidence, {"child": child, **documents}


def run(
    *,
    repository: Path,
    bootstrap_root: Path,
    approval_dir: Path,
    output: Path,
    canary_roots: dict[str, str],
    blocked: dict[str, str],
) -> dict[str, Any]:
    repository, output = repository.resolve(), output.resolve()
    external = runs_root().resolve()
    if is_within(output, repository) or (output != external and external not in output.parents):
        raise ValueError(f"output must be under external runs root: {external}")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("output must be an empty directory")
    if set(canary_roots) & set(blocked):
        raise ValueError("a project cannot be both canary and blocked")
    if set(canary_roots) | set(blocked) != set(PROJECTS):
        raise ValueError("every project must have one real canary or an explicit blocker")
    output.mkdir(parents=True, exist_ok=True)

    plans: list[dict[str, Any]] = []
    contracts: dict[str, dict[str, Any]] = {}
    for project_id in PROJECTS:
        contract_path, contract = load_approved_contract(approval_dir, project_id)
        contracts[project_id] = {"path": str(contract_path.resolve()), "sha256": _sha(contract_path), "oracle_id": contract.get("oracle_id"), "contract_sha256": contract.get("contract_sha256"), "status": "frozen"}
        bootstrap = _load(bootstrap_root / f"{project_id}-41-capability-bootstrap.json")
        plan = build_experiment_plan(
            project_id=project_id,
            project_revision=str(bootstrap.get("project_revision") or "unknown"),
            capability_bootstrap=bootstrap,
            oracle_ref=contracts[project_id],
        )
        plans.append(plan)
        _write(output / "plans" / f"{project_id}-experiment-plan.json", plan)

    canaries: list[dict[str, Any]] = []
    loaded: dict[str, dict[str, Any]] = {}
    for project_id, root in canary_roots.items():
        evidence, documents = _load_canary(project_id, Path(root))
        if evidence.get("contract_sha256") != contracts[project_id].get("contract_sha256"):
            raise ValueError(f"canary Oracle hash differs from approved contract for {project_id}")
        canaries.append(evidence)
        loaded[project_id] = documents
        _write(output / "canary-evidence" / f"{project_id}.json", evidence)

    project_results: list[dict[str, Any]] = []
    for project_id in PROJECTS:
        if project_id in loaded:
            evidence = next(item for item in canaries if item["project_id"] == project_id)
            project_results.append({
                "project_id": project_id,
                "status": "canary_completed",
                "claim_scope": "real_runtime",
                "fault_id": evidence["fault_id"],
                "run_id": evidence["run_id"],
                "mechanisms": evidence["mechanisms"],
                "business_transaction": "pass",
                "anomaly_observed": evidence["anomaly_observed"],
                "issue_eligible": False,
                "evidence_ref": evidence["source_ref"],
            })
        else:
            project_results.append({
                "project_id": project_id,
                "status": "blocked",
                "claim_scope": "environment_blocker",
                "reason": blocked[project_id],
                "fault_injection_performed": False,
                "issue_eligible": False,
            })

    status_counts: dict[str, int] = {}
    for plan in plans:
        for key, value in plan["status_counts"].items():
            status_counts[key] = status_counts.get(key, 0) + int(value)
    coverage = {
        "schema_version": "chaosatlas-p5-coverage-summary-v1",
        "created_at": _utc_now(),
        "development_set": True,
        "capability_intent_denominator": sum(plan["denominators"]["all_capabilities"] for plan in plans),
        "catalog_per_project": {"core": 32, "provisional_extension": 9, "total": 41},
        "static_status_counts": dict(sorted(status_counts.items())),
        "projects_with_validated_real_canary": len(canaries),
        "project_denominator": len(PROJECTS),
        "validated_real_canary_count": len(canaries),
        "validated_mechanism_count": sum(bool(item["mechanisms"]) for item in canaries),
        "qualified_finding_count": 0,
        "issue_draft_count": 0,
        "full_runtime_matrix_executed": False,
        "scope_limit": "The 164 cells are static conclusions; only listed canaries have current unified transaction-and-fault evidence.",
        "project_results": project_results,
    }
    cost = summarize_cost(experiments=len(canaries), llm_calls=0)
    cost.update({"measurement_status": "counts_only", "llm_status": "deterministic_fallback_no_provider_credentials", "wall_time_seconds_measured": False})
    report = build_p5_report(plans=plans, canary_evidence=canaries, costs=cost, real_evidence=True)
    report.update({"formal_round_status": "completed_with_documented_blocker", "qualified_finding_count": 0, "llm_runtime_evidence": False})
    report["report_sha256"] = _object_sha(report)

    _write(output / "capability_matrix.json", {"schema_version": "chaosatlas-p5-capability-matrix-v1", "plans": plans})
    _write(output / "environment_fidelity.json", {"schema_version": "chaosatlas-p5-environment-fidelity-v1", "projects": [{"project_id": item["project_id"], "status": item["status"], "evidence_ref": item.get("evidence_ref"), "scope": "disposable_application_clone_with_approved_transaction" if item["status"] == "canary_completed" else "not_verified"} for item in project_results]})
    _write(output / "environment_lease.json", {"schema_version": "chaosatlas-p5-environment-lease-v1", "leases": [{"project_id": project_id, "status": docs["isolation_lifecycle"].get("status"), "cleanup_state": docs["isolation_lifecycle"].get("cleanup_state"), "lease_id": docs["isolation_lifecycle"].get("lease_id")} for project_id, docs in loaded.items()]})
    _write(output / "oracle_contract_ref.json", {"schema_version": "chaosatlas-p5-oracle-contract-refs-v1", "contracts": contracts})
    _write_jsonl(output / "runtime_results.jsonl", project_results)
    _write_jsonl(output / "hypotheses.jsonl", [{"project_id": item["project_id"], "status": "deterministic_fallback", "source_ref": item.get("evidence_ref"), "source_artifact": next((row["source_artifacts"]["hypotheses"] for row in canaries if row["project_id"] == item["project_id"]), None), "llm_generated": False} for item in project_results])
    _write_jsonl(output / "decisions.jsonl", [{"project_id": item["project_id"], "decision": "stop_after_no_impact_canary" if item["status"] == "canary_completed" else "stop_environment_blocked", "reason": item.get("reason", "approved bounded canary budget completed"), "candidate_selection_artifact": next((row["source_artifacts"]["candidate_selection"] for row in canaries if row["project_id"] == item["project_id"]), None), "stop_decision_artifact": next((row["source_artifacts"]["stop_decision"] for row in canaries if row["project_id"] == item["project_id"]), None)} for item in project_results])
    _write(output / "reproduction_ledger.json", {"schema_version": "chaosatlas-p5-reproduction-ledger-v1", "anomaly_count": 0, "reproduction_attempt_count": 0, "valid_reproduction_count": 0, "reason": "No anomaly crossed the reproduction trigger; no records were relabeled as reproductions."})
    _write(output / "rca.json", {"schema_version": "chaosatlas-p5-rca-summary-v1", "candidate_finding_count": 0, "confirmed_source_root_cause_count": 0, "results": [{"project_id": item["project_id"], "status": "not_triggered_no_anomaly" if item["status"] == "canary_completed" else "not_run_blocked", "source_artifact": next((row["source_artifacts"]["rca_report"] for row in canaries if row["project_id"] == item["project_id"]), None)} for item in project_results]})
    _write(output / "knowledge_snapshot_manifest.json", {"schema_version": "chaosatlas-p5-knowledge-snapshot-manifest-v1", "llm_provider": None, "policy": "deterministic_fallback", "cross_project_promotion_performed": False, "run_refs": [{"project_id": item["project_id"], "source_ref": item["source_ref"], "knowledge_consumption_artifact": item["source_artifacts"]["knowledge_consumption"]} for item in canaries]})
    _write(output / "coverage_summary.json", coverage)
    _write(output / "cost_summary.json", cost)
    _write(output / "issue-drafts" / "manifest.json", {"schema_version": "chaosatlas-p5-issue-draft-manifest-v1", "draft_count": 0, "submission_performed": False, "reason": "No anomaly satisfied the causal evidence gates."})
    _write(output / "p5-report.json", report)

    artifact_paths = sorted(path for path in output.rglob("*") if path.is_file())
    manifest = {"schema_version": "chaosatlas-p5-artifact-manifest-v1", "created_at": _utc_now(), "artifacts": [{"path": str(path.relative_to(output)).replace("\\", "/"), "sha256": _sha(path)} for path in artifact_paths]}
    _write(output / "artifact-manifest.json", manifest)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--bootstrap-root", type=Path, required=True)
    parser.add_argument("--approval-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--canary", action="append", default=[], help="project=external-run-root")
    parser.add_argument("--blocked", action="append", default=[], help="project=exact-blocker")
    args = parser.parse_args(argv)
    report = run(repository=args.repository, bootstrap_root=args.bootstrap_root, approval_dir=args.approval_dir, output=args.output, canary_roots=_pairs(args.canary, "canary"), blocked=_pairs(args.blocked, "blocked"))
    print(json.dumps({"status": report["formal_round_status"], "output": str(args.output.resolve()), "validated_real_canary_count": report["validated_real_canary_count"], "issue_draft_count": report["issue_draft_count"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
