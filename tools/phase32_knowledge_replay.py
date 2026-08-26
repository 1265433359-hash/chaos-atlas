"""Audit whether project knowledge changes a dry-run's advisory plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _payload(value: dict[str, Any]) -> dict[str, Any]:
    payload = value.get("payload")
    return payload if isinstance(payload, dict) else value


def _first(values: Any) -> str | None:
    return str(values[0]) if isinstance(values, list) and values else None


def _load_run(root: Path) -> dict[str, Any]:
    names = ("summary.json", "retrieval.json", "knowledge_consumption.json", "hypotheses.json", "evidence_plan.json", "regression_intents.json")
    loaded = {name.removesuffix(".json"): _payload(json.loads((root / name).read_text(encoding="utf-8"))) for name in names}
    loaded["consumption"] = loaded.pop("knowledge_consumption")
    loaded["regression"] = loaded.pop("regression_intents")
    return loaded


def _load_consumption(root: Path) -> dict[str, Any]:
    return json.loads((root / "knowledge_consumption.json").read_text(encoding="utf-8"))


def compare_runs(
    with_knowledge: dict[str, Any],
    without_knowledge: dict[str, Any],
    *,
    boundary: dict[str, Any] | None = None,
    commit_boundary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with_retrieval = with_knowledge["retrieval"]
    without_retrieval = without_knowledge["retrieval"]
    with_consumption = with_knowledge["consumption"]
    without_consumption = without_knowledge["consumption"]
    with_hypotheses = with_knowledge["hypotheses"]
    without_hypotheses = without_knowledge["hypotheses"]
    with_evidence = with_knowledge["evidence_plan"]
    without_evidence = without_knowledge["evidence_plan"]
    with_regression = with_knowledge["regression"]

    with_ids = list(with_hypotheses.get("candidate_ids") or [])
    without_ids = list(without_hypotheses.get("candidate_ids") or [])
    with_selected = list((with_evidence.get("selection") or {}).get("candidate_ids") or [])
    without_selected = list((without_evidence.get("selection") or {}).get("candidate_ids") or [])
    with_intents = [item for item in with_regression.get("intents") or [] if isinstance(item, dict)]
    accepted_ids = list(with_consumption.get("accepted_card_ids") or [])
    knowledge_view = ((with_hypotheses.get("input") or {}).get("knowledge_view") or [])
    forbidden_view_keys = {"status", "classification", "rca_status", "knowledge_status", "weakness_status", "runtime_verdict", "final_verdict", "defense_status"}

    def view_has_forbidden(value: Any) -> bool:
        if isinstance(value, dict):
            return any(key in forbidden_view_keys or view_has_forbidden(child) for key, child in value.items())
        if isinstance(value, list):
            return any(view_has_forbidden(child) for child in value)
        return False

    boundary = boundary or {}
    commit_boundary = commit_boundary or {}
    cross_project_rejected = bool(boundary.get("rejected_card_ids")) and boundary.get("rejection_reasons", {}).get("project_mismatch", 0) > 0
    commit_mismatch_rejected = bool(commit_boundary.get("rejected_card_ids")) and commit_boundary.get("rejection_reasons", {}).get("project_commit_mismatch", 0) > 0
    live_triggered = any(
        str(run.get("summary", {}).get("claim_scope")) == "runtime"
        for run in (with_knowledge, without_knowledge)
    )

    checks = {
        "with_run_ready": with_knowledge.get("summary", {}).get("status") == "dry_run_ready",
        "without_run_ready": without_knowledge.get("summary", {}).get("status") == "dry_run_ready",
        "knowledge_consumed": len(with_consumption.get("accepted_card_ids") or []) > 0,
        "without_run_empty": not without_consumption.get("accepted_card_ids") and not without_consumption.get("rejected_card_ids"),
        "top_candidate_changed": _first(with_ids) != _first(without_ids),
        "evidence_selection_changed": with_selected != without_selected,
        "advisory_scope_preserved": with_hypotheses.get("claim_scope") == "advisory" and with_evidence.get("claim_scope") == "advisory",
        "knowledge_view_sanitized": bool(knowledge_view) and not view_has_forbidden(knowledge_view),
        "dry_run_only": not live_triggered,
        "regression_is_non_executable_draft": bool(with_intents) and all(item.get("executable") is False for item in with_intents),
        "cross_project_rejected": cross_project_rejected,
        "commit_mismatch_rejected": commit_mismatch_rejected,
    }
    return {
        "schema_version": "chaosatlas-phase32-acceptance-v1",
        "status": "passed" if all(checks.values()) else "failed",
        "knowledge": {
            "accepted_card_ids": accepted_ids,
            "accepted_count": int(with_consumption.get("accepted_count") or len(accepted_ids)),
            "rejected_card_ids": list(with_consumption.get("rejected_card_ids") or []),
            "statuses": sorted({str(item.get("knowledge_status")) for item in with_retrieval.get("cards") or []}),
        },
        "comparison": {
            "with_knowledge_top_candidates": with_ids[:10],
            "without_knowledge_top_candidates": without_ids[:10],
            "with_knowledge_evidence_selection": with_selected,
            "without_knowledge_evidence_selection": without_selected,
            "top_candidate_changed": checks["top_candidate_changed"],
            "evidence_selection_changed": checks["evidence_selection_changed"],
            "hypothesis_order_changed": with_ids != without_ids,
        },
        "boundaries": {
            "cross_project_rejected": cross_project_rejected,
            "cross_project_rejected_card_ids": list(boundary.get("rejected_card_ids") or []),
            "commit_mismatch_rejected": commit_mismatch_rejected,
            "commit_mismatch_rejected_card_ids": list(commit_boundary.get("rejected_card_ids") or []),
        },
        "safety": {
            "live_triggered": live_triggered,
            "claim_scope": "static/synthetic",
            "regression_intents_are_dry_run_drafts": checks["regression_is_non_executable_draft"],
        },
        "checks": checks,
    }


def _markdown(report: dict[str, Any]) -> str:
    comparison = report["comparison"]
    boundaries = report["boundaries"]
    return "\n".join(
        [
            "# ChaosAtlas 阶段 32 验收",
            "",
            f"- status: `{report['status']}`",
            f"- accepted knowledge cards: `{report['knowledge']['accepted_count']}`",
            f"- with-knowledge top candidate: `{_first(comparison['with_knowledge_top_candidates'])}`",
            f"- without-knowledge top candidate: `{_first(comparison['without_knowledge_top_candidates'])}`",
            f"- evidence selection changed: `{comparison['evidence_selection_changed']}`",
            f"- cross-project rejection: `{boundaries['cross_project_rejected']}`",
            f"- commit-mismatch rejection: `{boundaries['commit_mismatch_rejected']}`",
            f"- live triggered: `{report['safety']['live_triggered']}`",
            "",
            "本阶段只验证知识消费和 advisory 计划变化；dry-run 的 regression intents 保持不可执行，不能据此宣称新的运行时弱点或已完成 live 回归。",
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-root", type=Path, required=True)
    parser.add_argument("--without-root", type=Path, required=True)
    parser.add_argument("--boundary-root", type=Path, required=True)
    parser.add_argument("--commit-boundary-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = compare_runs(
        _load_run(args.with_root),
        _load_run(args.without_root),
        boundary=_load_consumption(args.boundary_root),
        commit_boundary=_load_consumption(args.commit_boundary_root),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(_markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
