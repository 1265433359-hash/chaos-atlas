"""Review the corrected Sock Shop Full Top 11 evidence without changing the KB."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.build_sock_shop_r5_evidence_selection import validate_runtime_report


WEAKNESS = "weakness_observed"
NO_IMPACT = "no_business_impact_observed"
EXPECTED_DIAGNOSTICS = {
    "front-end.log",
    "catalogue.log",
    "orders.log",
    "target.log",
    "events.json",
    "zipkin.json",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(path: str) -> Path:
    value = Path(path)
    if value.is_file():
        return value
    candidate = ROOT / value
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(path)


def executable_mutation_key(instance_key: str) -> str:
    return re.sub(r"\|call_chain_position=[^|]*", "", instance_key)


def classify_pair(classifications: Iterable[str]) -> str:
    values = list(classifications)
    if len(values) != 2:
        raise ValueError("classification requires exactly two replicates")
    unsupported = sorted(set(values) - {WEAKNESS, NO_IMPACT})
    if unsupported:
        raise ValueError(f"unsupported classification: {', '.join(unsupported)}")
    weakness_count = values.count(WEAKNESS)
    if weakness_count == 2:
        return "stable_weakness"
    if weakness_count == 1:
        return "unstable"
    return "no_impact"


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> list[float]:
    if total <= 0 or not 0 <= successes <= total:
        raise ValueError("invalid Wilson interval inputs")
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(
        proportion * (1 - proportion) / total + z * z / (4 * total * total)
    ) / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


def build_review(
    plan: dict[str, Any],
    evidence_by_rank: dict[int, list[dict[str, Any]]],
    ablation_entries: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    if plan.get("human_review") != "pending" or plan.get("knowledge_base_updated") is not False:
        raise ValueError("execution plan must remain pending and must not update the knowledge base")

    entries = list(plan.get("entries") or [])
    ablation_entries = list(ablation_entries)
    blocked = [entry for entry in entries if entry.get("execution_status") == "blocked"]
    executable = [entry for entry in entries if entry.get("execution_status") != "blocked"]
    counts: Counter[str] = Counter()
    items = []
    for entry in executable:
        rank = int(entry.get("rank") or 0)
        reports = sorted(evidence_by_rank.get(rank) or [], key=lambda item: int(item.get("replicate") or 0))
        if len(reports) != 2 or {int(item.get("replicate") or 0) for item in reports} != {1, 2} or not all(item.get("valid") for item in reports):
            raise ValueError(f"rank {rank} does not have two valid reports with replicates {{1, 2}}")
        classification = classify_pair(str(item.get("classification")) for item in reports)
        counts[classification] += 1
        items.append(
            {
                "rank": rank,
                "hypothesis_id": entry.get("hypothesis_id"),
                "confidence_score": entry.get("confidence_score"),
                "category": entry.get("category"),
                "target_service": entry.get("target_service"),
                "action_or_target": entry.get("action_or_target"),
                "execution_status": entry.get("execution_status"),
                "executable_mutation_key": entry.get("executable_mutation_key"),
                "replicate_classifications": [item.get("classification") for item in reports],
                "classification": classification,
                "reports": [item.get("path") for item in reports],
            }
        )

    full_by_key: dict[str, dict[str, Any]] = {}
    for entry in executable:
        key = str(entry.get("executable_mutation_key") or "")
        if not key:
            continue
        if key in full_by_key:
            raise ValueError(f"duplicate executable mutation key: {key}")
        full_by_key[key] = entry
    pairs = []
    seen_pairs = set()
    for ablation in ablation_entries:
        instance_key = str(ablation.get("mutation_instance_key") or "")
        key = executable_mutation_key(instance_key)
        full = full_by_key.get(key)
        pair_id = (key, str(ablation.get("hypothesis_id") or ""))
        if not full or pair_id in seen_pairs:
            continue
        seen_pairs.add(pair_id)
        pairs.append(
            {
                "full_rank": int(full.get("rank") or 0),
                "full_hypothesis_id": full.get("hypothesis_id"),
                "ablation_hypothesis_id": ablation.get("hypothesis_id"),
                "executable_mutation_key": key,
            }
        )
    pairs.sort(key=lambda item: (item["full_rank"], str(item["ablation_hypothesis_id"])))

    denominator = len(executable)
    stable = counts["stable_weakness"]
    top_k = len(entries)
    return {
        "schema_version": "sock-shop-full-top11-review-v1",
        "selection": {
            "top_k": top_k,
            "executable": denominator,
            "blocked": len(blocked),
            "executable_rate": denominator / top_k if top_k else 0.0,
            "blocked_items": [
                {
                    "rank": entry.get("rank"),
                    "hypothesis_id": entry.get("hypothesis_id"),
                    "confidence_score": entry.get("confidence_score"),
                    "gate_errors": entry.get("gate_errors") or [],
                }
                for entry in blocked
            ],
        },
        "results": {
            "denominator": denominator,
            "counts": {
                "stable_weakness": stable,
                "unstable": counts["unstable"],
                "no_impact": counts["no_impact"],
            },
            "stable_weakness_rate": stable / denominator if denominator else 0.0,
            "wilson_95_interval": wilson_interval(stable, denominator) if denominator else [0.0, 1.0],
            "items": items,
        },
        "ablation_identity_overlap": {
            "ablation_candidate_count": len(ablation_entries),
            "executable_overlap_count": len(pairs),
            "pairs": pairs,
            "interpretation": "identity_only_not_a_cross_arm_performance_comparison",
        },
        "interpretation": {
            "business_weakness_rule": "both_replicates_must_be_weakness_observed",
            "unstable_rule": "one_of_two_is_reported_separately_and_not_counted_as_stable",
            "blocked_rule": "blocked_candidates_are_not_replaced_and_are_excluded_from_runtime_denominator",
            "causal_claim": "business_effect_is_supported_but_specific_internal_mechanism_is_not_inferred",
        },
        "human_review": "pending",
        "knowledge_base_updated": False,
    }


def _validate_diagnostics(evidence: dict[str, Any]) -> list[str]:
    names = {Path(str(item.get("path") or "")).name for item in evidence.get("diagnostic_files") or []}
    return sorted(EXPECTED_DIAGNOSTICS - names)


def revalidate_evidence(
    plan: dict[str, Any],
    batch: dict[str, Any],
) -> tuple[dict[int, list[dict[str, Any]]], dict[str, Any]]:
    fresh_rows: dict[int, list[dict[str, Any]]] = {}
    for row in batch.get("rows") or []:
        fresh_rows.setdefault(int(row.get("rank") or 0), []).append(row)

    evidence_by_rank: dict[int, list[dict[str, Any]]] = {}
    failures = []
    fresh_reports = historical_reports = diagnostic_files = 0
    if batch.get("arm") != "ChaosAtlas-full-top11":
        failures.append({"reasons": ["batch_arm_mismatch"]})
    batch_plan = batch.get("execution_plan")
    batch_plan_sha = batch.get("execution_plan_sha256")
    if not batch_plan or not batch_plan_sha:
        raise ValueError("batch execution plan provenance missing")
    else:
        try:
            if _sha(_resolve(str(batch_plan))) != batch_plan_sha:
                raise ValueError("batch execution plan SHA-256 mismatch")
        except Exception as exc:
            if isinstance(exc, ValueError):
                raise
            raise ValueError(f"batch execution plan unavailable: {type(exc).__name__}") from exc
    for entry in plan.get("entries") or []:
        rank = int(entry.get("rank") or 0)
        status = entry.get("execution_status")
        if status == "blocked":
            continue
        reports: list[dict[str, Any]] = []
        if status == "fresh_required":
            rows = sorted(fresh_rows.get(rank) or [], key=lambda item: int(item.get("replicate") or 0))
            if len(rows) != 2 or {int(row.get("replicate") or 0) for row in rows} != {1, 2}:
                failures.append({"rank": rank, "reasons": ["fresh_report_count_not_two"]})
                continue
            sources = [dict(row, path=row.get("report_path")) for row in rows]
            fresh_reports += len(sources)
        elif status == "reused_historical":
            sources = list((entry.get("historical_evidence") or {}).get("reports") or [])
            historical_reports += len(sources)
        else:
            failures.append({"rank": rank, "reasons": [f"unsupported_execution_status:{status}"]})
            continue

        for source in sources:
            reasons = []
            try:
                evidence = validate_runtime_report(_resolve(str(source.get("path") or "")))
            except Exception as exc:
                failures.append({"rank": rank, "path": source.get("path"), "reasons": [f"{type(exc).__name__}:{exc}"]})
                continue
            if source.get("report_sha256") and evidence.get("report_sha256") != source.get("report_sha256"):
                reasons.append("report_sha256_changed_since_execution_plan")
            if source.get("classification") and evidence.get("classification") != source.get("classification"):
                reasons.append("classification_changed_since_execution_plan")
            if status == "fresh_required":
                if source.get("hypothesis_id") != entry.get("hypothesis_id"):
                    reasons.append("fresh_hypothesis_id_mismatch")
                if evidence.get("mutation_id") != entry.get("hypothesis_id"):
                    reasons.append("fresh_report_mutation_id_mismatch")
                if int(source.get("replicate") or 0) != int(evidence.get("replicate") or 0):
                    reasons.append("fresh_replicate_mismatch")
                if int(evidence.get("replicate") or 0) not in {1, 2}:
                    reasons.append("fresh_report_replicate_out_of_range")
                if source.get("arm") != "ChaosAtlas-full-top11":
                    reasons.append("fresh_arm_mismatch")
                if source.get("mutation_sha256") != entry.get("mutation_sha256"):
                    reasons.append("fresh_row_mutation_sha256_mismatch")
            if status == "fresh_required" and evidence.get("mutation_sha256") != entry.get("mutation_sha256"):
                reasons.append("fresh_mutation_sha256_mismatch")
            if status == "reused_historical" and source.get("mutation_instance_key") != entry.get("mutation_instance_key"):
                reasons.append("historical_mutation_identity_mismatch")
            missing_diagnostics = _validate_diagnostics(evidence)
            if missing_diagnostics:
                reasons.append(f"missing_diagnostics:{','.join(missing_diagnostics)}")
            diagnostic_files += len(evidence.get("diagnostic_files") or [])
            if reasons:
                evidence["valid"] = False
                evidence.setdefault("reasons", []).extend(reasons)
            if not evidence.get("valid"):
                failures.append({"rank": rank, "path": evidence.get("path"), "reasons": evidence.get("reasons")})
            reports.append(evidence)
        evidence_by_rank[rank] = reports

    expected_ready = sum(entry.get("execution_status") != "blocked" for entry in plan.get("entries") or [])
    if len(evidence_by_rank) != expected_ready:
        failures.append({"reasons": ["ready_candidate_evidence_count_mismatch"]})
    verification = {
        "fresh_reports_revalidated": fresh_reports,
        "historical_reports_revalidated": historical_reports,
        "total_reports_revalidated": fresh_reports + historical_reports,
        "diagnostic_files_rehashed": diagnostic_files,
        "expected_diagnostics_per_report": sorted(EXPECTED_DIAGNOSTICS),
        "failures": failures,
        "all_valid": not failures,
    }
    if failures:
        raise ValueError(f"evidence revalidation failed: {len(failures)} issue(s)")
    return evidence_by_rank, verification


def load_ablation_entries(overlap_audit: dict[str, Any]) -> list[dict[str, Any]]:
    entries = list(overlap_audit.get("ablation_only") or [])
    entries.extend(
        item.get("ablation") or {}
        for item in overlap_audit.get("strict_overlap") or []
        if item.get("ablation")
    )
    unique = {}
    for entry in entries:
        key = (str(entry.get("hypothesis_id") or ""), str(entry.get("mutation_instance_key") or ""))
        unique[key] = entry
    return [unique[key] for key in sorted(unique)]


def _percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def render_markdown(review: dict[str, Any]) -> str:
    selection = review["selection"]
    results = review["results"]
    counts = results["counts"]
    low, high = results["wilson_95_interval"]
    lines = [
        "# Sock Shop Full Top 11 纠正实验审核",
        "",
        "## 结论",
        "",
        f"- Full 自身去重后置信度最高的 {selection['top_k']} 个候选全部保留，没有按历史证据可得性筛选，也没有为 blocked 候选补位。",
        f"- {selection['executable']} 个候选可执行，{selection['blocked']} 个在注入前被 gate 阻断；可执行率为 {_percent(selection['executable_rate'])}。",
        f"- 可执行候选中稳定弱点 {counts['stable_weakness']} 个、不稳定 {counts['unstable']} 个、两次均未观察到影响 {counts['no_impact']} 个。",
        f"- 稳定弱点率为 {_percent(results['stable_weakness_rate'])}（Wilson 95% CI {_percent(low)} - {_percent(high)}）。",
        "- 这里确认的是故障注入与业务失败的稳定关联，不据此猜测具体内部机制。",
        "",
        "## 候选明细",
        "",
        "| 排名 | 假设 | 置信度 | 执行来源 | 两次结果 | 归类 |",
        "|---:|---|---:|---|---|---|",
    ]
    for item in results["items"]:
        replications = " / ".join(item["replicate_classifications"])
        lines.append(
            f"| {item['rank']} | `{item['hypothesis_id']}` | {float(item['confidence_score']):.6f} | "
            f"{item['execution_status']} | {replications} | **{item['classification']}** |"
        )
    for item in selection["blocked_items"]:
        errors = "; ".join(item["gate_errors"])
        lines.append(
            f"| {item['rank']} | `{item['hypothesis_id']}` | {float(item['confidence_score']):.6f} | "
            f"blocked | 未注入 | **blocked: {errors}** |"
        )
    lines.extend(
        [
            "",
            "## Ablation 身份重合",
            "",
            f"- Ablation 去重候选数：{review['ablation_identity_overlap']['ablation_candidate_count']}。",
            f"- 与 Full Top 11 按实际 executable mutation 重合：{review['ablation_identity_overlap']['executable_overlap_count']} 个。",
            "- 该结果只说明候选身份关系；两边候选池不同，不能直接把本表稳定弱点率当作公平的跨方法胜负。",
            "",
            "## 证据完整性",
            "",
            f"- 重新校验报告：{review['evidence_verification']['total_reports_revalidated']} 份。",
            f"- 重新计算诊断文件 SHA-256：{review['evidence_verification']['diagnostic_files_rehashed']} 个。",
            f"- 所有证据有效：`{str(review['evidence_verification']['all_valid']).lower()}`。",
            f"- human review：`{review['human_review']}`。",
            f"- knowledge base updated：`{str(review['knowledge_base_updated']).lower()}`。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--batch-progress", type=Path, required=True)
    parser.add_argument("--ablation-overlap", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty output directory: {args.output}")
    args.output.mkdir(parents=True, exist_ok=True)

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    batch = json.loads(args.batch_progress.read_text(encoding="utf-8"))
    if batch.get("execution_plan_sha256") != _sha(args.plan):
        raise ValueError("batch progress does not match execution plan SHA-256")
    overlap_audit = json.loads(args.ablation_overlap.read_text(encoding="utf-8"))
    evidence_by_rank, verification = revalidate_evidence(plan, batch)
    ablation_entries = load_ablation_entries(overlap_audit)
    review = build_review(plan, evidence_by_rank, ablation_entries)
    review["evidence_verification"] = verification
    review["provenance"] = {
        "execution_plan": str(args.plan),
        "execution_plan_sha256": _sha(args.plan),
        "batch_progress": str(args.batch_progress),
        "batch_progress_sha256": _sha(args.batch_progress),
        "ablation_overlap": str(args.ablation_overlap),
        "ablation_overlap_sha256": _sha(args.ablation_overlap),
        "normalization_config_sha256": overlap_audit.get("normalization_config_sha256"),
    }

    json_path = args.output / "review.json"
    markdown_path = args.output / "REVIEW.zh-CN.md"
    json_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(review), encoding="utf-8")
    (args.output / "SHA256SUMS").write_text(
        f"{_sha(json_path)}  {json_path.name}\n{_sha(markdown_path)}  {markdown_path.name}\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "selection": review["selection"],
                "results": {key: review["results"][key] for key in ("denominator", "counts", "stable_weakness_rate")},
                "evidence_verification": verification,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
