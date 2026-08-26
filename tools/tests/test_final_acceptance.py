from __future__ import annotations

import json
from pathlib import Path

from tools.final_acceptance import build_final_acceptance


def _card(project: str, commit: str, card_id: str) -> dict:
    return {
        "schema_version": "chaosatlas-weakness-knowledge-v1",
        "id": card_id,
        "project": project,
        "project_commit": commit,
        "case_family": "native_deployment_pod_kill",
        "weakness_id": f"WS-{project}",
        "target": "front-end",
        "target_kind": "deployment",
        "classification": "availability_weakness",
        "weakness_status": "confirmed",
        "rca_status": "confirmed",
        "knowledge_status": "local_reusable",
        "mechanism_level": "service_boundary",
        "mechanism_claim": "bounded service boundary claim",
        "test_node": {"family": "pod_kill", "operation": "pod_kill"},
        "applicability_conditions": ["same project and commit"],
        "exclusion_conditions": ["cross_project_pending"],
        "evidence_runs": [
            {"run_id": "r1", "run_fingerprint": "fp1"},
            {"run_id": "r2", "run_fingerprint": "fp2"},
        ],
        "valid_reproductions": 2,
        "counter_evidence": [],
        "promotion_audit": {"allowed": True, "next_status": "local_reusable"},
        "next_evidence": ["repeat_business_oracle"],
        "stop_rule": "stop after two valid reproductions",
        "regression_intents": [{"kind": "reproduce"}, {"kind": "guard"}],
    }


def _write_card(root: Path, project: str, commit: str, card_id: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{card_id}.json").write_text(json.dumps(_card(project, commit, card_id)), encoding="utf-8")


def _write_evidence(root: Path, status: str = "improvement_verified") -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "improvement_evidence.json").write_text(
        json.dumps(
            {
                "schema_version": "chaosatlas-improvement-evidence-v1",
                "status": status,
                "same_scenario_contract": status == "improvement_verified",
                "cleanup_verified": status == "improvement_verified",
                "knowledge_update_allowed": status == "improvement_verified",
                "validation": {"valid": status == "improvement_verified", "errors": []},
            }
        ),
        encoding="utf-8",
    )


def _write_dry_run(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "summary.json").write_text(json.dumps({"status": "dry_run_ready"}), encoding="utf-8")
    (root / "finding_report.json").write_text(json.dumps({"payload": {"result": "not_run"}}), encoding="utf-8")
    (root / "rca_report.json").write_text(json.dumps({"payload": {"rca_status": "not_run"}}), encoding="utf-8")


def test_final_acceptance_passes_with_three_local_projects_and_verified_improvement(tmp_path: Path) -> None:
    projects = {}
    for index, project in enumerate(("sock-shop", "online-boutique", "P02")):
        commit = f"commit-{index}"
        root = tmp_path / project
        _write_card(root, project, commit, f"KB-{index}")
        projects[project] = {"root": root, "commit": commit}
    improvement = tmp_path / "improvement"
    _write_evidence(improvement)
    dry_runs = []
    for index in range(3):
        dry_run = tmp_path / f"dry-run-{index}"
        _write_dry_run(dry_run)
        dry_runs.append(dry_run)

    report = build_final_acceptance(
        projects=projects,
        improvement_roots=[improvement],
        dry_run_roots=dry_runs,
        policy_mode="legacy",
    )

    assert report["status"] == "passed"
    assert report["default_policy_decision"] == "retain_legacy"
    assert report["checks"]["local_project_knowledge"]["status"] == "passed"
    assert report["checks"]["improvement_retest"]["status"] == "passed"


def test_final_acceptance_rejects_foreign_commit_and_bad_improvement(tmp_path: Path) -> None:
    root = tmp_path / "sock-shop"
    _write_card(root, "sock-shop", "commit-a", "KB-sock")
    bad_improvement = tmp_path / "improvement"
    _write_evidence(bad_improvement, status="deployment_blocked")

    report = build_final_acceptance(
        projects={"sock-shop": {"root": root, "commit": "commit-b"}},
        improvement_roots=[bad_improvement],
        dry_run_roots=[],
        policy_mode="legacy",
    )

    assert report["status"] == "blocked"
    assert report["checks"]["local_project_knowledge"]["status"] == "blocked"
    assert report["checks"]["improvement_retest"]["status"] == "blocked"


def test_guarded_mode_does_not_become_default_without_explicit_gate(tmp_path: Path) -> None:
    report = build_final_acceptance(projects={}, improvement_roots=[], dry_run_roots=[], policy_mode="guarded")
    assert report["status"] == "blocked"
    assert report["default_policy_decision"] == "retain_legacy"
