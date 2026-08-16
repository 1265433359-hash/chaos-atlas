"""Classify the raw YAML corpus into the five controlled fault categories.

The classifier is a deterministic static inventory pass.  It measures kind,
action, selector, duration, intensity, and motif distributions so the Full
discovery arm can derive category-specific stopping parameters.  These counts
describe the input corpus; they are not runtime weakness labels.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import NormalDist
from typing import Any

import yaml


YAML_CATEGORY_CONFIG: dict[str, dict[str, Any]] = {
    "Pod disruption": {
        "kinds": ["PodChaos"],
        "min": 3,
        "max": 6,
        "tau": 0.08,
        "coverage_target": 0.75,
    },
    "Network degradation": {
        "kinds": ["NetworkChaos"],
        "min": 4,
        "max": 8,
        "tau": 0.05,
        "coverage_target": 0.80,
    },
    "Resource pressure": {
        "kinds": ["StressChaos"],
        "min": 2,
        "max": 5,
        "tau": 0.08,
        "coverage_target": 0.70,
    },
    "Protocol/HTTP fault": {
        "kinds": ["HTTPChaos", "DNSChaos"],
        "min": 1,
        "max": 4,
        "tau": 0.10,
        "coverage_target": 0.60,
    },
    "Composite/scheduled fault": {
        "kinds": ["Workflow", "Schedule"],
        "min": 0,
        "max": 2,
        "tau": 0.15,
        "coverage_target": 0.50,
    },
}

_KIND_TO_CATEGORY = {
    kind: category
    for category, config in YAML_CATEGORY_CONFIG.items()
    for kind in config["kinds"]
}

_DURATION_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)(ms|s|m|h)\s*$")
_SIZE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)(Ki|Mi|Gi|Ti|K|M|G|T|B)?\s*$")


def classify_kind(kind: str | None) -> str | None:
    return _KIND_TO_CATEGORY.get(kind or "")


def _parse_seconds(value: Any) -> float | None:
    if value is None:
        return None
    match = _DURATION_RE.match(str(value))
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2)
    return amount * {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}[unit]


def _parse_percent(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().rstrip("%")
    try:
        return float(text)
    except ValueError:
        return None


def _parse_size_mib(value: Any) -> float | None:
    if value is None:
        return None
    match = _SIZE_RE.match(str(value))
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2) or "B"
    return amount * {
        "B": 1 / (1024 * 1024),
        "K": 1 / 1024,
        "Ki": 1 / 1024,
        "M": 1,
        "Mi": 1,
        "G": 1024,
        "Gi": 1024,
        "T": 1024 * 1024,
        "Ti": 1024 * 1024,
    }[unit]


def _bucket_numeric(value: float | None, low: float, high: float) -> str:
    if value is None:
        return "unknown"
    if value <= low:
        return "low"
    if value <= high:
        return "medium"
    return "high"


def bucket_duration(value: Any) -> str:
    seconds = _parse_seconds(value)
    if seconds is None:
        return "unknown"
    if seconds <= 60:
        return "short"
    if seconds <= 600:
        return "medium"
    return "long"


def selector_shape(spec: dict[str, Any]) -> str:
    selector = spec.get("selector") or {}
    if not isinstance(selector, dict) or not selector:
        return "empty-or-high-risk"
    labels = selector.get("labelSelectors") or {}
    namespaces = selector.get("namespaces") or []
    if isinstance(labels, dict) and labels.get("app"):
        return "app-label"
    if isinstance(labels, dict) and len(labels) > 1:
        return "multi-label"
    if namespaces and not labels:
        return "namespace-only"
    return "other-selector"


def _stressors(spec: dict[str, Any]) -> dict[str, Any]:
    stressors = spec.get("stressors") or {}
    return stressors if isinstance(stressors, dict) else {}


def action_or_target(kind: str, spec: dict[str, Any]) -> str:
    if kind == "StressChaos":
        stressors = _stressors(spec)
        if "cpu" in stressors and "memory" in stressors:
            return "cpu+memory"
        if "cpu" in stressors:
            return "cpu"
        if "memory" in stressors:
            return "memory"
    if kind == "HTTPChaos":
        return str(spec.get("target") or spec.get("method") or spec.get("path") or "http")
    if kind == "DNSChaos":
        return str(spec.get("action") or "dns")
    if kind == "PodChaos":
        return str(spec.get("action") or "pod-kill")
    return str(spec.get("action") or spec.get("target") or "unknown")


def intensity_bucket(kind: str, spec: dict[str, Any]) -> str:
    if kind == "NetworkChaos":
        action = str(spec.get("action") or "")
        if action == "delay":
            latency = (spec.get("delay") or {}).get("latency") if isinstance(spec.get("delay"), dict) else None
            return _bucket_numeric(_parse_seconds(latency), 0.2, 2.0)
        if action == "loss":
            loss = (spec.get("loss") or {}).get("loss") if isinstance(spec.get("loss"), dict) else None
            return _bucket_numeric(_parse_percent(loss), 5, 25)
        if action == "bandwidth":
            return "bandwidth-present"
        if action == "partition":
            return "partition"
    if kind == "StressChaos":
        stressors = _stressors(spec)
        cpu = stressors.get("cpu") if isinstance(stressors.get("cpu"), dict) else {}
        memory = stressors.get("memory") if isinstance(stressors.get("memory"), dict) else {}
        if "load" in cpu:
            return _bucket_numeric(_parse_percent(cpu.get("load")), 50, 90)
        if "size" in memory:
            return _bucket_numeric(_parse_size_mib(memory.get("size")), 256, 1024)
    return "unknown"


def extract_yaml_features(path: str, doc: dict[str, Any]) -> dict[str, Any]:
    kind = doc.get("kind")
    spec = doc.get("spec") or {}
    if not isinstance(spec, dict):
        spec = {}
    category = classify_kind(kind)
    return {
        "path": path,
        "sha256": "",
        "kind": kind,
        "category": category,
        "included_in_runtime_scope": category is not None,
        "action_or_target": action_or_target(kind or "", spec),
        "mode": str(spec.get("mode") or "unknown"),
        "selector_shape": selector_shape(spec),
        "duration_bucket": bucket_duration(spec.get("duration")),
        "intensity_bucket": intensity_bucket(kind or "", spec),
        "scheduler_present": bool(spec.get("scheduler") or kind in {"Workflow", "Schedule"}),
        "parse_error": None,
    }


def _fallback_row(file_path: Path, parse_error: str | None = None) -> dict[str, Any]:
    kind = file_path.parent.name
    category = classify_kind(kind)
    return {
        "path": str(file_path),
        "sha256": hashlib.sha256(file_path.read_bytes()).hexdigest(),
        "kind": kind,
        "category": category,
        "included_in_runtime_scope": category is not None,
        "action_or_target": "unknown",
        "mode": "unknown",
        "selector_shape": "unknown",
        "duration_bucket": "unknown",
        "intensity_bucket": "unknown",
        "scheduler_present": kind in {"Workflow", "Schedule"},
        "parse_error": parse_error,
    }


def load_yaml_feature_rows(raw_yaml_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for file_path in sorted(raw_yaml_root.glob("*/*.yaml")):
        try:
            doc = yaml.safe_load(file_path.read_text(encoding="utf-8"))
        except Exception as exc:
            rows.append(_fallback_row(file_path, str(exc)))
            continue
        if not isinstance(doc, dict):
            rows.append(_fallback_row(file_path, "document is not a mapping"))
            continue
        row = extract_yaml_features(str(file_path), doc)
        row["sha256"] = hashlib.sha256(file_path.read_bytes()).hexdigest()
        if not row.get("kind"):
            row["kind"] = file_path.parent.name
            row["category"] = classify_kind(row["kind"])
            row["included_in_runtime_scope"] = row["category"] is not None
        rows.append(row)
    return rows


def _entropy(values: list[str]) -> float:
    counts = Counter(values)
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def _normalized_entropy(values: list[str]) -> float:
    """Normalize entropy by the number of observed values in one feature."""
    distinct = len(set(values))
    if distinct <= 1:
        return 0.0
    maximum = math.log2(distinct)
    return _entropy(values) / maximum if maximum else 0.0


def _feature_complexity(rows: list[dict[str, Any]]) -> float:
    fields = [
        "action_or_target",
        "mode",
        "selector_shape",
        "duration_bucket",
        "intensity_bucket",
    ]
    if not rows:
        return 0.0
    ratios = [
        _normalized_entropy([str(row.get(field, "unknown")) for row in rows])
        for field in fields
    ]
    return sum(ratios) / len(ratios)


def _posterior_upper95(novel_count: int, duplicate_count: int) -> float:
    alpha = 1 + novel_count
    beta = 1 + duplicate_count
    mean = alpha / (alpha + beta)
    variance = (alpha * beta) / (((alpha + beta) ** 2) * (alpha + beta + 1))
    return max(0.0, min(1.0, mean + NormalDist().inv_cdf(0.95) * math.sqrt(variance)))


def _duplicates_needed(novel_count: int, tau: float) -> int:
    for duplicate_count in range(0, 4097):
        if _posterior_upper95(novel_count, duplicate_count) < tau:
            return duplicate_count
    return 4096


def _confidence_policy(
    config: dict[str, Any],
    rows: list[dict[str, Any]],
    complexity: float,
    motif_count: int,
) -> dict[str, Any]:
    """Derive stopping parameters from frozen corpus features, not runtime outcomes."""
    count = len(rows)
    if count == 0:
        return {
            "min_hypotheses": 0,
            "max_hypotheses": 0,
            "tau": round(max(0.12, config["tau"]), 4),
            "coverage_target": round(max(0.60, config["coverage_target"]), 4),
            "formula": "empty category: no hypotheses are generated",
            "runtime_outcomes_used": False,
        }
    minimum = max(config["min"], min(12, math.ceil(math.log2(max(2, count + 1)))))
    tau = round(min(0.25, max(0.12, 0.12 + 0.08 * complexity + 0.01 * math.log10(max(1, count)))), 4)
    coverage = round(min(0.90, max(0.60, 0.62 + 0.22 * complexity)), 4)
    novelty_slack = max(4, math.ceil(math.sqrt(count)))
    expected_novel = max(1, motif_count + 4 + math.ceil(8 * complexity) + novelty_slack)
    duplicate_tail = _duplicates_needed(expected_novel, tau)
    safety_margin = math.ceil(2 * math.sqrt(count))
    maximum = min(2048, max(minimum + 8, expected_novel + duplicate_tail + safety_margin))
    return {
        "min_hypotheses": minimum,
        "max_hypotheses": maximum,
        "tau": tau,
        "coverage_target": coverage,
        "formula": "complexity=mean normalized entropy; tau=clamp(0.12+0.08*complexity+0.01*log10(count),0.12,0.25); coverage=clamp(0.62+0.22*complexity,0.60,0.90); novelty_slack=max(4,ceil(sqrt(count))); max=expected_novel+beta_tail(tau)+2*sqrt(count)",
        "expected_novel": expected_novel,
        "novelty_slack": novelty_slack,
        "duplicate_tail_required": duplicate_tail,
        "safety_margin": safety_margin,
        "runtime_outcomes_used": False,
    }


def _motifs(rows: list[dict[str, Any]], class_count: int) -> list[dict[str, Any]]:
    if class_count == 0:
        return []
    fields = [
        "action_or_target",
        "mode",
        "selector_shape",
        "duration_bucket",
        "intensity_bucket",
    ]
    counts: Counter[str] = Counter()
    for row in rows:
        for field in fields:
            counts[f"{field}={row.get(field, 'unknown')}"] += 1
    min_support = max(1, math.ceil(class_count * 0.05))
    return [
        {
            "motif": motif,
            "support": support,
            "support_ratio": round(support / class_count, 4),
        }
        for motif, support in counts.most_common()
        if support >= min_support
    ][:12]


def _pairwise_lift(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields = ["action_or_target", "mode", "selector_shape", "duration_bucket", "intensity_bucket"]
    total = len(rows)
    if total == 0:
        return []
    singles: Counter[str] = Counter()
    pairs: Counter[tuple[str, str]] = Counter()
    for row in rows:
        values = [f"{field}={row.get(field, 'unknown')}" for field in fields]
        singles.update(values)
        for index, left in enumerate(values):
            for right in values[index + 1 :]:
                pairs[(left, right)] += 1
    lifted = []
    for (left, right), support in pairs.items():
        expected = (singles[left] / total) * (singles[right] / total)
        observed = support / total
        lift = observed / expected if expected else 0.0
        if support >= max(1, math.ceil(total * 0.05)) and lift >= 1.5:
            lifted.append(
                {
                    "pair": [left, right],
                    "support": support,
                    "support_ratio": round(observed, 4),
                    "lift": round(lift, 4),
                }
            )
    return sorted(lifted, key=lambda item: (-item["lift"], -item["support"], item["pair"]))[:12]


def summarize_feature_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    included = [row for row in rows if row.get("included_in_runtime_scope")]
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in included:
        by_category[str(row["category"])].append(row)

    categories: dict[str, Any] = {}
    for category, config in YAML_CATEGORY_CONFIG.items():
        class_rows = by_category.get(category, [])
        count = len(class_rows)
        complexity = round(_feature_complexity(class_rows), 4)
        top_motifs = _motifs(class_rows, count)
        policy = _confidence_policy(config, class_rows, complexity, len(top_motifs))
        categories[category] = {
            "count": count,
            "kinds": config["kinds"],
            "min_hypotheses": policy["min_hypotheses"],
            "max_hypotheses": policy["max_hypotheses"],
            "tau": policy["tau"],
            "coverage_target": policy["coverage_target"],
            "feature_complexity": complexity,
            "confidence_policy": policy,
            "feature_entropy": {
                field: round(_entropy([str(row.get(field, "unknown")) for row in class_rows]), 4)
                for field in [
                    "action_or_target",
                    "mode",
                    "selector_shape",
                    "duration_bucket",
                    "intensity_bucket",
                ]
            },
            "top_motifs": top_motifs,
            "pairwise_lift": _pairwise_lift(class_rows),
        }

    return {
        "total_yaml": len(rows),
        "included_runtime_scope": len(included),
        "excluded_from_runtime_scope": len(rows) - len(included),
        "categories": categories,
        "low_frequency_kinds": dict(
            sorted(
                Counter(str(row.get("kind") or "unknown") for row in rows if not row.get("included_in_runtime_scope")).items()
            )
        ),
    }


def write_inventory_outputs(raw_yaml_root: Path, output_dir: Path) -> dict[str, Any]:
    rows = load_yaml_feature_rows(raw_yaml_root)
    summary = summarize_feature_rows(rows)
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "yaml_inventory.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "category_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "feature_distribution.json").write_text(
        json.dumps(summary["categories"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    motifs = {
        category: data["top_motifs"]
        for category, data in summary["categories"].items()
    }
    (output_dir / "feature_motifs.json").write_text(
        json.dumps(motifs, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary
