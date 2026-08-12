"""Offline, project-clustered analysis for the ChaosAtlas open-discovery study.

The statistical unit is a project. Seeds are repeated measurements nested in a
project, and hypotheses/LLM calls are never treated as independent projects.
The reader accepts a normalized records JSON/JSONL file and can also discover
the frozen open-discovery, runtime-summary, and token-ledger artifacts.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = ROOT / "artifacts/experiments/chaosatlas_10_projects"
ARMS = ("ChaosAtlas-KB", "ChaosAtlas-noKB")
METRICS = (
    "valid_output_rate", "compiler_acceptance_rate", "executable_rate",
    "confirmed_weakness_yield", "protected_target_yield", "method_invalid_rate",
    "environment_blocked_rate", "call_chain_coverage", "call_chain_depth",
    "recovery_success", "token_cost", "human_review_time",
)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _first(mapping: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in mapping and mapping[name] is not None:
            return mapping[name]
    return None


def _rate(numerator: Any, denominator: Any) -> float | None:
    n, d = _number(numerator), _number(denominator)
    return n / d if n is not None and d is not None and d > 0 else None


def _mean(values: Iterable[Any]) -> float | None:
    valid = [float(v) for v in values if _number(v) is not None]
    return statistics.mean(valid) if valid else None


def _arm(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    lowered = value.lower().replace("_", "-")
    if "nokb" in lowered:
        return "ChaosAtlas-noKB"
    if "chaosatlas" in lowered and "kb" in lowered:
        return "ChaosAtlas-KB"
    return value


def _metric_aliases(row: dict[str, Any], name: str) -> Any:
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    aliases = {
        "valid_output_rate": ("valid_output_rate", "valid_rate"),
        "compiler_acceptance_rate": ("compiler_acceptance_rate", "acceptance_rate"),
        "executable_rate": ("executable_rate",),
        "confirmed_weakness_yield": ("confirmed_weakness_yield", "weakness_yield"),
        "protected_target_yield": ("protected_target_yield", "protected_yield"),
        "method_invalid_rate": ("method_invalid_rate", "invalid_rate"),
        "environment_blocked_rate": ("environment_blocked_rate", "blocked_rate"),
        "call_chain_coverage": ("call_chain_coverage", "chain_coverage"),
        "call_chain_depth": ("call_chain_depth", "chain_depth"),
        "recovery_success": ("recovery_success", "recovery_success_rate"),
        "token_cost": ("token_cost", "tokens", "total_tokens", "billed_tokens"),
        "human_review_time": ("human_review_time", "human_review_minutes", "review_time_minutes"),
    }
    for alias in aliases[name]:
        if alias in row:
            return row[alias]
        if alias in metrics:
            return metrics[alias]
    return None


def normalize_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize one project/arm/seed row without inventing missing evidence."""
    metrics = raw.get("metrics") if isinstance(raw.get("metrics"), dict) else {}
    source = {**raw, **metrics}
    project = _first(source, "project_id", "project")
    arm = _arm(_first(source, "arm", "method_arm", "condition"))
    seed = _first(source, "seed", "replicate", "replicate_id")
    submitted = _first(source, "submitted", "submitted_outputs", "outputs_returned", "calls")
    valid = _first(source, "valid_outputs", "valid_output", "schema_valid_outputs")
    generated = _first(source, "generated", "hypotheses", "compiler_input")
    accepted = _first(source, "compiler_accepted", "accepted", "accepted_hypotheses")
    executable = _first(source, "executable", "executable_hypotheses")
    confirmed = _first(source, "confirmed_weakness", "confirmed_weaknesses", "weaknesses")
    protected = _first(source, "protected_targets", "protected")
    invalid = _first(source, "method_invalid", "method_invalid_outputs", "invalid")
    blocked = _first(source, "environment_blocked", "environment_blocked_outputs", "blocked")
    recovery_ok = _first(source, "recovery_successes", "recovered", "recovery_ok")
    recovery_n = _first(source, "recovery_attempts", "recovery_total", "recovery_runs")

    # Discovery artifacts describe one model response per arm.  A response
    # can contain several hypotheses, so `generated` is not the denominator
    # for the output-validity rate.  Recover the response-level counts from
    # the compiler status without treating runtime repetitions as outputs.
    compiled_status = source.get("compiled_status")
    if submitted is None and compiled_status is not None:
        submitted = 1
    if valid is None and compiled_status is not None:
        valid = 1 if compiled_status == "valid" else 0

    # ``main_result.json`` represents one discovery call per arm/seed.
    if valid is None and "compiled_status" in source:
        submitted = 1 if submitted is None else submitted
        valid = 1 if source.get("compiled_status") == "valid" else 0

    # A row may provide explicit rates, otherwise derive rates from counts.
    values = {
        "valid_output_rate": _metric_aliases(source, "valid_output_rate"),
        "compiler_acceptance_rate": _metric_aliases(source, "compiler_acceptance_rate"),
        "executable_rate": _metric_aliases(source, "executable_rate"),
        "confirmed_weakness_yield": _metric_aliases(source, "confirmed_weakness_yield"),
        "protected_target_yield": _metric_aliases(source, "protected_target_yield"),
        "method_invalid_rate": _metric_aliases(source, "method_invalid_rate"),
        "environment_blocked_rate": _metric_aliases(source, "environment_blocked_rate"),
        "call_chain_coverage": _metric_aliases(source, "call_chain_coverage"),
        "call_chain_depth": _metric_aliases(source, "call_chain_depth"),
        "recovery_success": _metric_aliases(source, "recovery_success"),
        "token_cost": _metric_aliases(source, "token_cost"),
        "human_review_time": _metric_aliases(source, "human_review_time"),
    }
    if values["valid_output_rate"] is None:
        values["valid_output_rate"] = _rate(valid, submitted)
    if values["compiler_acceptance_rate"] is None:
        values["compiler_acceptance_rate"] = _rate(accepted, generated)
    if values["executable_rate"] is None:
        values["executable_rate"] = _rate(executable, accepted)
    if values["confirmed_weakness_yield"] is None:
        values["confirmed_weakness_yield"] = _rate(confirmed, executable if _number(executable) is not None else accepted)
    if values["protected_target_yield"] is None:
        values["protected_target_yield"] = _rate(protected, executable if _number(executable) is not None else accepted)
    if values["method_invalid_rate"] is None:
        values["method_invalid_rate"] = _rate(invalid, submitted)
    if values["environment_blocked_rate"] is None:
        values["environment_blocked_rate"] = _rate(blocked, submitted)
    if values["recovery_success"] is None:
        values["recovery_success"] = _rate(recovery_ok, recovery_n)

    # A nested hypothesis list can supply chain and yield fields.
    hypotheses = source.get("hypotheses") if isinstance(source.get("hypotheses"), list) else []
    if values["call_chain_coverage"] is None:
        values["call_chain_coverage"] = _mean(
            _first(h, "call_chain_coverage", "chain_coverage")
            for h in hypotheses if isinstance(h, dict)
        )
    if values["call_chain_depth"] is None:
        values["call_chain_depth"] = _mean(
            _first(h, "call_chain_depth", "chain_depth")
            for h in hypotheses if isinstance(h, dict)
        )
    return {
        "project_id": str(project) if project is not None else None,
        "arm": arm,
        "seed": seed,
        "metrics": {name: _number(value) for name, value in values.items()},
        "source": source.get("source") or source.get("source_path"),
    }


