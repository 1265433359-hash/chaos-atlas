"""Prepare the ChaosAtlas 10-project open-discovery main experiment.

This command is intentionally offline by default.  It creates an auditable
run ledger from frozen evidence, checks the project/runtime gates, qualifies
the native ChaosEater input, and writes the runtime selector map needed by the
ChaosAtlas mutation compiler.  It never reads API keys, calls an LLM, applies
Kubernetes resources, or invokes the official ChaosEater cycle.

The resulting ledger is the hand-off point for a separately approved runner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "artifacts/experiments/chaosatlas_10_projects"
PROJECTS = [f"P{index:02d}" for index in range(1, 11)]
SEEDS = [1001, 1002, 1003]
ATLAS_ARMS = ["ChaosAtlas-KB-open", "ChaosAtlas-noKB-open"]
CHAOSEATER_ARM = "ChaosEater-official"
ACTIVE_LEDGER = EXPERIMENT / "active_atlas_experiment_ledger.json"


def active_experiment_arms(include_chaoseater: bool = False) -> list[str]:
    """Return the methods allowed in the current experiment scope.

    ChaosEater remains available for a later unified comparison, but it must
    never re-enter the active ledger accidentally.
    """
    arms = list(ATLAS_ARMS)
    if include_chaoseater:
        arms.append(CHAOSEATER_ARM)
    return arms


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def project_commit(project_id: str) -> str | None:
    path = EXPERIMENT / "input_bundles" / project_id / "seed-1001" / "common.json"
    return read_json(path).get("project_commit") if path.exists() else None


def official_chaoseater_gate(project_id: str) -> dict[str, Any]:
    """Check the native ChaosEater input requirement without deploying it."""
    source = EXPERIMENT / "sources" / project_id
    skaffold = sorted(source.rglob("skaffold.y*ml")) if source.exists() else []
    return {
        "status": "pass_static" if skaffold else "environment_blocked",
        "required_input": "skaffold.yaml plus Kubernetes manifests",
        "skaffold_files": [str(path.relative_to(ROOT)).replace("\\", "/") for path in skaffold],
        "reason": None if skaffold else "frozen project evidence has no native Skaffold entrypoint",
        "runtime_invoked": False,
    }


def p02_runtime_map() -> dict[str, Any]:
    """Derive explicit Compose-node -> namespace workload selectors from P02."""
    profile = EXPERIMENT / "runtime_profiles" / "P02" / "kubernetes-static" / "static-profile.yaml"
    targets: dict[str, Any] = {}
    if not profile.exists():
        return {"schema_version": "1.0", "project_id": "P02", "namespace": "chaosatlas-p02", "targets": {}, "status": "unavailable"}
    for document in yaml.safe_load_all(profile.read_text(encoding="utf-8")):
        if not isinstance(document, dict) or document.get("kind") != "Deployment":
            continue
        metadata = document.get("metadata") or {}
        spec = document.get("spec") or {}
        selector = ((spec.get("selector") or {}).get("matchLabels") or {})
        name = str(metadata.get("name") or "")
        namespace = str(metadata.get("namespace") or "chaosatlas-p02")
        if not name or not selector:
            continue
        targets[f"compose/service/{name}"] = {
            "namespace": namespace,
            "workload": {"kind": "Deployment", "name": name},
            "selector": {str(key): str(value) for key, value in selector.items()},
            "source": "runtime_profiles/P02/kubernetes-static/static-profile.yaml",
        }
    return {
        "schema_version": "1.0",
        "project_id": "P02",
        "namespace": "chaosatlas-p02",
        "targets": targets,
        "source_sha256": sha256(profile),
        "status": "ready" if targets else "unavailable",
    }


def runtime_gate(project_id: str, matrix: dict[str, Any]) -> dict[str, Any]:
    item = (matrix.get("projects") or {}).get(project_id) or {}
    return {
        "status": item.get("gate_status", "unknown"),
        "execution_ready": bool(item.get("execution_ready")),
        "method_result_eligible": bool(item.get("method_result_eligible")),
        "namespace": item.get("namespace", f"chaosatlas-{project_id.lower()}"),
        "blocker": item.get("blocker"),
        "baseline": item.get("baseline", {}),
        "health": item.get("health", {}),
        "recovery": item.get("recovery", {}),
        "cleanup": item.get("cleanup", {}),
    }


def build_run_rows(
    project_id: str,
    gate: dict[str, Any],
    ce_gate: dict[str, Any],
    include_chaoseater: bool = False,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for seed in SEEDS:
        for arm in ATLAS_ARMS:
            bundle = EXPERIMENT / "open_discovery_bundles" / project_id / f"seed-{seed}" / f"{arm.lower()}.json"
            bundle_exists = bundle.exists()
            execution_status = (
                "ready_for_explicit_llm_consent"
                if gate["execution_ready"] and bundle_exists
                else "static_only_runtime_blocked"
                if bundle_exists
                else "static_input_missing"
            )
            rows.append({
                "project_id": project_id,
                "seed": seed,
                "arm": arm,
                "input": str(bundle.relative_to(ROOT)).replace("\\", "/") if bundle.exists() else None,
                "input_sha256": sha256(bundle) if bundle.exists() else None,
                "status": execution_status,
                "static_input_status": "frozen_bundle_ready" if bundle_exists else "missing_bundle",
                "runtime_status": gate["status"],
                "reason": None if gate["execution_ready"] and bundle_exists else (gate["blocker"] or "open-discovery bundle is missing"),
                "llm_called": False,
                "mutation_applied": False,
                "evidence_status": "not_started",
            })
        if include_chaoseater:
            official_status = (
                "ready_for_explicit_llm_consent"
                if gate["execution_ready"] and ce_gate["status"] == "pass_static"
                else "official_input_blocked"
                if ce_gate["status"] != "pass_static"
                else "static_only_runtime_blocked"
            )
            rows.append({
                "project_id": project_id,
                "seed": seed,
                "arm": CHAOSEATER_ARM,
                "input": str((EXPERIMENT / "sources" / project_id).relative_to(ROOT)).replace("\\", "/"),
                "input_sha256": None,
                "status": official_status,
                "static_input_status": ce_gate["status"],
                "runtime_status": gate["status"],
                "reason": None if gate["execution_ready"] and ce_gate["status"] == "pass_static" else (ce_gate["reason"] or gate["blocker"]),
                "llm_called": False,
                "mutation_applied": False,
                "evidence_status": "not_started",
                "improvement_isolated": True,
            })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ACTIVE_LEDGER)
    parser.add_argument("--write-runtime-maps", action="store_true", help="write static runtime maps for eligible projects")
    parser.add_argument(
        "--include-chaoseater",
        action="store_true",
        help="explicitly unfreeze the deferred ChaosEater arm for a later unified comparison",
    )
    args = parser.parse_args()

    matrix = read_json(EXPERIMENT / "runtime_gate_matrix.json")
    projects: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    for project_id in PROJECTS:
        gate = runtime_gate(project_id, matrix)
        ce_gate = official_chaoseater_gate(project_id)
        projects[project_id] = {
            "project_commit": project_commit(project_id),
            "runtime_gate": gate,
            "official_chaoseater_gate": ce_gate,
            "runtime_map": None,
        }
        if args.write_runtime_maps and project_id == "P02":
            runtime_map = p02_runtime_map()
            map_path = EXPERIMENT / "runtime_profiles" / project_id / "runtime-map.json"
            map_path.write_text(json.dumps(runtime_map, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
            projects[project_id]["runtime_map"] = str(map_path.relative_to(ROOT)).replace("\\", "/")
        rows.extend(build_run_rows(project_id, gate, ce_gate, include_chaoseater=args.include_chaoseater))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    ledger = {
        "schema_version": "1.0",
        "kind": "chaosatlas_open_discovery_main_experiment_ledger",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "protocol": "artifacts/experiments/chaosatlas_10_projects/protocol_v2_open_discovery.md",
        "primary_arms": active_experiment_arms(include_chaoseater=args.include_chaoseater),
        "deferred_arms": [] if args.include_chaoseater else [CHAOSEATER_ARM],
        "projects": projects,
        "runs": rows,
        "offline_only": True,
        "deepseek": {"model": "deepseek-v4-flash", "key_read": False, "requests_sent": 0, "consent": False},
        "runtime": {"cluster": "chaos-kind", "namespace_isolation_required": True, "mutation_applied": False},
        "method_scope_policy": (
            "Active scope is the complete ChaosAtlas method plus its noKB ablation. "
            "Historical ChaosEater artifacts are frozen and excluded from active runs, "
            "statistics, knowledge feedback, and method-result eligibility."
            if not args.include_chaoseater
            else
            "ChaosEater was explicitly unfrozen for a separate unified comparison; "
            "its outputs remain method-owned and cannot enter ChaosAtlas knowledge feedback."
        ),
        "improvement_policy": "ChaosEater improvement/reconfiguration outputs are recorded separately and excluded from first-discovery yield.",
        "secondary_candidate_pool_track": "parked_until_primary_track_review",
    }
    args.output.write_text(json.dumps(ledger, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    summary = {
        "output": str(args.output),
        "projects": len(projects),
        "rows": len(rows),
        "ready_rows": sum(row["status"] == "ready_for_explicit_llm_consent" for row in rows),
        "static_input_ready_rows": sum(row["static_input_status"] == "frozen_bundle_ready" for row in rows),
        "static_only_runtime_blocked_rows": sum(row["status"] == "static_only_runtime_blocked" for row in rows),
        "official_input_blocked_rows": sum(row["status"] == "official_input_blocked" for row in rows),
        "blocked_rows": sum(row["status"] in {"static_only_runtime_blocked", "official_input_blocked", "static_input_missing"} for row in rows),
        "official_static_qualified": sum(item["official_chaoseater_gate"]["status"] == "pass_static" for item in projects.values()),
        "deepseek_called": False,
        "mutation_applied": False,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
