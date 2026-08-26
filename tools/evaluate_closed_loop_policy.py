"""Offline replay evaluator for policy decisions and deterministic outcomes."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def evaluate_replay(
    denominator: dict[str, Any],
    decisions: Iterable[dict[str, Any]],
    runtime_results: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    candidates = {str(item.get("candidate_id")): item for item in denominator.get("candidates", []) if isinstance(item, dict)}
    decisions_list = list(decisions)
    runtime_list = list(runtime_results)
    selected: list[str] = []
    stop_reasons: Counter[str] = Counter()
    for decision in decisions_list:
        ids = [str(item) for item in decision.get("policy_selected_candidate_ids", [])]
        unknown = sorted(set(ids) - set(candidates))
        if unknown:
            raise ValueError(f"selection outside denominator: {unknown}")
        selected.extend(ids)
        if decision.get("stop_reason"):
            stop_reasons[str(decision["stop_reason"])] += 1
    runtime_by_candidate = {str(item.get("candidate_id")): item for item in runtime_list}
    classifications = Counter(str(item.get("classification") or "unsupported") for item in runtime_list)
    clusters = {str(candidates[item].get("causal_cluster_id")) for item in selected if candidates[item].get("causal_cluster_id")}
    report = {
        "schema_version": "chaosatlas-closed-loop-replay-v1",
        "project_id": denominator.get("project_id"),
        "seed": denominator.get("seed"),
        "experiments": len(selected),
        "unique_causal_clusters": len(clusters),
        "confirmed_weakness_yield": classifications.get("confirmed_weakness", 0),
        "protected_waste": classifications.get("protected", 0),
        "method_invalid": classifications.get("method_invalid", 0),
        "environment_blocked": classifications.get("environment_blocked", 0),
        "unresolved_uncertainty": sum(1 for cid in selected if cid not in runtime_by_candidate),
        "boundary_discoveries": sum(1 for item in runtime_list if item.get("boundary_discovered") is True),
        "stop_reasons": dict(sorted(stop_reasons.items())),
    }
    report["replay_sha256"] = hashlib.sha256(_canonical({"denominator": denominator, "decisions": decisions_list, "runtime": runtime_list}).encode()).hexdigest()
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--denominator", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    denominator = json.loads(args.denominator.read_text(encoding="utf-8"))
    decisions = [json.loads(line) for line in args.decisions.read_text(encoding="utf-8").splitlines() if line.strip()]
    runtime = json.loads(args.runtime.read_text(encoding="utf-8"))
    if isinstance(runtime, dict):
        runtime = runtime.get("results", runtime.get("records", []))
    report = evaluate_replay(denominator, decisions, runtime)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"experiments": report["experiments"], "unique_causal_clusters": report["unique_causal_clusters"]}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

