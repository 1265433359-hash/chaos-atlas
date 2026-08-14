from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_reports(root: Path) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.json")):
        if path.parent.name != "runtime_reports":
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict) or "status" not in value:
            continue
        value["_path"] = str(path)
        reports.append(value)
    return reports


def _mutation_id(report: dict[str, Any]) -> str:
    return str(
        report.get("mutation_id")
        or report.get("hypothesis_id")
        or (report.get("mutation") or {}).get("sha256")
        or report.get("_path")
    )


def _classification(report: dict[str, Any]) -> str:
    return str((report.get("observation") or {}).get("classification") or report.get("classification") or "unknown")


def _infer_category_from_mutation_id(mutation_id: str) -> str:
    value = mutation_id.lower()
    if value.startswith("pod-"):
        return "Pod disruption"
    if value.startswith("net-"):
        return "Network degradation"
    if value.startswith("res-"):
        return "Resource pressure"
    if value.startswith("http-") or value.startswith("dns-"):
        return "Protocol/HTTP fault"
    if value.startswith("composite-") or value.startswith("schedule-"):
        return "Composite/scheduled fault"
    return "unknown"


def _category(report: dict[str, Any]) -> str:
    return str(
        report.get("category")
        or report.get("fault_category")
        or _infer_category_from_mutation_id(_mutation_id(report))
    )


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _derive_wall_clock_seconds(reports: list[dict[str, Any]]) -> float | None:
    starts = []
    ends = []
    for report in reports:
        started = _parse_timestamp(report.get("started_at"))
        finished = _parse_timestamp(report.get("finished_at"))
        if started is not None and finished is not None:
            starts.append(started)
            ends.append(finished)
    if not starts or not ends:
        return None
    return round((max(ends) - min(starts)).total_seconds(), 3)


def _summarize_method(reports: list[dict[str, Any]], total_seconds: float | None) -> dict[str, Any]:
    if total_seconds is None:
        total_seconds = _derive_wall_clock_seconds(reports)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    invalid_runtime = 0
    for report in reports:
        if report.get("status") != "completed":
            invalid_runtime += 1
            continue
        groups[_mutation_id(report)].append(report)

    stable = 0
    unstable = 0
    no_impact = 0
    categories: dict[str, dict[str, int]] = defaultdict(lambda: {"stable_weakness": 0, "unstable_or_nonrepeatable": 0, "no_business_impact_observed": 0})
    mutations: list[dict[str, Any]] = []
    for mutation_id, rows in groups.items():
        classifications = [_classification(row) for row in rows]
        category = _category(rows[0])
        if len(rows) >= 2 and all(item == "weakness_observed" for item in classifications):
            outcome = "stable_weakness"
            stable += 1
        elif any(item == "weakness_observed" for item in classifications):
            outcome = "unstable_or_nonrepeatable"
            unstable += 1
        elif rows and all(item == "no_business_impact_observed" for item in classifications):
            outcome = "no_business_impact_observed"
            no_impact += 1
        else:
            outcome = "invalid_runtime"
            invalid_runtime += 1
        if outcome in categories[category]:
            categories[category][outcome] += 1
        mutations.append(
            {
                "mutation_id": mutation_id,
                "category": category,
                "replicates": len(rows),
                "classifications": classifications,
                "outcome": outcome,
            }
        )

    hours = (total_seconds / 3600) if total_seconds else None
    per_hour = round(stable / hours, 3) if hours else None
    completed_replicates = sum(len(rows) for rows in groups.values())
    return {
        "reports": len(reports),
        "completed_replicates": completed_replicates,
        "runtime_candidates": len(groups),
        "stable_weaknesses": stable,
        "unstable_or_nonrepeatable": unstable,
        "no_business_impact_observed": no_impact,
        "invalid_runtime": invalid_runtime,
        "gate_failed": 0,
        "hit_rate": round(stable / len(groups), 4) if groups else 0.0,
        "total_wall_clock_seconds": total_seconds,
        "stable_weaknesses_per_hour": per_hour,
        "categories": {category: dict(values) for category, values in categories.items()},
        "mutations": sorted(mutations, key=lambda item: item["mutation_id"]),
    }


def _markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Sock Shop YAML Confidence Native vs Ablation Review",
        "",
        "本报告只把同一 mutation 至少 2 次 completed replicate 都出现业务失败的候选标为稳定真实弱点。",
        "业务弱点不等于具体内部根因；没有额外 RCA 证据时，不推断缓存、注册、重试或服务发现机制。",
        "",
        "- human_review: pending",
        "- knowledge_base_updated: false",
        "",
        "| 方法 | runtime 候选 | 稳定弱点 | 不稳定 | 非弱点 | invalid | 命中率 | 总耗时(s) | 稳定弱点/小时 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for method, data in summary["methods"].items():
        lines.append(
            "| {method} | {runtime_candidates} | {stable_weaknesses} | {unstable_or_nonrepeatable} | {no_business_impact_observed} | {invalid_runtime} | {hit_rate:.2%} | {time} | {per_hour} |".format(
                method=method,
                time=data.get("total_wall_clock_seconds"),
                per_hour=data.get("stable_weaknesses_per_hour"),
                **data,
            )
        )
    lines.extend(["", "## Category Contribution", ""])
    lines.append("| 方法 | 大类 | 稳定弱点 | 不稳定 | 非弱点 |")
    lines.append("|---|---|---:|---:|---:|")
    for method, data in summary["methods"].items():
        for category, values in data["categories"].items():
            lines.append(
                f"| {method} | {category} | {values.get('stable_weakness', 0)} | {values.get('unstable_or_nonrepeatable', 0)} | {values.get('no_business_impact_observed', 0)} |"
            )
    lines.extend(
        [
            "",
            "## Boundaries",
            "",
            "- 方法本体没有修改；修改的是假设生成条件。",
            "- 两方法使用同一套 5 大类与置信停止规则。",
            "- 不要求相同 runtime 预算；时间成本是实验结果。",
            "- pending 审核结果不会自动写入知识库。",
        ]
    )
    return "\n".join(lines) + "\n"


def review_confidence_experiment(
    method_report_roots: dict[str, Path],
    timing: dict[str, dict[str, float | None]] | None = None,
    output_markdown: Path | None = None,
) -> dict[str, Any]:
    timing = timing or {}
    methods = {
        method: _summarize_method(
            _load_reports(root),
            timing.get(method, {}).get("total_wall_clock_seconds"),
        )
        for method, root in method_report_roots.items()
    }
    summary = {
        "experiment": "sock_shop_yaml_confidence",
        "methods": methods,
        "human_review": "pending",
        "knowledge_base_updated": False,
    }
    if output_markdown:
        output_markdown.parent.mkdir(parents=True, exist_ok=True)
        output_markdown.write_text(_markdown(summary), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--method-root", action="append", required=True, help="method=path")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()

    roots = {}
    for item in args.method_root:
        method, path = item.split("=", 1)
        roots[method] = Path(path)
    summary = review_confidence_experiment(roots, output_markdown=args.output_md)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"methods": list(summary["methods"]), "output": str(args.output_json)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
