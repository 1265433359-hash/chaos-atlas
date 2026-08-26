"""Project frozen lifecycle reports into deterministic policy replay inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "chaosatlas-policy-runtime-results-v1"
AUDIT_SCHEMA = "chaosatlas-policy-runtime-projection-audit-v1"


def _lifecycle_checks(report: dict[str, Any]) -> dict[str, bool]:
    observation = report.get("observation") or {}
    return {
        "schema": report.get("schema_version") == "unified-lifecycle-v1",
        "completed": report.get("status") == "completed",
        "baseline": (report.get("baseline") or {}).get("pass") is True,
        "injection": (report.get("injection") or {}).get("injected") is True,
        "observation": bool(observation.get("classification")),
        "recovery": (report.get("recovery") or {}).get("recovered") is True,
        "resource_recovery": (report.get("recovery") or {}).get("resource_recovered") is True,
        "cleanup": (report.get("cleanup") or {}).get("absent_confirmed") is True,
        "washout": (report.get("washout") or {}).get("stable") is True,
        "errors": not report.get("errors"),
        "eligibility": (report.get("eligibility") or {}).get("eligible") is True,
    }


def _lifecycle_complete(report: dict[str, Any]) -> bool:
    return all(_lifecycle_checks(report).values())


def _validate_source_hash(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text.lower()):
        raise ValueError("source SHA-256 must be lowercase hexadecimal")
    return text.lower()


def project_runtime_results(
    candidates: list[dict[str, Any]],
    reports: list[dict[str, Any]],
    project_id: str,
) -> dict[str, Any]:
    """Validate complete stable pairs and produce canonical replay outcomes."""
    candidate_ids: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError("candidate must be an object")
        candidate_id = str(candidate.get("candidate_id") or "")
        if not candidate_id:
            raise ValueError("candidate_id is required")
        if candidate_id in candidate_ids:
            raise ValueError(f"duplicate candidate: {candidate_id}")
        if candidate.get("project_id") not in (None, project_id):
            raise ValueError(f"candidate project mismatch: {candidate_id}")
        candidate_ids.add(candidate_id)

    grouped: dict[str, list[dict[str, Any]]] = {}
    seen_replicates: set[tuple[str, int]] = set()
    for report in reports:
        if not isinstance(report, dict):
            raise ValueError("runtime report must be an object")
        if report.get("project_id") != project_id:
            raise ValueError("project mismatch")
        candidate_id = str(report.get("mutation_id") or "")
        if candidate_id not in candidate_ids:
            raise ValueError(f"unknown candidate: {candidate_id}")
        try:
            replicate = int(report.get("replicate"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"replicate is required: {candidate_id}") from exc
        if replicate < 1:
            raise ValueError(f"replicate must be positive: {candidate_id}")
        key = (candidate_id, replicate)
        if key in seen_replicates:
            raise ValueError(f"duplicate replicate: {candidate_id}#{replicate}")
        seen_replicates.add(key)
        if not _lifecycle_complete(report):
            raise ValueError(f"lifecycle incomplete: {candidate_id}#{replicate}")
        grouped.setdefault(candidate_id, []).append(report)

    projected: list[dict[str, Any]] = []
    candidate_audits: list[dict[str, Any]] = []
    for candidate_id in sorted(grouped):
        rows = sorted(grouped[candidate_id], key=lambda row: int(row["replicate"]))
        if len(rows) < 2:
            raise ValueError(f"candidate requires two distinct replicates: {candidate_id}")
        classifications = [str((row.get("observation") or {}).get("classification") or "") for row in rows]
        if any(value != "weakness_observed" for value in classifications):
            raise ValueError("only weakness_observed pairs can be projected")
        source_reports = []
        for row in rows:
            source_reports.append(
                {
                    "replicate": int(row["replicate"]),
                    "source_path": row.get("_source_path"),
                    "source_sha256": _validate_source_hash(row.get("_source_sha256")),
                    "source_classification": classifications[0],
                    "lifecycle_checks": _lifecycle_checks(row),
                }
            )
        projected.append(
            {
                "candidate_id": candidate_id,
                "classification": "confirmed_weakness",
                "evidence_quality": "complete",
                "source_classification": "weakness_observed",
                "source_report_count": len(rows),
                "projection_reason": "two_or_more_complete_replicates_with_same_weakness_observed_classification",
                "source_reports": source_reports,
            }
        )
        candidate_audits.append(
            {
                "candidate_id": candidate_id,
                "replicates": [int(row["replicate"]) for row in rows],
                "classification": "confirmed_weakness",
                "source_classifications": classifications,
                "lifecycle_complete": True,
            }
        )

    return {
        "runtime_results": projected,
        "audit": {
            "schema_version": AUDIT_SCHEMA,
            "project_id": project_id,
            "projected_candidate_count": len(projected),
            "source_report_count": sum(len(rows) for rows in grouped.values()),
            "candidate_audits": candidate_audits,
            "cluster_access": False,
            "model_called": False,
            "mutation_executed": False,
            "formal_knowledge_written": False,
        },
    }


def _load_candidates(path: Path) -> tuple[list[dict[str, Any]], str]:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8-sig"))
    if isinstance(payload, dict):
        payload = payload.get("candidates")
    if not isinstance(payload, list):
        raise ValueError("candidate pool must be a JSON list or candidates envelope")
    return payload, hashlib.sha256(raw).hexdigest()


def _load_reports(root: Path) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for path in sorted(root.rglob("rep-*.json")):
        raw = path.read_bytes()
        report = json.loads(raw.decode("utf-8-sig"))
        if not isinstance(report, dict):
            raise ValueError(f"runtime report must be an object: {path}")
        report["_source_path"] = path.as_posix()
        report["_source_sha256"] = hashlib.sha256(raw).hexdigest()
        reports.append(report)
    if not reports:
        raise ValueError(f"no rep-*.json reports found under {root}")
    return reports


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--project-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    args = parser.parse_args()

    candidates, candidate_pool_sha256 = _load_candidates(args.candidates)
    reports = _load_reports(args.runtime_root)
    result = project_runtime_results(candidates, reports, args.project_id)
    runtime_payload = {
        "schema_version": SCHEMA,
        "project_id": args.project_id,
        "project_commit": args.project_commit,
        "candidate_pool_sha256": candidate_pool_sha256,
        "runtime_results": result["runtime_results"],
    }
    audit = {
        **result["audit"],
        "project_commit": args.project_commit,
        "candidate_pool_sha256": candidate_pool_sha256,
        "candidate_source": args.candidates.as_posix(),
        "runtime_source_root": args.runtime_root.as_posix(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.audit_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(runtime_payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    args.audit_output.write_text(json.dumps(audit, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "projected_candidate_count": audit["projected_candidate_count"], "source_report_count": audit["source_report_count"]}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
