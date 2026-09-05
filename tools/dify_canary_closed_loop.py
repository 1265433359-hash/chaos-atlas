"""Shared evidence, RCA and knowledge handling for standalone Dify canaries."""

from __future__ import annotations

from collections import defaultdict
import json
import hashlib
from pathlib import Path
import re
from typing import Any, Iterable

from chaosatlas.orchestration.engine import _live_lifecycle_evidence, _live_rca_projection
from tools.dify_experience_promotion import promote_confirmed_experiences
from tools.dify_adaptive_coverage import inspect_trial


def _safe_name(value: Any) -> str:
    safe = "".join(
        char if char.isalnum() or char in "._-" else "-"
        for char in str(value)
    ).strip("-") or "canary"
    if len(safe) <= 72:
        return safe
    return f"{safe[:48]}-{hashlib.sha256(str(value).encode('utf-8')).hexdigest()[:16]}"


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _observation_summary(value: Any) -> dict[str, Any]:
    payload = value if isinstance(value, dict) else {}
    return {
        "status": payload.get("status"),
        "phase": payload.get("phase"),
        "reason": payload.get("reason"),
        "sample_count": len(payload.get("samples") or []),
    }


def _classify(result: dict[str, Any]) -> str:
    observation = result.get("observation") if isinstance(result.get("observation"), dict) else {}
    status = str(observation.get("status") or result.get("outcome_status") or "")
    if status == "degraded":
        return "availability_degraded"
    if status in {"business_unreachable", "business_not_reachable"}:
        return "business_not_reachable"
    return "response_observed"


def _candidate_with_defaults(candidate: dict[str, Any]) -> dict[str, Any]:
    value = dict(candidate)
    target = str(value.get("target") or value.get("service_target") or "unknown")
    value.setdefault("candidate_id", f"canary:{_safe_name(target)}:{_safe_name(value.get('fault_family') or 'unknown')}")
    value.setdefault("target", target)
    value.setdefault("target_kind", "deployment")
    value.setdefault("fault_family", "unknown")
    value.setdefault("parameters", {})
    value.setdefault("parameter_level", "baseline")
    return value


