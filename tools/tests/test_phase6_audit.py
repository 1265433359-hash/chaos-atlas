from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.phase6_audit import (
    build_artifact_index,
    build_execution_contract,
    write_phase6_audit,
)


def _profile() -> dict:
    return {
        "project_id": "demo",
        "project_commit": "a" * 40,
        "namespace_policy": {
            "allowed_namespaces": ["demo-lab"],
            "isolation_required": True,
        },
        "recovery": {"deadline_s": 120},
    }


def test_build_execution_contract_requires_approved_allowed_live_namespace() -> None:
    blocked = build_execution_contract(
        _profile(), mode="live", approve_live=False, candidate_id="candidate-1", seed=1001
    )
    assert blocked["live_execution_allowed"] is False
    assert blocked["approval"]["status"] == "required"
    assert blocked["namespace"]["selected"] == "demo-lab"

    approved = build_execution_contract(
        _profile(), mode="live", approve_live=True, candidate_id="candidate-1", seed=1001
    )
    assert approved["live_execution_allowed"] is True
    assert approved["approval"]["status"] == "approved"


def test_build_execution_contract_sets_single_candidate_budget() -> None:
    contract = build_execution_contract(
        _profile(), mode="dry-run", approve_live=False, candidate_id=None, seed=7
    )
    assert contract["budget"]["max_candidates"] == 1
    assert contract["budget"]["max_duration_s"] == 120
    assert contract["seed"] == 7


def test_build_artifact_index_hashes_relative_files_without_self_reference(tmp_path: Path) -> None:
    first = tmp_path / "run_manifest.json"
    first.write_text('{"status":"dry_run_ready"}\n', encoding="utf-8")
    nested = tmp_path / "runtime" / "observe.json"
    nested.parent.mkdir()
    nested.write_text('{"status":"pass"}\n', encoding="utf-8")

    index = build_artifact_index(tmp_path)

    assert index["schema_version"] == "chaosatlas-artifact-index-v1"
    paths = {item["path"] for item in index["artifacts"]}
    assert paths == {"run_manifest.json", "runtime/observe.json"}
    entry = next(item for item in index["artifacts"] if item["path"] == "runtime/observe.json")
    assert entry["sha256"] == hashlib.sha256(nested.read_bytes()).hexdigest()
    assert "artifact_index.json" not in paths


def test_write_phase6_audit_projects_knowledge_and_cleanup_status(tmp_path: Path) -> None:
    contract = build_execution_contract(
        _profile(), mode="dry-run", approve_live=False, candidate_id="candidate-1", seed=1001
    )
    (tmp_path / "run_manifest.json").write_text("{}\n", encoding="utf-8")

    audit = write_phase6_audit(
        tmp_path,
        status="dry_run_ready",
        execution_contract=contract,
        completed_stages=["onboard", "learn"],
        knowledge_base_updated=False,
        cleanup={"status": "verified", "errors": []},
    )

    assert audit["status"] == "dry_run_ready"
    assert audit["knowledge_base_updated"] is False
    assert audit["cleanup"]["status"] == "verified"
    assert (tmp_path / "artifact_index.json").is_file()
    assert (tmp_path / "phase6_audit.json").is_file()
    persisted = json.loads((tmp_path / "phase6_audit.json").read_text(encoding="utf-8"))
    assert persisted["artifact_index_ref"] == "artifact_index.json"
