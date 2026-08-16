"""Independently review the frozen Sock Shop R5 two-arm evidence."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.build_sock_shop_r5_evidence_selection import validate_runtime_report

WEAKNESS = "weakness_observed"
NO_IMPACT = "no_business_impact_observed"


def executable_mutation_key(instance_key: str) -> str:
    return re.sub(r"\|call_chain_position=[^|]*", "", instance_key)


def executable_overlap_pairs(
    full_entries: Iterable[dict[str, Any]],
    ablation_entries: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    full_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in full_entries:
        instance = str((entry.get("record") or {}).get("mutation_instance_key") or "")
        if instance:
            full_by_key[executable_mutation_key(instance)].append(entry)
    pairs = []
    for ablation in ablation_entries:
        ablation_record = ablation.get("record") or {}
        ablation_instance = str(ablation_record.get("mutation_instance_key") or "")
        if not ablation_instance:
            continue
        key = executable_mutation_key(ablation_instance)
        for full in full_by_key.get(key) or []:
            full_record = full.get("record") or {}
            pairs.append(
                {
                    "full_hypothesis_id": full_record.get("hypothesis_id"),
                    "ablation_hypothesis_id": ablation_record.get("hypothesis_id"),
                    "strict_instance_match": full_record.get("mutation_instance_key") == ablation_instance,
                    "executable_mutation_key": key,
                }
            )
    return pairs


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


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total <= 0 or not 0 <= successes <= total:
        raise ValueError("successes and total must satisfy 0 <= successes <= total and total > 0")
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def fisher_exact_two_sided(a: int, b: int, c: int, d: int) -> dict[str, float]:
    if min(a, b, c, d) < 0:
        raise ValueError("contingency cells must be non-negative")
    row_one = a + b
    successes = a + c
    total = a + b + c + d
    if total == 0:
        raise ValueError("contingency table must not be empty")

    def probability(x: int) -> float:
        return math.comb(successes, x) * math.comb(total - successes, row_one - x) / math.comb(total, row_one)

    lower = max(0, row_one - (total - successes))
    upper = min(row_one, successes)
    observed = probability(a)
    p_value = sum(probability(x) for x in range(lower, upper + 1) if probability(x) <= observed + 1e-12)
    if b * c == 0:
        odds_ratio = math.inf if a * d else math.nan
    else:
        odds_ratio = (a * d) / (b * c)
    return {"odds_ratio": odds_ratio, "p_value": min(1.0, p_value)}


def summarize_method(entries: Iterable[dict[str, Any]]) -> dict[str, Any]:
    items = []
    counts: Counter[str] = Counter()
    for entry in entries:
        evidence = entry.get("evidence") or {}
        reports = evidence.get("reports") or []
        if evidence.get("valid") is False or not all(report.get("valid", True) for report in reports):
            raise ValueError(f"invalid evidence for {entry.get('record', {}).get('hypothesis_id')}")
        pair_classification = classify_pair(report.get("classification") for report in reports)
        counts[pair_classification] += 1
        items.append(
            {
                "hypothesis_id": (entry.get("record") or {}).get("hypothesis_id"),
                "fault_family_key": (entry.get("record") or {}).get("fault_family_key"),
                "mutation_instance_key": (entry.get("record") or {}).get("mutation_instance_key"),
                "replicate_classifications": [report.get("classification") for report in reports],
                "classification": pair_classification,
            }
        )
    denominator = len(items)
    stable = counts["stable_weakness"]
    interval = wilson_interval(stable, denominator)
    return {
        "denominator": denominator,
        "counts": {
            "stable_weakness": stable,
            "unstable": counts["unstable"],
            "no_impact": counts["no_impact"],
        },
        "stable_weakness_rate": stable / denominator,
        "wilson_95_interval": list(interval),
        "items": items,
    }


def _all_main_entries(selection: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    groups = selection.get("groups") or {}
    overlap = groups.get("strict_overlap_high_confidence") or []
    full = [item["full"] for item in overlap] + list(groups.get("full_only_high_confidence") or [])
    ablation = [item["ablation"] for item in overlap] + list(groups.get("ablation_only_random") or [])
    return full, ablation


def build_review(selection: dict[str, Any], exploratory: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if selection.get("human_review") != "pending" or selection.get("knowledge_base_updated") is not False:
        raise ValueError("selection must remain pending and must not update the knowledge base")
    full_entries, ablation_entries = _all_main_entries(selection)
    executable_pairs = executable_overlap_pairs(full_entries, ablation_entries)
    full = summarize_method(full_entries)
    ablation = summarize_method(ablation_entries)
    fisher = fisher_exact_two_sided(
        full["counts"]["stable_weakness"],
        full["denominator"] - full["counts"]["stable_weakness"],
        ablation["counts"]["stable_weakness"],
        ablation["denominator"] - ablation["counts"]["stable_weakness"],
    )
    return {
        "schema_version": "sock-shop-r5-dedup-review-v1",
        "selection_basis": selection.get("selection_basis") or {},
        "methods": {"native-full": full, "chaosatlas-ablation": ablation},
        "statistics": {
            "fisher_exact_two_sided": fisher,
            "interpretation": "small_sample_no_general_superiority_claim",
        },
        "identity_sensitivity": {
            "registered_strict_overlap_count": len(
                (selection.get("groups") or {}).get("strict_overlap_high_confidence") or []
            ),
            "executable_overlap_count": len(executable_pairs),
            "reworded_call_chain_collisions": sum(not item["strict_instance_match"] for item in executable_pairs),
            "executable_overlap_pairs": executable_pairs,
        },
        "excluded_from_main_denominator": list(
            (selection.get("excluded") or {}).get("ablation_runtime_extra_not_in_main_denominator") or []
        ),
        "exploratory": exploratory or [],
        "human_review": "pending",
        "knowledge_base_updated": False,
    }


def _percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def render_markdown(review: dict[str, Any]) -> str:
    full = review["methods"]["native-full"]
    ablation = review["methods"]["chaosatlas-ablation"]
    fisher = review["statistics"]["fisher_exact_two_sided"]
    excluded = review.get("excluded_from_main_denominator") or []
    sensitivity = review.get("identity_sensitivity") or {}

    lines = [
        "# Sock Shop R5 去重后两臂证据审核",
        "",
        "## 主结果",
        "",
        "| 方法 | 稳定弱点 | 不稳定 | 非弱点 | 分母 | 稳定弱点率 | Wilson 95% CI |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for label, summary in (("native-full", full), ("ChaosAtlas-ablation", ablation)):
        counts = summary["counts"]
        low, high = summary["wilson_95_interval"]
        lines.append(
            f"| {label} | {counts['stable_weakness']} | {counts['unstable']} | {counts['no_impact']} | "
            f"{summary['denominator']} | {_percent(summary['stable_weakness_rate'])} | "
            f"{_percent(low)} - {_percent(high)} |"
        )
    odds = fisher["odds_ratio"]
    lines.extend(
        [
            "",
            f"Fisher 双侧精确检验：odds ratio = {odds:.3g}，p = {fisher['p_value']:.3g}。",
            "",
            "两臂在本次冻结主样本中的稳定弱点率相同。小样本且区间很宽，不能据此宣称两种方法具有普遍性优劣。",
            "",
            "## 统计口径",
            "",
            "- 两次均为 `weakness_observed` 才计为稳定弱点。",
            "- 仅一次复现单列为不稳定，不计入稳定弱点分子。",
            "- 分母仅包含 gate 通过、两次生命周期完成且证据校验通过的冻结 mutation。",
        ]
    )
    if excluded:
        lines.append(f"- `{', '.join(excluded)}` 属于额外运行样本，仅作 exploratory 观察，不进入主分母。")
    if sensitivity:
        lines.extend(
            [
                "",
                "## 身份敏感性",
                "",
                f"- 注册的 strict overlap 为 {sensitivity['registered_strict_overlap_count']} 个。",
                f"- 忽略文字化调用链位置、只比较实际 Chaos mutation 后，executable overlap 为 {sensitivity['executable_overlap_count']} 个。",
                f"- 其中 {sensitivity['reworded_call_chain_collisions']} 对仅因调用链措辞不同而被分入 only 集合；主统计不事后改样本，但 only 集合不能解释为完全不同的物理故障。",
            ]
        )
    lines.extend(
        [
            "",
            "## 审核状态",
            "",
            f"- human review: `{review['human_review']}`",
            f"- knowledge base updated: `{str(review['knowledge_base_updated']).lower()}`",
            "",
        ]
    )
    return "\n".join(lines)


def _resolve(path: str) -> Path:
    value = Path(path)
    if value.is_file():
        return value
    candidate = ROOT / value
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(path)


def revalidate_selection(selection: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    verified = copy.deepcopy(selection)
    full_entries, ablation_entries = _all_main_entries(verified)
    report_count = 0
    diagnostic_count = 0
    failures = []
    for entry in full_entries + ablation_entries:
        evidence = entry.get("evidence") or {}
        refreshed = []
        for embedded in evidence.get("reports") or []:
            report_count += 1
            actual = validate_runtime_report(_resolve(str(embedded.get("path") or "")))
            diagnostic_count += len(actual.get("diagnostic_files") or [])
            if actual.get("report_sha256") != embedded.get("report_sha256"):
                actual.setdefault("reasons", []).append("report_sha256_changed_since_selection")
                actual["valid"] = False
            if actual.get("classification") != embedded.get("classification"):
                actual.setdefault("reasons", []).append("classification_changed_since_selection")
                actual["valid"] = False
            if embedded.get("mutation_instance_key"):
                actual["mutation_instance_key"] = embedded["mutation_instance_key"]
            if not actual["valid"]:
                failures.append({"path": actual.get("path"), "reasons": actual.get("reasons")})
            refreshed.append(actual)
        evidence["reports"] = refreshed
        evidence["valid"] = len(refreshed) == 2 and all(item["valid"] for item in refreshed)
    verification = {
        "main_reports_revalidated": report_count,
        "diagnostic_files_rehashed": diagnostic_count,
        "failures": failures,
        "all_valid": not failures,
    }
    if failures:
        raise ValueError(f"evidence revalidation failed for {len(failures)} reports")
    return verified, verification


def load_exploratory(progress_path: Path, hypothesis_ids: Iterable[str]) -> list[dict[str, Any]]:
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    wanted = set(hypothesis_ids)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in progress.get("rows") or []:
        hypothesis_id = str(row.get("hypothesis_id"))
        if hypothesis_id in wanted:
            grouped[hypothesis_id].append(validate_runtime_report(_resolve(str(row.get("report_path") or ""))))
    result = []
    for hypothesis_id in sorted(wanted):
        reports = sorted(grouped.get(hypothesis_id) or [], key=lambda item: int(item.get("replicate") or 0))
        if len(reports) != 2 or not all(item["valid"] for item in reports):
            raise ValueError(f"invalid exploratory evidence: {hypothesis_id}")
        result.append(
            {
                "hypothesis_id": hypothesis_id,
                "classification": classify_pair(item["classification"] for item in reports),
                "replicate_classifications": [item["classification"] for item in reports],
                "included_in_main_denominator": False,
            }
        )
    return result


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--ablation-progress", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty output directory: {args.output}")
    args.output.mkdir(parents=True, exist_ok=True)

    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    verified, verification = revalidate_selection(selection)
    excluded = (selection.get("excluded") or {}).get("ablation_runtime_extra_not_in_main_denominator") or []
    exploratory = load_exploratory(args.ablation_progress, excluded)
    review = build_review(verified, exploratory)
    review["evidence_verification"] = verification

    json_path = args.output / "review.json"
    markdown_path = args.output / "REVIEW.zh-CN.md"
    json_path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_markdown(review), encoding="utf-8")
    (args.output / "SHA256SUMS").write_text(
        f"{_sha(json_path)}  {json_path.name}\n{_sha(markdown_path)}  {markdown_path.name}\n",
        encoding="utf-8",
    )
    print(json.dumps({"methods": review["methods"], "statistics": review["statistics"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