def record_canary_trial(
    *,
    root: Path,
    profile: dict[str, Any],
    candidate: dict[str, Any],
    result: dict[str, Any],
    project_inventory: dict[str, Any] | None = None,
    repetition: int = 1,
) -> dict[str, Any]:
    """Convert one standalone canary result into the shared RCA artifact contract."""

    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    candidate = _candidate_with_defaults(candidate)
    result = dict(result)
    action_id = str(result.get("action_id") or candidate["candidate_id"])
    run_id = f"{_safe_name(candidate['candidate_id'])}-{_safe_name(action_id)}"
    inventory = {
        "project_id": profile.get("project_id"),
        "project_commit": profile.get("project_commit"),
        "namespace": profile.get("namespace_policy", {}).get("allowed_namespaces", [""])[0],
        **(project_inventory or {}),
    }
    claim_scope = f"deployment:{candidate['target']}"
    fault = {
        **result,
        "status": str(result.get("status") or "failed"),
        "outcome_status": (
            "observed"
            if result.get("status") == "executed"
            and (result.get("observation") or {}).get("status") in {"pass", "degraded"}
            else str(result.get("outcome_status") or "")
        ),
        "action_id": action_id,
        "kind": candidate.get("fault_family"),
        "target_node_id": candidate.get("node_id") or candidate["target"],
        "attestation": result.get("attestation") or {},
    }
    business_ref = f"runtime/business/{_safe_name(run_id)}.json"
    _write_json(
        root / business_ref,
        {
            "schema_version": "chaosatlas-canary-business-observation-v1",
            "claim_scope": claim_scope,
            "candidate_id": candidate["candidate_id"],
            "fault_family": candidate["fault_family"],
            "baseline": _observation_summary(result.get("baseline")),
            "observation": _observation_summary(result.get("observation")),
            "recovery": {
                "confirmed": bool((result.get("recovery") or {}).get("confirmed")),
            },
            "cleanup": {
                "confirmed": bool((result.get("cleanup") or {}).get("confirmed")),
            },
        },
    )
    evidence = _live_lifecycle_evidence(
        output_root=root,
        evidence_prefix=_safe_name(run_id),
        claim_scope=claim_scope,
        fault=fault,
    )
    updated, ingested, draft = _live_rca_projection(
        profile=profile,
        inventory=inventory,
        candidate=candidate,
        fault=fault,
        evidence_records=evidence,
        run_id=run_id,
    )
    cleanup = result.get("cleanup") if isinstance(result.get("cleanup"), dict) else {}
    cleanup_payload = {
        "schema_version": "chaosatlas-canary-cleanup-v1",
        "status": "verified" if cleanup.get("confirmed") is True else "failed",
        "cleanup_confirmed": cleanup.get("confirmed") is True,
        "errors": result.get("errors") or [],
        "claim_scope": "runtime",
    }
    _write_json(root / "cleanup_report.json", cleanup_payload)
    evidence_payload = {
        "schema_version": "chaosatlas-canary-evidence-refs-v1",
        "records": evidence,
        "available_count": len(evidence),
        "claim_scope": "runtime",
    }
    _write_json(root / "evidence_refs.json", evidence_payload)
    finding = {
        "schema_version": "chaosatlas-canary-finding-v1",
        "result": _classify(result),
        "claim_scope": "runtime",
        "candidate_id": candidate["candidate_id"],
        "target": candidate["target"],
        "fault_family": candidate["fault_family"],
        "valid_reproductions": 1 if result.get("status") == "executed" else 0,
        "attestation": result.get("attestation") or {},
        "evidence_refs": [item.get("source_ref") for item in evidence],
    }
    _write_json(root / "finding_report.json", finding)
    rca_payload = {
        **updated,
        "claim_scope": "runtime",
        "transition": ingested.get("transition"),
        "promotion": ingested.get("promotion"),
        "valid_reproductions": 1 if result.get("status") == "executed" else 0,
    }
    _write_json(root / "rca_report.json", rca_payload)
    draft["claim_scope"] = "runtime"
    draft["evidence_refs"] = evidence_payload["records"]
    _write_json(root / "knowledge_draft.json", draft)
    _write_json(
        root / "run_manifest.json",
        {
            "schema_version": "chaosatlas-canary-run-manifest-v1",
            "run_id": run_id,
            "project_id": inventory.get("project_id"),
            "project_commit": inventory.get("project_commit"),
            "candidate_id": candidate["candidate_id"],
            "claim_scope": "runtime",
        },
    )
    return {
        "action": "canary",
        "candidate_id": candidate["candidate_id"],
        "target": candidate["target"],
        "fault_family": candidate["fault_family"],
        "parameter_level": candidate.get("parameter_level", "baseline"),
        "repetition": int(repetition),
        "status": "live_completed" if result.get("status") == "executed" else str(result.get("status") or "failed"),
        "output": str(root),
        "cleanup_status": cleanup_payload["status"],
        "rca_status": rca_payload.get("rca_status"),
        "classification": finding["result"],
    }


def aggregate_canary_trials(
    *,
    rows: Iterable[dict[str, Any]],
    output_root: Path,
    knowledge_root: Path,
) -> dict[str, Any]:
    """Summarize standalone canaries and run the common promotion gate."""

    rows = [dict(row) for row in rows if isinstance(row, dict)]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        candidate_id = str(row.get("candidate_id") or "")
        if candidate_id:
            grouped[candidate_id].append(row)
    candidates: list[dict[str, Any]] = []
    for candidate_id, candidate_rows in sorted(grouped.items()):
        inspected = [inspect_trial(row) for row in candidate_rows]
        valid = [item for item in inspected if item["valid"]]
        anomalies = [item for item in valid if item["anomaly"]]
        candidates.append(
            {
                "candidate_id": candidate_id,
                "trial_count": len(candidate_rows),
                "valid_trial_count": len(valid),
                "anomaly_trial_count": len(anomalies),
                "stable_anomaly": len(anomalies) >= 3,
                "rca_statuses": sorted({item["rca_status"] for item in inspected if item["rca_status"]}),
            }
        )
    promotion = promote_confirmed_experiences(
        rows=rows,
        output_root=Path(output_root),
        knowledge_root=Path(knowledge_root),
    )
    report = {
        "schema_version": "chaosatlas-dify-canary-closed-loop-v1",
        "status": "completed",
        "trial_count": len(rows),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "promotion": promotion,
    }
    _write_json(Path(output_root) / "canary_closed_loop_report.json", report)
    return report


def repetition_from_name(value: str, default: int = 1) -> int:
    match = re.search(r"(?:^|[-_])r(\d+)(?:$|[-_])", str(value), re.IGNORECASE)
    return int(match.group(1)) if match else default
