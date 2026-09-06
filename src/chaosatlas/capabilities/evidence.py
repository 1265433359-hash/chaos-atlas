"""Derive capability grades from immutable external runtime artifacts."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def _read(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    return value if isinstance(value, dict) else None


def _payload(value: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    payload = value.get("payload")
    return payload if isinstance(payload, dict) else value


def _causal_digest(candidate: dict[str, Any], oracle_ids: list[str]) -> str:
    parameters = candidate.get("parameters") if isinstance(candidate.get("parameters"), dict) else {}
    identity = {
        "parameters": parameters,
        "oracle_ids": sorted({str(item) for item in oracle_ids if str(item)}),
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _valid_outer_isolation(run_dir: Path, evidence_root: Path) -> tuple[bool, str | None]:
    """Require the owning isolation lifecycle when a run is nested below one."""
    current = run_dir
    while current == evidence_root or evidence_root in current.parents:
        path = current / "isolation-lifecycle.json"
        if path.is_file():
            lifecycle = _read(path)
            valid = bool(
                lifecycle
                and lifecycle.get("status") == "verified"
                and lifecycle.get("cleanup_state") == "released"
            )
            return valid, None if valid else str(path.relative_to(evidence_root)).replace("\\", "/")
        if current == evidence_root:
            break
        current = current.parent
    return True, None


class CapabilityEvidenceIndex:
    """A secret-free lookup over valid completed live runs."""

    def __init__(self, entries: list[dict[str, Any]] | None = None, warnings: list[str] | None = None) -> None:
        self.entries = list(entries or [])
        self.warnings = list(warnings or [])

    @classmethod
    def empty(cls) -> "CapabilityEvidenceIndex":
        return cls()

    @classmethod
    def from_root(cls, root: str | Path | None) -> "CapabilityEvidenceIndex":
        if root is None:
            return cls.empty()
        evidence_root = Path(root).expanduser().resolve()
        if not evidence_root.is_dir():
            return cls(warnings=[f"evidence root is unavailable: {evidence_root}"])
        entries: list[dict[str, Any]] = []
        warnings: list[str] = []
        seen_runs: set[tuple[str, str, str, str, str]] = set()
        for summary_path in sorted(evidence_root.rglob("summary.json")):
            summary = _read(summary_path)
            if summary is None:
                warnings.append(f"invalid summary JSON: {summary_path.relative_to(evidence_root)}")
                continue
            if summary.get("status") != "live_completed":
                continue
            run_dir = summary_path.parent
            isolation_valid, isolation_ref = _valid_outer_isolation(run_dir, evidence_root)
            if not isolation_valid:
                warnings.append(f"outer isolation lifecycle is not verified: {isolation_ref}")
                continue
            cleanup = _read(run_dir / "cleanup_report.json")
            finding = _payload(_read(run_dir / "finding_report.json"))
            if not cleanup or cleanup.get("status") != "verified":
                continue
            attestation = finding.get("attestation") if isinstance(finding.get("attestation"), dict) else {}
            if attestation.get("valid") is not True:
                continue
            onboard = _payload(_read(run_dir / "onboard.json"))
            profile = onboard.get("profile") if isinstance(onboard.get("profile"), dict) else {}
            project_id = str(profile.get("project_id") or "")
            project_revision = str(profile.get("project_commit") or "")
            project_oracles = [
                str(item.get("id"))
                for item in profile.get("business_oracles") or []
                if isinstance(item, dict) and item.get("id")
            ]
            candidate_space = _payload(_read(run_dir / "candidate_space.json"))
            candidates = {
                str(item.get("candidate_id")): item
                for item in candidate_space.get("candidates") or []
                if isinstance(item, dict) and item.get("candidate_id")
            }
            for candidate_id in summary.get("selected_candidate_ids") or []:
                candidate = candidates.get(str(candidate_id))
                if not candidate:
                    warnings.append(f"selected candidate is missing from candidate_space: {summary_path.relative_to(evidence_root)}")
                    continue
                target = str(candidate.get("target") or "")
                fault_id = str(candidate.get("fault_family") or candidate.get("extension_id") or "")
                run_id = str(summary.get("run_id") or "")
                candidate_oracle = str(candidate.get("oracle_id") or "")
                oracle_ids = [candidate_oracle] if candidate_oracle else project_oracles
                parameter_digest = _causal_digest(candidate, oracle_ids)
                identity = (project_id, project_revision, target, fault_id, parameter_digest)
                dedupe = (*identity, run_id)
                if not all((project_id, target, fault_id, run_id)) or dedupe in seen_runs:
                    continue
                seen_runs.add(dedupe)
                entries.append({
                    "project_id": project_id,
                    "project_revision": project_revision,
                    "target": target,
                    "fault_id": fault_id,
                    "parameter_digest": parameter_digest,
                    "run_id": run_id,
                    "classification": finding.get("result"),
                    "evidence_ref": str(summary_path.relative_to(evidence_root)).replace("\\", "/"),
                })
        return cls(entries=entries, warnings=warnings)

    def lookup(self, *, project_id: str, project_revision: str, target: str | None, fault_id: str) -> dict[str, Any]:
        matches = [
            item for item in self.entries
            if item["project_id"] == project_id
            and item["project_revision"] == project_revision
            and item["target"] == str(target or "")
            and item["fault_id"] == fault_id
        ]
        by_parameters: dict[str, set[str]] = defaultdict(set)
        for item in matches:
            by_parameters[item["parameter_digest"]].add(item["run_id"])
        repetitions = max((len(run_ids) for run_ids in by_parameters.values()), default=0)
        grade = "E3" if repetitions >= 3 else "E2" if matches else "E0"
        return {
            "evidence_grade": grade,
            "valid_run_count": len({item["run_id"] for item in matches}),
            "stable_reproduction_count": repetitions,
            "evidence_refs": sorted({item["evidence_ref"] for item in matches}),
        }
