"""Run one auditable ChaosAtlas RCA knowledge-loop round.

The orchestrator owns round lineage and stage-level audit data.  RCA state
transitions and evidence eligibility remain in ``rca_runtime_loop`` so the
deterministic contracts have one implementation.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.llm_rca_assistant import analyze_with_backend
from tools.rca_loop import _contains_sensitive_value, canonical_json, sha256_json
from tools.rca_runtime_loop import ActionExecutor, advance_rca_loop


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _input_snapshot(rca_root: Path, source_manifest: dict[str, Any]) -> dict[str, Any]:
    cases = []
    cases_root = rca_root / "cases"
    for case_path in sorted(cases_root.glob("*.json")):
        cases.append({"name": case_path.name, "case": _read_json(case_path)})
    return {
        "schema_version": 1,
        "parent_manifest": source_manifest,
        "cases": cases,
    }


def _case_index(rca_root: Path) -> list[dict[str, Any]]:
    cases = []
    for case_path in sorted((rca_root / "cases").glob("*.json")):
        case = _read_json(case_path)
        cases.append(
            {
                "weakness_id": case.get("weakness_id"),
                "case_family": case.get("case_family"),
                "weakness_status": case.get("weakness_status"),
                "rca_status": case.get("rca_status"),
                "knowledge_status": case.get("knowledge_status"),
            }
        )
    return cases


def _cleanup_report(output_root: Path, *, dry_run: bool) -> dict[str, Any]:
    result_paths = sorted((output_root / "actions").glob("*.json"))
    if not result_paths:
        return {
            "status": "verified" if dry_run else "blocked",
            "mode": "dry_run" if dry_run else "live",
            "action_count": 0,
            "verified_action_count": 0,
            "errors": [] if dry_run else ["no action results found"],
        }

    errors: list[str] = []
    verified = 0
    for path in result_paths:
        result = _read_json(path)
        status = result.get("status")
        if status == "dry_run":
            verified += 1
            continue
        if status != "executed":
            errors.append(f"{path.name}: status={status!r}")
            continue
        attestation = result.get("attestation") or {}
        if attestation.get("cleanup") is True:
            verified += 1
        else:
            errors.append(f"{path.name}: cleanup attestation missing")
    return {
        "status": "verified" if not errors and verified == len(result_paths) else "blocked",
        "mode": "dry_run" if dry_run else "live",
        "action_count": len(result_paths),
        "verified_action_count": verified,
        "errors": errors,
    }


def _knowledge_stage(output_root: Path) -> dict[str, Any]:
    draft_paths = sorted(
        path
        for path in (output_root / "knowledge_drafts").glob("*.json")
        if path.name != "regression_intents.json"
    )
    intents = _read_json(output_root / "knowledge_drafts" / "regression_intents.json")
    cards = [_read_json(path) for path in draft_paths]
    return {
        "knowledge_base_updated": False,
        "card_ids": [card.get("id") for card in cards],
        "provisional_card_count": sum(
            1 for card in cards if card.get("knowledge_status") == "provisional"
        ),
        "intent_count": len(intents.get("intents") or []),
        "rejected_card_ids": list(intents.get("rejected_cards") or []),
        "snapshot_sha256": intents.get("snapshot_sha256"),
        "regression_intents_ref": "knowledge_drafts/regression_intents.json",
    }


def _llm_analysis_stage(output_root: Path, backend: Any) -> dict[str, Any]:
    """Persist advisory evidence analysis without mutating deterministic cases."""

    analysis_root = output_root / "analysis"
    analysis_root.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    for case_path in sorted((output_root / "cases").glob("*.json")):
        case = _read_json(case_path)
        weakness_id = str(case.get("weakness_id") or case_path.stem)
        try:
            analysis = analyze_with_backend(
                backend,
                case,
                list(case.get("evidence_refs") or []),
            )
            serialized = json.dumps(analysis, ensure_ascii=True, sort_keys=True)
            if _contains_sensitive_value(serialized):
                raise ValueError("LLM analysis contains sensitive values")
            filename = re.sub(r"[^A-Za-z0-9._-]+", "-", weakness_id).strip("-") + ".json"
            _write_json(analysis_root / filename, analysis)
            records.append({"weakness_id": weakness_id, "status": "completed", "ref": f"analysis/{filename}"})
        except Exception as exc:
            errors.append(f"{weakness_id}: {type(exc).__name__}: {exc}")
            records.append({"weakness_id": weakness_id, "status": "blocked"})
    return {
        "status": "completed" if not errors else "blocked",
        "case_count": len(records),
        "completed_count": sum(item["status"] == "completed" for item in records),
        "records": records,
        "errors": errors,
        "authority": "advisory_only",
    }


def run_closed_loop(
    *,
    rca_root: Path,
    output_root: Path,
    available_preconditions: set[str],
    executor: ActionExecutor | None = None,
    dry_run: bool = True,
    allow_live: bool = False,
    llm_backend: Any | None = None,
) -> dict[str, Any]:
    """Advance one immutable round and write a four-stage audit manifest."""

    rca_root = Path(rca_root)
    output_root = Path(output_root)
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(
            f"output {output_root} already exists and is not empty"
        )

    source_manifest = _read_json(rca_root / "manifest.json")
    snapshot = _input_snapshot(rca_root, source_manifest)
    input_snapshot_sha256 = sha256_json(snapshot)
    parent_manifest_sha256 = sha256_json(source_manifest)
    parent_round_id = source_manifest.get("round_id")
    source_cases = _case_index(rca_root)

    result = advance_rca_loop(
        rca_root=rca_root,
        output_root=output_root,
        available_preconditions=set(available_preconditions),
        executor=executor,
        dry_run=dry_run,
        allow_live=allow_live,
    )
    output_manifest = result["manifest"]
    knowledge = _knowledge_stage(output_root)
    cleanup = _cleanup_report(output_root, dry_run=dry_run)

    stages: dict[str, Any] = {
        "onboard": {
            "status": "completed",
            "parent_round_id": parent_round_id,
            "input_snapshot_sha256": input_snapshot_sha256,
            "case_count": len(source_cases),
        },
        "discover": {
            "status": "completed",
            "case_count": len(source_cases),
            "weakness_ids": [case.get("weakness_id") for case in source_cases],
            "candidate_count": len(source_cases),
        },
        "diagnose": {
            "status": "completed",
            "action_plan_ref": "action_plan.json",
            "case_statuses": output_manifest.get("case_statuses", []),
        },
        "learn": {
            "status": "completed",
            **knowledge,
        },
    }
    if llm_backend is not None:
        stages["llm_analysis"] = _llm_analysis_stage(output_root, llm_backend)

    audit = {
        "schema_version": 1,
        "tool": "run_closed_loop",
        "project_id": source_manifest.get("project_id"),
        "project_commit": source_manifest.get("project_commit"),
        "round_id": output_manifest.get("round_id"),
        "parent_round_id": parent_round_id,
        "parent_manifest_sha256": parent_manifest_sha256,
        "input_snapshot_sha256": input_snapshot_sha256,
        "execution": {
            "mode": "dry_run" if dry_run else "live",
            "live_execution_allowed": bool(allow_live and not dry_run),
            "available_preconditions": sorted(available_preconditions),
            "approval": bool(allow_live and not dry_run),
        },
        "stages": stages,
        "cleanup": cleanup,
        "knowledge_base_updated": False,
        "status": "completed",
    }
    _write_json(output_root / "closed_loop_manifest.json", audit)

    return {
        "status": "completed",
        "round_id": output_manifest.get("round_id"),
        "input_snapshot_sha256": input_snapshot_sha256,
        "parent_manifest_sha256": parent_manifest_sha256,
        "manifest": audit,
        "validation": result.get("validation"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rca-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)
    if args.live:
        parser.error(
            "live execution requires an injected runtime executor through the Python API"
        )
    result = run_closed_loop(
        rca_root=args.rca_root,
        output_root=args.output,
        available_preconditions={
            "frozen_verdicts",
            "frozen_manifest",
            "captured_ready_samples",
            "captured_window",
        },
        dry_run=True,
    )
    print(
        canonical_json(
            {
                "status": result["status"],
                "round_id": result["round_id"],
                "input_snapshot_sha256": result["input_snapshot_sha256"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
