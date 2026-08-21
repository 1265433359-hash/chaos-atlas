"""Run the first deterministic, offline ChaosAtlas closed-loop pipeline."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.chaosatlas_adapters import FakeExecutor, KnowledgeProvider, OfflineProjectAdapter
from tools.chaosatlas_contracts import (
    STAGES,
    RunContext,
    StageResult,
    load_checkpoint,
    write_checkpoint,
    write_stage_artifact,
)
from tools.chaosatlas_hypothesis import (
    build_deterministic_hypotheses,
    build_hypothesis_input,
    rank_candidates,
)


REQUIRED_ALIASES = {
    "inventory": "inventory.json",
    "server_deployment_detection": "server_deployment_detection.json",
    "mapping": "candidate_space.json",
    "retrieval": "retrieval.json",
    "hypotheses": "hypotheses.json",
    "classify": "finding_report.json",
    "rca": "rca_report.json",
    "learn": "knowledge_draft.json",
    "regression": "regression_intents.json",
    "cleanup_report": "cleanup_report.json",
}


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _write_alias(output_root: Path, source: Path, name: str) -> None:
    destination = output_root / name
    if destination != source:
        shutil.copyfile(source, destination)


def _facts_path(project_id: str) -> Path:
    return Path(__file__).resolve().parent / "tests" / "fixtures" / "chaosatlas_offline" / project_id / "project_facts.json"


def _stage(
    output_root: Path,
    completed: list[str],
    stage: str,
    payload: dict[str, Any],
    *,
    claim_scope: str = "static",
    aliases: tuple[str, ...] = (),
) -> dict[str, Any]:
    next_stage = STAGES[STAGES.index(stage) + 1] if stage != STAGES[-1] else None
    result = StageResult.completed(stage, payload, claim_scope=claim_scope, next_stage=next_stage)
    path = write_stage_artifact(output_root, result)
    for alias in aliases:
        _write_alias(output_root, path, alias)
    completed.append(stage)
    write_checkpoint(output_root, next_stage=next_stage, completed_stages=completed)
    return payload


def _summary(output_root: Path, *, status: str, context: RunContext, completed: list[str], error: str | None = None) -> dict[str, Any]:
    payload = {
        "schema_version": "chaosatlas-run-summary-v1",
        "status": status,
        "run_id": context.run_id,
        "input_snapshot_sha256": context.input_snapshot_sha256,
        "completed_stages": completed,
        "error": error,
    }
    _write_text(
        output_root / "summary.md",
        "# ChaosAtlas Offline Run\n\n"
        f"- status: `{status}`\n"
        f"- run_id: `{context.run_id}`\n"
        f"- completed_stages: `{', '.join(completed)}`\n"
        "- claim_scope: `static/synthetic`; no runtime weakness or defense claim\n"
        + (f"- error: `{error}`\n" if error else ""),
    )
    (output_root / "summary.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def _load_or_create_context(profile_path: Path, output_root: Path, mode: str, seed: int, resume: bool) -> tuple[RunContext, bool]:
    if mode != "dry-run":
        raise ValueError("live adapters are not part of the offline milestone; use --mode dry-run")
    if resume:
        if not output_root.is_dir():
            raise FileNotFoundError(f"cannot resume missing output directory: {output_root}")
        manifest_path = output_root / "run_manifest.json"
        if not manifest_path.is_file():
            raise ValueError("cannot resume without run_manifest.json")
        manifest = _read_json(manifest_path)
        context = RunContext.create(profile_path=profile_path, mode=mode, seed=seed, output_root=output_root)
        if manifest.get("input_snapshot_sha256") != context.input_snapshot_sha256:
            raise ValueError("input snapshot changed; refusing resume")
        return context, True
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"refusing non-empty output: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    return RunContext.create(profile_path=profile_path, mode=mode, seed=seed, output_root=output_root), False


def run_closed_loop(
    *,
    profile_path: Path,
    output_root: Path,
    mode: str = "dry-run",
    seed: int = 1001,
    resume: bool = False,
    knowledge_root: Path | None = None,
) -> dict[str, Any]:
    profile_path = Path(profile_path)
    output_root = Path(output_root)
    context, resumed = _load_or_create_context(profile_path, output_root, mode, seed, resume)
    manifest = {
        "schema_version": "chaosatlas-run-manifest-v1",
        "run_id": context.run_id,
        "profile_path": context.profile_path,
        "mode": context.mode,
        "seed": context.seed,
        "input_snapshot_sha256": context.input_snapshot_sha256,
        "claim_scope": "static/synthetic",
    }
    (output_root / "run_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    completed: list[str] = []
    if resumed:
        checkpoint = load_checkpoint(output_root)
        completed = list(checkpoint.get("completed_stages") or [])
    profile: dict[str, Any] | None = None
    inventory: dict[str, Any] | None = None
    detection: dict[str, Any] | None = None
    candidate_space: dict[str, Any] | None = None
    retrieval: dict[str, Any] | None = None
    ranked: dict[str, Any] | None = None
    execution: dict[str, Any] | None = None

    try:
        if "onboard" not in completed:
            profile = _read_json(profile_path)
            facts_hint = _read_json(profile_path)
            project_id = str(facts_hint.get("project_id") or "")
            facts_path = _facts_path(project_id)
            adapter = OfflineProjectAdapter(facts_path, workspace_root=Path(__file__).resolve().parents[1])
            onboard = adapter.onboard(profile_path, Path(__file__).resolve().parents[1])
            _stage(output_root, completed, "onboard", onboard)
            if onboard.get("status") != "ready_for_static_analysis":
                result = _summary(output_root, status="method_invalid", context=context, completed=completed, error="profile onboarding failed")
                return {**result, "input_snapshot_sha256": context.input_snapshot_sha256, "resumed": resumed}
        else:
            profile = _read_json(profile_path)
            project_id = str(profile.get("project_id") or "")
            adapter = OfflineProjectAdapter(_facts_path(project_id), workspace_root=Path(__file__).resolve().parents[1])

        if "inventory" not in completed:
            assert profile is not None
            inventory = adapter.inventory(profile)
            _stage(output_root, completed, "inventory", inventory, aliases=(REQUIRED_ALIASES["inventory"],))
        else:
            inventory = _read_json(output_root / "inventory.json").get("payload", _read_json(output_root / "inventory.json"))

        if "server_deployment_detection" not in completed:
            assert inventory is not None
            detection = adapter.detect_server_deployment(inventory)
            _stage(output_root, completed, "server_deployment_detection", detection, aliases=(REQUIRED_ALIASES["server_deployment_detection"],))
        else:
            detection = _read_json(output_root / "server_deployment_detection.json").get("payload", _read_json(output_root / "server_deployment_detection.json"))

        if "mapping" not in completed:
            assert detection is not None
            candidate_space = adapter.map_test_nodes(detection)
            _stage(output_root, completed, "mapping", candidate_space, aliases=(REQUIRED_ALIASES["mapping"],))
        else:
            candidate_space = _read_json(output_root / "candidate_space.json").get("payload", _read_json(output_root / "candidate_space.json"))

        if "retrieval" not in completed:
            assert inventory is not None and candidate_space is not None
            provider = KnowledgeProvider()
            retrieval = provider.retrieve(project_id=str(inventory["project_id"]), candidate_space=candidate_space, root=knowledge_root)
            _stage(output_root, completed, "retrieval", retrieval, aliases=(REQUIRED_ALIASES["retrieval"],))
        else:
            retrieval = _read_json(output_root / "retrieval.json").get("payload", _read_json(output_root / "retrieval.json"))

        if "hypotheses" not in completed:
            assert inventory is not None and detection is not None and candidate_space is not None and retrieval is not None
            hypothesis_input = build_hypothesis_input(inventory, detection, candidate_space, retrieval.get("cards", []))
            ranked = rank_candidates(candidate_space, retrieval.get("cards", []))
            hypotheses = build_deterministic_hypotheses(ranked)
            hypotheses["input"] = hypothesis_input
            _stage(output_root, completed, "hypotheses", hypotheses, claim_scope="advisory", aliases=(REQUIRED_ALIASES["hypotheses"],))
        else:
            hypotheses = _read_json(output_root / "hypotheses.json").get("payload", _read_json(output_root / "hypotheses.json"))
            ranked = {"candidates": [item for item in (candidate_space or {}).get("candidates", [])], "candidate_count": len((candidate_space or {}).get("candidates", []))}

        if "gate" not in completed:
            assert candidate_space is not None
            gate = {"status": "verified", "accepted_candidate_ids": [item.get("candidate_id") for item in candidate_space.get("candidates", [])], "claim_scope": "static"}
            _stage(output_root, completed, "gate", gate)
        else:
            gate = _read_json(output_root / "gate.json").get("payload", _read_json(output_root / "gate.json"))

        first_candidate = ((ranked or {}).get("candidates") or (candidate_space or {}).get("candidates") or [None])[0]
        if first_candidate is None:
            raise ValueError("no candidate survived server deployment detection")
        plan = {"candidate_id": first_candidate.get("candidate_id"), "expected_invariant": "business_oracle_success"}

        if "baseline" not in completed:
            _stage(output_root, completed, "baseline", {"status": "planned", "plan": plan, "claim_scope": "synthetic"}, claim_scope="synthetic")
        if "execute" not in completed or "observe" not in completed:
            execution = FakeExecutor().run(plan)
        if "execute" not in completed:
            _stage(output_root, completed, "execute", execution, claim_scope="synthetic")
        if "observe" not in completed:
            _stage(output_root, completed, "observe", execution.get("observation", {}), claim_scope="synthetic")
        if "classify" not in completed:
            _stage(output_root, completed, "classify", {"result": "not_run", "claim_scope": "synthetic", "evidence_status": "synthetic", "reason": "offline fake executor"}, claim_scope="synthetic", aliases=(REQUIRED_ALIASES["classify"],))
        if "rca" not in completed:
            _stage(output_root, completed, "rca", {"rca_status": "not_run", "claim_scope": "synthetic", "reason": "runtime evidence unavailable"}, claim_scope="synthetic", aliases=(REQUIRED_ALIASES["rca"],))
        if "learn" not in completed:
            _stage(output_root, completed, "learn", {"knowledge_status": "none", "claim_scope": "synthetic", "promotion_allowed": False, "reason": "fake evidence cannot promote knowledge"}, claim_scope="synthetic", aliases=(REQUIRED_ALIASES["learn"],))
        if "regression" not in completed:
            intents = [{"candidate_id": item.get("candidate_id"), "status": "draft", "executable": False, "reason": "requires runtime validation"} for item in (candidate_space or {}).get("candidates", [])]
            _stage(output_root, completed, "regression", {"intents": intents, "claim_scope": "synthetic"}, claim_scope="synthetic", aliases=(REQUIRED_ALIASES["regression"],))

        cleanup = {"status": "verified", "cleanup_confirmed": True, "evidence_status": "synthetic", "claim_scope": "synthetic"}
        _write_text(output_root / "cleanup_report.json", json.dumps(cleanup, indent=2, ensure_ascii=False) + "\n")
        summary = _summary(output_root, status="dry_run_ready", context=context, completed=completed)
        return {**summary, "input_snapshot_sha256": context.input_snapshot_sha256, "resumed": resumed}
    except Exception as exc:
        summary = _summary(output_root, status="method_invalid", context=context, completed=completed, error=str(exc))
        if not (output_root / "checkpoint.json").exists():
            write_checkpoint(output_root, next_stage=STAGES[len(completed)] if len(completed) < len(STAGES) else None, completed_stages=completed)
        return {**summary, "input_snapshot_sha256": context.input_snapshot_sha256, "resumed": resumed}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--profile", type=Path, required=True)
    run.add_argument("--mode", choices=("dry-run", "live"), default="dry-run")
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--seed", type=int, default=1001)
    run.add_argument("--resume", action="store_true")
    run.add_argument("--knowledge-root", type=Path)
    args = parser.parse_args(argv)
    if args.command == "run":
        result = run_closed_loop(profile_path=args.profile, output_root=args.output, mode=args.mode, seed=args.seed, resume=args.resume, knowledge_root=args.knowledge_root)
        print(json.dumps({"status": result["status"], "run_id": result.get("run_id"), "output": str(args.output)}, ensure_ascii=True))
        return 0 if result["status"] == "dry_run_ready" else 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
