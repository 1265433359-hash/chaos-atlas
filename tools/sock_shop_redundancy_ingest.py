"""Promote a validated two-replica counterfactual into a local RCA round."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

from tools.compile_rca_regression import compile_regression_intents, project_knowledge_draft
from tools.evidence_collectors import collect_file_evidence
from tools.rca_loop import _contains_sensitive_value, evaluate_knowledge_promotion, sha256_json
from tools.validate_rca_loop import validate_artifact


ROUND_ID = "pilot-r4-redundancy-r1"
ACTION_ID = "A-SS-SINGLETON-COUNTERFACTUAL-001"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, indent=2, ensure_ascii=True, sort_keys=True) + "\n"
    if _contains_sensitive_value(text):
        raise ValueError(f"sensitive value detected in {path}")
    path.write_text(text, encoding="utf-8")


def _copy_tree(parent_root: Path, output_root: Path) -> None:
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"output {output_root} is not empty")
    output_root.mkdir(parents=True, exist_ok=True)
    for source in parent_root.rglob("*"):
        if source.is_file() and source.name != "validation_report.json":
            destination = output_root / source.relative_to(parent_root)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)


def _require_valid_counterfactual(result: dict[str, Any]) -> dict[str, Any]:
    summary = result.get("summary") or {}
    if summary.get("classification") != "defended" or summary.get("deterministic") is not True:
        raise ValueError("redundancy ingestion requires a deterministic defended result")
    if result.get("run_error") is not None:
        raise ValueError("redundancy ingestion refuses a run with errors")
    if result.get("cleanup_error") is not None or result.get("residual_podchaos"):
        raise ValueError("redundancy ingestion refuses incomplete cleanup")
    if result.get("original_replicas") != 1 or result.get("restored_replicas") != 1:
        raise ValueError("redundancy ingestion requires singleton restoration")
    if int(result.get("sample_count", 0)) < 1 or int(summary.get("defended_sample_count", 0)) < 1:
        raise ValueError("redundancy ingestion requires at least one defended sample")
    return summary


def build_redundancy_round(*, parent_root: Path, source_root: Path, output_root: Path) -> dict[str, Any]:
    parent_root = Path(parent_root)
    source_root = Path(source_root)
    output_root = Path(output_root)
    parent_manifest = _load(parent_root / "manifest.json")
    source_result = _load(source_root / "result.json")
    summary = _require_valid_counterfactual(source_result)
    _copy_tree(parent_root, output_root)

    case_paths = sorted((output_root / "cases").glob("*.json"))
    if len(case_paths) != 1:
        raise ValueError("Sock Shop redundancy ingestion expects exactly one case")
    case_path = case_paths[0]
    case = _load(case_path)
    if case.get("knowledge_status") != "provisional":
        raise ValueError("redundancy promotion expects a provisional parent case")
    case["round_id"] = ROUND_ID
    evidence_root = output_root / "evidence" / "redundancy-r1"
    source_names = ("result.json", "timeline.jsonl", "before.json", "after.json", "mutation.yaml", "scale_events.json")
    for name in source_names:
        source = source_root / name
        if not source.is_file():
            raise ValueError(f"missing redundancy source: {source}")
        destination = evidence_root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    claim_scope = str(case.get("test_node", {}).get("target_role") or "front-end deployment")
    window = source_result.get("window")
    evidence = [
        collect_file_evidence(
            root=output_root,
            source_ref="evidence/redundancy-r1/result.json",
            evidence_id="EV-LIVE-R4-COUNTERFACTUAL-001",
            kind="business_path_replay",
            claim_scope=claim_scope,
            interpretation="scaling front-end to two replicas and killing one fixed Pod UID preserved HTTP 200 through a different Ready Pod UID in Service endpoints",
            satisfies=["redundancy_counterfactual", "business_continuity", "business_impact_in_window"],
            window=window,
        ),
        collect_file_evidence(
            root=output_root,
            source_ref="evidence/redundancy-r1/scale_events.json",
            evidence_id="EV-LIVE-R4-SCALE-001",
            kind="config",
            claim_scope=claim_scope,
            interpretation="runtime scale timeline records 1->2 before injection and restoration to 1 after cleanup",
            satisfies=["scale_isolation", "singleton_restoration"],
            window=window,
        ),
        collect_file_evidence(
            root=output_root,
            source_ref="evidence/redundancy-r1/after.json",
            evidence_id="EV-LIVE-R4-CLEANUP-001",
            kind="kubernetes_event",
            claim_scope=claim_scope,
            interpretation="post-run snapshot confirms the original singleton replica count was restored and the PodChaos resource was removed",
            satisfies=["cleanup_confirmation", "singleton_restoration"],
            window=window,
        ),
    ]
    case.setdefault("evidence_refs", []).extend(evidence)
    promotion = evaluate_knowledge_promotion(
        current=str(case.get("knowledge_status")),
        weakness_status=str(case.get("weakness_status")),
        rca_status=str(case.get("rca_status")),
        valid_reproductions=1,
        valid_counterfactuals=1,
        lifecycle_complete=True,
        direct_evidence=True,
        applicability_complete=True,
        regression_complete=True,
        contradiction=False,
    )
    if not promotion.get("allowed") or promotion.get("next_status") != "local_reusable":
        raise ValueError(f"knowledge promotion gate rejected redundancy evidence: {promotion}")
    case["knowledge_status"] = "local_reusable"
    case["knowledge_promotion_audit"] = {
        **promotion,
        "valid_reproductions": 1,
        "valid_counterfactuals": 1,
        "lifecycle_complete": True,
        "direct_evidence": True,
        "applicability_complete": True,
        "regression_complete": True,
        "counterfactual_summary": summary,
    }
    for hypothesis in case.get("hypotheses", []):
        hypothesis.setdefault("evidence_for", []).append("EV-LIVE-R4-COUNTERFACTUAL-001")
        hypothesis["evidence_for"] = sorted(set(hypothesis["evidence_for"]))
        hypothesis["unsupported_claims"] = [
            item
            for item in hypothesis.get("unsupported_claims", [])
            if item not in {
                "isolated_scale_to_two_counterfactual",
                "static_manifest_replica_facts",
                "business_impact_in_window",
            }
        ]
        hypothesis["next_action"] = None
    case.setdefault("action_history", []).append(
        {"action_id": ACTION_ID, "action_ref": "evidence/redundancy-r1/result.json", "evidence_ids": [item["evidence_id"] for item in evidence], "status": "executed"}
    )
    case["next_actions"] = [{"action_id": ACTION_ID, "status": "completed", "evidence_ids": [item["evidence_id"] for item in evidence]}]
    _write(case_path, case)
    for hypothesis in case.get("hypotheses", []):
        _write(output_root / "hypotheses" / f"{hypothesis['hypothesis_id']}.json", hypothesis)

    action_plan = _load(output_root / "action_plan.json")
    action_plan["round_id"] = ROUND_ID
    for entry in action_plan.get("case_plans", []):
        if entry.get("weakness_id") == case.get("weakness_id"):
            plan = entry.setdefault("plan", {})
            plan.update({"status": "completed", "completed_action": {"action_id": ACTION_ID, "result_ref": "evidence/redundancy-r1/result.json", "result_status": "executed"}, "promotion": promotion})
    _write(output_root / "action_plan.json", action_plan)

    draft = project_knowledge_draft(case, case.get("hypotheses", []), case.get("next_actions", []))
    _write(output_root / "knowledge_drafts" / f"{draft['id']}.json", draft)
    _write(output_root / "knowledge_drafts" / "regression_intents.json", compile_regression_intents([draft], snapshot={"cards": [draft]}))

    manifest = _load(output_root / "manifest.json")
    manifest.update(
        {
            "round_id": ROUND_ID,
            "parent_round_id": parent_manifest.get("round_id"),
            "parent_manifest_sha256": sha256_json(parent_manifest),
            "redundancy_source_sha256": hashlib.sha256((source_root / "result.json").read_bytes()).hexdigest(),
            "knowledge_base_updated": False,
            "case_statuses": [{"weakness_id": case.get("weakness_id"), "weakness_status": case.get("weakness_status"), "rca_status": case.get("rca_status"), "knowledge_status": case.get("knowledge_status")}],
        }
    )
    _write(output_root / "manifest.json", manifest)
    report = validate_artifact(output_root)
    _write(output_root / "validation_report.json", report)
    if not report["valid"]:
        raise ValueError("generated redundancy RCA round failed validation: " + "; ".join(report["errors"]))
    return {
        "status": summary["classification"],
        "knowledge_status": case["knowledge_status"],
        "round_id": ROUND_ID,
        "validation": report,
        "evidence_ids": [item["evidence_id"] for item in evidence],
    }