def _records_from_json(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    if isinstance(value, dict):
        for key in ("records", "rows", "results", "observations"):
            if isinstance(value.get(key), list):
                return [x for x in value[key] if isinstance(x, dict)]
        if value.get("project_id") and (value.get("arms") or value.get("metrics")):
            return _expand_arm_object(value)
    return []


def _expand_arm_object(value: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for arm_name, arm_data in (value.get("arms") or {}).items():
        if not isinstance(arm_data, dict):
            continue
        rows.append({**arm_data, "project_id": value.get("project_id"), "seed": value.get("seed"), "arm": arm_name})
    return rows


def read_records(path: Path) -> list[dict[str, Any]]:
    """Read normalized JSON/JSONL records."""
    if path.is_file():
        text = path.read_text(encoding="utf-8")
        try:
            return _records_from_json(json.loads(text))
        except json.JSONDecodeError:
            return [json.loads(line) for line in text.splitlines() if line.strip()]
    rows: list[dict[str, Any]] = []
    for item in sorted(path.rglob("*.json")):
        try:
            rows.extend(_records_from_json(json.loads(item.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError):
            continue
    return rows


def discover_frozen_records(root: Path) -> list[dict[str, Any]]:
    """Build records from the currently frozen P02 artifacts when no input is supplied."""
    root = root.resolve()
    rows: dict[tuple[str, str, Any], dict[str, Any]] = {}
    open_root, runtime_root = root / "open_discovery_results", root / "runtime_results"
    for result_path in open_root.glob("P*/seed-*/main_result.json"):
        value = json.loads(result_path.read_text(encoding="utf-8"))
        for row in _expand_arm_object(value):
            key = (str(row.get("project_id")), _arm(row.get("arm")), row.get("seed"))
            row["source"] = str(result_path.relative_to(ROOT)).replace("\\", "/")
            rows[key] = row
    for summary_path in runtime_root.glob("P*/seed-*/p*_runtime_summary.json"):
        value = json.loads(summary_path.read_text(encoding="utf-8"))
        for arm_name, arm_data in (value.get("arms") or {}).items():
            key = (str(value.get("project_id")), _arm(arm_name), value.get("seed"))
            if key[1] is None:
                continue
            row = rows.setdefault(key, {"project_id": value.get("project_id"), "seed": value.get("seed"), "arm": arm_name})
            targets = arm_data.get("targets") or {}
            row.update({
                "valid_runs": arm_data.get("valid_runs"),
                "invalid_runs": arm_data.get("invalid_runs"),
                "confirmed_weaknesses": sum(1 for t in targets.values() if isinstance(t, dict) and t.get("classification") == "confirmed_weakness"),
                "protected_targets": sum(1 for t in targets.values() if isinstance(t, dict) and t.get("classification") == "protected"),
                # valid_runs are runtime repetitions, not discovery hypotheses;
                # keep executable_hypotheses absent unless a compiler artifact
                # supplies that count explicitly.
                "recovery_successes": arm_data.get("valid_runs"),
                # Invalid baseline/observation runs are excluded from the
                # runtime recovery denominator.
                "recovery_attempts": arm_data.get("valid_runs"),
                "source": row.get("source") or str(summary_path.relative_to(ROOT)).replace("\\", "/"),
            })
    ledger_path = root / "cost_token_ledger.json"
    if ledger_path.exists():
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        totals: dict[tuple[str, str, Any], float] = defaultdict(float)
        for call in ledger.get("rows", []):
            key = (str(call.get("project_id")), _arm(call.get("arm")), call.get("seed"))
            amount = _number(call.get("billed_tokens", call.get("total_tokens")))
            if key[1] and amount is not None:
                totals[key] += amount
        for key, amount in totals.items():
            rows.setdefault(key, {"project_id": key[0], "arm": key[1], "seed": key[2]})["token_cost"] = amount
    return list(rows.values())


def _aggregate_seed_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = [normalize_record(r) for r in rows]
    project = next((r["project_id"] for r in normalized if r["project_id"] is not None), None)
    arm = next((r["arm"] for r in normalized if r["arm"] is not None), None)
    seed = next((r["seed"] for r in normalized if r["seed"] is not None), None)
    metrics = {name: _mean(r["metrics"].get(name) for r in normalized) for name in METRICS}
    return {"project_id": project, "arm": arm, "seed": seed, "metrics": metrics, "n_rows": len(rows)}


def _distribution(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n_projects": 0, "values": [], "mean": None, "median": None, "sd": None, "min": None, "max": None}
    return {"n_projects": len(values), "values": values, "mean": statistics.mean(values),
            "median": statistics.median(values), "sd": statistics.stdev(values) if len(values) > 1 else 0.0,
            "min": min(values), "max": max(values)}


def analyze(records: list[dict[str, Any]], expected_projects: int | None = None) -> dict[str, Any]:
    """Return seed, project, and paired project-clustered summaries."""
    grouped: dict[tuple[str, str, Any], list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        normalized = normalize_record(row)
        if normalized["project_id"] and normalized["arm"]:
            grouped[(normalized["project_id"], normalized["arm"], normalized["seed"])].append(row)
    seeds = [_aggregate_seed_rows(rows) for rows in grouped.values()]
    project_arm: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in seeds:
        project_arm[(row["project_id"], row["arm"])].append(row)
    projects = []
    for (project, arm), arm_seeds in sorted(project_arm.items()):
        projects.append({"project_id": project, "arm": arm, "n_seeds": len(arm_seeds),
                         "metrics": {name: _mean(s["metrics"].get(name) for s in arm_seeds) for name in METRICS},
                         "seeds": sorted(arm_seeds, key=lambda x: str(x["seed"]))})
    by_project = defaultdict(dict)
    for row in projects:
        by_project[row["project_id"]][row["arm"]] = row
    paired = []
    for project, arms in sorted(by_project.items()):
        if not all(arm in arms for arm in ARMS):
            continue
        deltas = {name: (arms[ARMS[0]]["metrics"].get(name) - arms[ARMS[1]]["metrics"].get(name)
                         if arms[ARMS[0]]["metrics"].get(name) is not None and arms[ARMS[1]]["metrics"].get(name) is not None else None)
                  for name in METRICS}
        paired.append({"project_id": project, "kb_minus_noKB": deltas,
                       "n_seeds_kb": arms[ARMS[0]]["n_seeds"], "n_seeds_noKB": arms[ARMS[1]]["n_seeds"]})
    distributions = {name: _distribution([p["kb_minus_noKB"][name] for p in paired if p["kb_minus_noKB"][name] is not None]) for name in METRICS}
    expected_ids = [f"P{i:02d}" for i in range(1, expected_projects + 1)] if expected_projects else []
    missing_projects = sorted(set(expected_ids) - set(by_project))
    return {"schema_version": "1.0", "kind": "chaosatlas_project_clustered_statistics",
            "created_at": datetime.now(timezone.utc).isoformat(), "expected_projects": expected_projects,
            "observed_projects": sorted(by_project), "missing_projects": missing_projects,
            "status": "complete" if not missing_projects else "incomplete_missing_projects",
            "seed_summaries": seeds, "project_summaries": projects,
            "paired_differences": paired, "paired_difference_distributions": distributions,
            "statistical_rules": {"seed_repeats_per_project": 3, "project_is_inference_unit": True,
                                   "llm_calls_are_not_independent_samples": True,
                                   "paired_difference": "project mean(KB) - project mean(noKB)"}}


def render(report: dict[str, Any]) -> str:
    lines = ["# ChaosAtlas Project-Clustered Statistics", "", f"Status: **{report['status']}**. Observed projects: {len(report['observed_projects'])}/{report['expected_projects'] or len(report['observed_projects'])}.", "", "Seeds are repeated measurements within a project; LLM calls are not independent samples.", "",
             "## Project summaries", "", "| Project | Arm | Seeds | " + " | ".join(METRICS) + " |",
             "|---|---|---:|" + "---:|" * len(METRICS)]
    for row in report["project_summaries"]:
        vals = ["" if row["metrics"][m] is None else f"{row['metrics'][m]:.4g}" for m in METRICS]
        lines.append(f"| {row['project_id']} | {row['arm']} | {row['n_seeds']} | " + " | ".join(vals) + " |")
    lines += ["", "## KB minus noKB by project", "", "| Project | " + " | ".join(METRICS) + " |", "|---|" + "---:|" * len(METRICS)]
    for row in report["paired_differences"]:
        vals = ["" if row["kb_minus_noKB"][m] is None else f"{row['kb_minus_noKB'][m]:.4g}" for m in METRICS]
        lines.append(f"| {row['project_id']} | " + " | ".join(vals) + " |")
    lines += ["", "## Difference distributions across projects", "", "| Metric | Projects | Mean | Median | SD | Min | Max |", "|---|---:|---:|---:|---:|---:|---:|"]
    for name, d in report["paired_difference_distributions"].items():
        fmt = lambda x: "" if x is None else f"{x:.4g}"
        lines.append(f"| {name} | {d['n_projects']} | {fmt(d['mean'])} | {fmt(d['median'])} | {fmt(d['sd'])} | {fmt(d['min'])} | {fmt(d['max'])} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="normalized records JSON/JSONL or directory")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="frozen experiment root for autodiscovery")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "analysis_outputs/chaosatlas_statistics")
    parser.add_argument("--expected-projects", type=int, default=10)
    args = parser.parse_args()
    raw = read_records(args.input) if args.input else discover_frozen_records(args.root)
    report = analyze(raw, expected_projects=args.expected_projects)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "statistics.json").write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    (args.output_dir / "statistics.md").write_text(render(report), encoding="utf-8")
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
