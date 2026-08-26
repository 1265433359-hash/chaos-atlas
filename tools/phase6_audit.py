"""Phase 6 execution contract and artifact audit helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def build_execution_contract(
    profile: dict[str, Any],
    *,
    mode: str,
    approve_live: bool,
    candidate_id: str | None,
    seed: int,
) -> dict[str, Any]:
    """Build the immutable policy recorded for one orchestrator run."""

    if mode not in {"dry-run", "live"}:
        raise ValueError("mode must be dry-run or live")
    policy = profile.get("namespace_policy") or {}
    allowed = sorted(
        {
            str(namespace).strip()
            for namespace in (policy.get("allowed_namespaces") or [])
            if str(namespace).strip()
        }
    )
    selected = allowed[0] if len(allowed) == 1 else None
    live = mode == "live"
    approved = bool(live and approve_live and selected and selected in allowed)
    approval_status = "approved" if approved else ("required" if live else "not_applicable")
    recovery = profile.get("recovery") or {}
    deadline = recovery.get("deadline_s", 0)
    try:
        max_duration = max(0, int(float(deadline)))
    except (TypeError, ValueError):
        max_duration = 0
    return {
        "schema_version": "chaosatlas-phase6-execution-contract-v1",
        "project_id": str(profile.get("project_id") or ""),
        "project_commit": str(profile.get("project_commit") or ""),
        "mode": mode,
        "seed": seed,
        "candidate_id": candidate_id,
        "namespace": {
            "selected": selected,
            "allowed": allowed,
            "isolation_required": bool(policy.get("isolation_required", True)),
        },
        "approval": {
            "required": live,
            "provided": bool(approve_live),
            "status": approval_status,
        },
        "budget": {"max_candidates": 1, "max_duration_s": max_duration},
        "live_execution_allowed": approved,
    }


def build_artifact_index(root: Path) -> dict[str, Any]:
    """Return hashes for the run files, excluding mutable audit files."""

    root = Path(root)
    artifacts: list[dict[str, Any]] = []
    excluded = {"artifact_index.json", "phase6_audit.json"}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative in excluded:
            continue
        data = path.read_bytes()
        artifacts.append(
            {
                "path": relative,
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    return {
        "schema_version": "chaosatlas-artifact-index-v1",
        "root": ".",
        "artifacts": artifacts,
    }


def write_phase6_audit(
    root: Path,
    *,
    status: str,
    execution_contract: dict[str, Any],
    completed_stages: list[str],
    knowledge_base_updated: bool,
    cleanup: dict[str, Any],
) -> dict[str, Any]:
    """Persist the final Phase 6 audit and its content-addressed index."""

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    index = build_artifact_index(root)
    index_path = root / "artifact_index.json"
    index_text = json.dumps(index, indent=2, ensure_ascii=True, sort_keys=True) + "\n"
    index_path.write_text(index_text, encoding="utf-8")
    audit = {
        "schema_version": "chaosatlas-phase6-audit-v1",
        "status": status,
        "execution_contract": execution_contract,
        "completed_stages": list(completed_stages),
        "knowledge_base_updated": bool(knowledge_base_updated),
        "cleanup": cleanup,
        "artifact_index_ref": "artifact_index.json",
        "artifact_index_sha256": hashlib.sha256(index_text.encode("utf-8")).hexdigest(),
    }
    (root / "phase6_audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return audit
