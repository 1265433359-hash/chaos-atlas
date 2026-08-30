"""Product-level offline closed-loop orchestration.

The runner deliberately stops at synthetic evidence.  It wires existing
project, policy, hypothesis and knowledge helpers into one resumable command
without granting dry-run output any runtime claim authority.
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from tools.chaosatlas_adapters import FakeExecutor, KnowledgeProvider, OfflineProjectAdapter
from tools.chaosatlas_contracts import (
    STAGES,
    RunContext,
    StageResult,
    load_checkpoint,
    write_checkpoint,
    write_stage_artifact,
)
from tools.chaosatlas_hypothesis import build_hypothesis_input, build_hypotheses_with_advisory, rank_candidates


_FIXTURE_FACTS_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "chaosatlas_offline"
_ALIASES = {
    "classify": "finding_report.json",
    "rca": "rca_report.json",
    "learn": "knowledge_draft.json",
    "regression": "regression_intents.json",
}


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _payload_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _facts_path(profile: dict[str, Any], workspace_root: Path) -> Path:
    explicit = profile.get("offline_facts")
    if explicit:
        path = (workspace_root / str(explicit)).resolve()
        if workspace_root.resolve() not in path.parents and path != workspace_root.resolve():
            raise ValueError("offline_facts escapes workspace")
        return path
    project = str(profile.get("project_id") or "").casefold()
    candidates = [path for path in _FIXTURE_FACTS_DIR.iterdir() if path.is_dir() and path.name.casefold() == project]
    if len(candidates) != 1:
        raise ValueError(f"offline facts not found for project: {project}")
    return candidates[0] / "project_facts.json"


def _write_stage(output_root: Path, stage: str, payload: dict[str, Any], *, claim_scope: str = "static") -> None:
    write_stage_artifact(output_root, StageResult.completed(stage, payload, claim_scope=claim_scope))


def _write_alias(output_root: Path, stage: str, payload: dict[str, Any], *, claim_scope: str) -> None:
    filename = _ALIASES.get(stage)
    if not filename:
        return
    artifact = {
        "schema_version": "chaosatlas-stage-result-v1",
        "stage": stage,
        "status": "completed",
        "claim_scope": claim_scope,
        "payload": payload,
    }
    _write_json(output_root / filename, artifact)


def _write_support_artifact(output_root: Path, name: str, payload: dict[str, Any], *, claim_scope: str) -> None:
    artifact = {
        "schema_version": "chaosatlas-support-artifact-v1",
        "artifact": name,
        "status": "completed",
        "claim_scope": claim_scope,
        "payload": payload,
        "output_sha256": _payload_sha256(payload),
    }
    _write_json(output_root / f"{name}.json", artifact)


def _summary(output_root: Path, context: RunContext, completed: list[str], *, status: str, **extra: Any) -> dict[str, Any]:
    summary = {
        "schema_version": "chaosatlas-run-summary-v1",
        "run_id": context.run_id,
        "status": status,
        "completed_stages": list(completed),
        "runtime_claims": [],
        "claim_scope": "synthetic" if "execute" in completed else "static",
        "input_snapshot_sha256": context.input_snapshot_sha256,
    }
    summary.update(extra)
    _write_json(output_root / "summary.json", summary)
    return summary


def _method_invalid(output_root: Path, context: RunContext, completed: list[str], reason: str) -> dict[str, Any]:
    write_checkpoint(output_root, next_stage=None, completed_stages=completed)
    return _summary(output_root, context, completed, status="method_invalid", errors=[reason])


def run_closed_loop(
    *,
    profile_path: Path,
    output_root: Path,
    mode: str = "dry-run",
    seed: int = 1001,
    resume: bool = False,
    knowledge_root: Path | None = None,
) -> dict[str, Any]:
    """Run the deterministic offline closed-loop pipeline."""

    profile_path = Path(profile_path).resolve()
    output_root = Path(output_root).resolve()
    if mode != "dry-run":
        return {"status": "method_invalid", "errors": ["live adapters are not part of the offline milestone"]}
    if not profile_path.is_file():
        return {"status": "method_invalid", "errors": [f"profile not found: {profile_path}"]}

    context = RunContext.create(profile_path=profile_path, mode=mode, seed=seed, output_root=output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    existing = [path for path in output_root.iterdir() if path.name != ".gitkeep"]
    if existing and not resume:
        return _summary(output_root, context, [], status="method_invalid", errors=["output directory is not empty; use --resume"])

    if resume:
        try:
            saved = _read_json(output_root / "run_context.json")
            if saved.get("input_snapshot_sha256") != context.input_snapshot_sha256 or saved.get("run_id") != context.run_id:
                return _method_invalid(output_root, context, [], "run context input hash mismatch")
            checkpoint = load_checkpoint(output_root)
            completed = list(checkpoint.get("completed_stages") or [])
            for stage_name in completed:
                artifact = _read_json(output_root / f"{stage_name}.json")
                if artifact.get("stage") != stage_name or artifact.get("output_sha256") != _payload_sha256(artifact.get("payload", {})):
                    return _method_invalid(output_root, context, completed, f"artifact hash mismatch: {stage_name}")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return _method_invalid(output_root, context, [], f"invalid resume state: {type(exc).__name__}")
    else:
        completed = []
        _write_json(output_root / "run_context.json", context.to_dict())

    try:
        profile = _read_json(profile_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _method_invalid(output_root, context, completed, f"invalid profile: {type(exc).__name__}")
    workspace_root = Path(__file__).resolve().parents[1]
    try:
        facts_path = _facts_path(profile, workspace_root)
    except ValueError as exc:
        return _method_invalid(output_root, context, completed, str(exc))
    adapter = OfflineProjectAdapter(facts_path, workspace_root=workspace_root)
    state: dict[str, Any] = {}

    def stage(stage_name: str, payload: dict[str, Any], *, claim_scope: str = "static") -> None:
        if stage_name in completed:
            return
        _write_stage(output_root, stage_name, payload, claim_scope=claim_scope)
        _write_alias(output_root, stage_name, payload, claim_scope=claim_scope)
        completed.append(stage_name)
        next_stage = STAGES[STAGES.index(stage_name) + 1] if stage_name != STAGES[-1] else None
        write_checkpoint(output_root, next_stage=next_stage, completed_stages=completed)

    if "onboard" not in completed:
        onboard = adapter.onboard(profile_path)
        stage("onboard", onboard)
        if onboard.get("status") != "ready_for_static_analysis":
            return _summary(output_root, context, completed, status="method_invalid", errors=onboard.get("errors", []))
    else:
        onboard = _read_json(output_root / "onboard.json").get("payload", {})
    state["profile"] = onboard.get("profile", profile)

    if "inventory" not in completed:
        stage("inventory", adapter.inventory(state["profile"]))
    inventory = _read_json(output_root / "inventory.json").get("payload", {})
    state["inventory"] = inventory

    if "server_deployment_detection" not in completed:
        stage("server_deployment_detection", adapter.detect_server_deployment(inventory))
    detection = _read_json(output_root / "server_deployment_detection.json").get("payload", {})
    if detection.get("status") != "verified":
        return _summary(output_root, context, completed, status="method_invalid", errors=detection.get("errors", []))

    if "mapping" not in completed:
        stage("mapping", adapter.map_test_nodes(detection))
    mapping = _read_json(output_root / "mapping.json").get("payload", {})
    if mapping.get("status") != "verified":
        return _summary(output_root, context, completed, status="method_invalid", errors=["candidate mapping failed"])

    if "retrieval" not in completed:
        retrieval = KnowledgeProvider().retrieve(
            project_id=str(inventory.get("project_id")),
            project_commit=str(inventory.get("project_commit") or ""),
            candidate_space=mapping,
            root=knowledge_root,
        )
        stage("retrieval", retrieval)
    retrieval = _read_json(output_root / "retrieval.json").get("payload", {})

    ranked = rank_candidates(mapping, retrieval.get("cards") or [])
    selected = ranked.get("candidates", [])[:1]
    _write_support_artifact(
        output_root,
        "candidate_selection",
        {
            "candidate_count": ranked.get("candidate_count", 0),
            "candidate_ids": ranked.get("candidate_ids", []),
            "selected_candidate_ids": [item.get("candidate_id") for item in selected],
            "selection_mode": "deterministic_ranked_prefix",
            "knowledge_card_ids": ranked.get("knowledge_card_ids", []),
            "knowledge_view_sha256": ranked.get("knowledge_view_sha256"),
        },
        claim_scope="advisory",
    )
    _write_support_artifact(
        output_root,
        "stop_decision",
        {
            "stop_reason": "budget_pending" if selected else "candidate_exhausted",
            "budget": 1,
            "next_candidate_id": selected[0].get("candidate_id") if selected else None,
            "evaluated_candidate_ids": [],
        },
        claim_scope="advisory",
    )
    if "hypotheses" not in completed:
        hypothesis_input = build_hypothesis_input(inventory, detection, mapping, retrieval.get("cards") or [])
        stage("hypotheses", build_hypotheses_with_advisory(ranked, hypothesis_input), claim_scope="advisory")
    hypotheses = _read_json(output_root / "hypotheses.json").get("payload", {})

    if "gate" not in completed:
        profile_value = state["profile"]
        required = profile_value.get("recovery", {}), profile_value.get("cleanup", {}), profile_value.get("business_oracles", [])
        gate_status = "pass" if all(required) else "method_invalid"
        stage("gate", {"status": gate_status, "candidate_count": mapping.get("candidate_count", 0), "errors": [] if gate_status == "pass" else ["recovery, cleanup and business oracle are required"]})
    gate = _read_json(output_root / "gate.json").get("payload", {})
    if gate.get("status") != "pass":
        return _summary(output_root, context, completed, status="method_invalid", errors=gate.get("errors", []))

    if "baseline" not in completed:
        stage("baseline", {"status": "planned", "candidate_ids": [item.get("candidate_id") for item in selected], "claim_scope": "static"})
    _write_support_artifact(
        output_root,
        "evidence_plan",
        {
            "candidate_ids": [item.get("candidate_id") for item in selected],
            "required_evidence": ["baseline", "injection", "observation", "recovery", "cleanup", "independent_oracle"],
            "execution_mode": "synthetic",
        },
        claim_scope="synthetic",
    )
    if "execute" not in completed:
        execution = FakeExecutor().run(selected[0] if selected else {"candidate_id": "none"})
        stage("execute", {"selection": selected, "execution": execution}, claim_scope="synthetic")
    execution_payload = _read_json(output_root / "execute.json").get("payload", {})
    execution = execution_payload.get("execution", {})

    if "observe" not in completed:
        stage("observe", {"status": "not_run", "evidence_status": "synthetic", "observation": execution.get("observation", {}), "claim_scope": "synthetic"}, claim_scope="synthetic")
    _write_support_artifact(
        output_root,
        "cleanup_report",
        {"status": "synthetic", "verified": False, "executor_cleanup_confirmed": bool(execution.get("cleanup_confirmed")), "claim_scope": "synthetic"},
        claim_scope="synthetic",
    )
    if "classify" not in completed:
        stage("classify", {"classification": "unsupported", "runtime_verdict": "not_run", "runtime_claims": [], "reason": "synthetic evidence cannot establish runtime outcome"}, claim_scope="synthetic")
    if "rca" not in completed:
        stage("rca", {"rca_status": "not_run", "hypotheses": hypotheses.get("hypotheses", []), "evidence_status": "synthetic", "runtime_claims": []}, claim_scope="synthetic")
    if "learn" not in completed:
        stage("learn", {"knowledge_status": "not_eligible", "reason": "dry-run synthetic evidence", "cards": [], "runtime_claims": []}, claim_scope="synthetic")
    if "promote_defense" not in completed:
        stage("promote_defense", {"status": "not_run", "promotion_allowed": False, "reason": "no verified runtime defense evidence"}, claim_scope="synthetic")
    if "regression" not in completed:
        stage("regression", {"status": "not_run", "intents": [], "reason": "knowledge promotion is not eligible in dry-run"}, claim_scope="synthetic")

    write_checkpoint(output_root, next_stage=None, completed_stages=completed)
    return _summary(
        output_root,
        context,
        completed,
        status="dry_run_ready",
        candidate_count=mapping.get("candidate_count", 0),
        selected_candidate_ids=[item.get("candidate_id") for item in selected],
        advisory_status=hypotheses.get("advisory_status", "deterministic_fallback"),
    )
