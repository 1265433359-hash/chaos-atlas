"""Generate a fixed cross-project candidate matrix for fair comparison and ablation."""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = {
    "plan_id", "method", "project_id", "replicate", "rank", "workload_id",
    "target", "fault", "trigger", "predicted_invariant", "predicted_root_cause",
    "information_tier", "evidence_refs", "generation_time_ms", "model_tokens", "execution",
}


CORE_CANDIDATES: list[dict[str, Any]] = [
    {
        "candidate_id": "TT-STATION-DELAY-100",
        "project_id": "train-ticket",
        "workload_id": "station-lookup",
        "service": "ts-station-service",
        "edge": "client->station",
        "fault_family": "latency",
        "intensity": "100ms",
        "duration": "20s",
        "mutation": "artifacts/train-ticket/runtime/generated_mutations/network-station/station-network-delay-candidate-r1.yaml",
        "preclassified": None,
        "scores": {"graph": 76, "local": 94, "yaml": 48},
        "invariant": "station lookup preserves its response contract and registered deadline",
        "root_cause": "unbounded latency propagation to the station endpoint",
    },
    {
        "candidate_id": "TT-STATION-DELAY-2000",
        "project_id": "train-ticket",
        "workload_id": "station-lookup",
        "service": "ts-station-service",
        "edge": "client->station",
        "fault_family": "latency",
        "intensity": "2000ms",
        "duration": "60s",
        "mutation": "artifacts/train-ticket/runtime/generated_mutations/network-station/station-network-delay-candidate-r3.yaml",
        "preclassified": None,
        "scores": {"graph": 78, "local": 98, "yaml": 50},
        "invariant": "station lookup does not exceed the client deadline under boundary delay",
        "root_cause": "missing bounded timeout or fallback at the station boundary",
    },
    {
        "candidate_id": "TT-STATION-CPU-80",
        "project_id": "train-ticket",
        "workload_id": "station-lookup",
        "service": "ts-station-service",
        "edge": "station-process",
        "fault_family": "cpu_stress",
        "intensity": "1-worker-80pct",
        "duration": "45s",
        "mutation": "artifacts/train-ticket/runtime/generated_mutations/stress-station/station-stress-cpu-candidate-r1.yaml",
        "preclassified": None,
        "scores": {"graph": 60, "local": 76, "yaml": 55},
        "invariant": "station lookup remains available under bounded CPU contention",
        "root_cause": "single replica saturation increases tail latency",
    },
    {
        "candidate_id": "TT-BASIC-DELAY-100",
        "project_id": "train-ticket",
        "workload_id": "basic-to-station",
        "service": "ts-basic-service",
        "edge": "basic->station",
        "fault_family": "latency",
        "intensity": "100ms",
        "duration": "20s",
        "mutation": "artifacts/train-ticket/runtime/generated_mutations/network/basic-network-delay-candidate-r1.yaml",
        "preclassified": None,
        "scores": {"graph": 82, "local": 88, "yaml": 52},
        "invariant": "basic query remains successful within the client deadline",
        "root_cause": "downstream latency propagates without a bounded fallback",
    },
    {
        "candidate_id": "OB-PAYMENT-DELAY-2000",
        "project_id": "online-boutique",
        "workload_id": "place-order",
        "service": "paymentservice",
        "edge": "checkout->payment",
        "fault_family": "latency",
        "intensity": "2000ms",
        "duration": "15s",
        "mutation": "artifacts/experiments/execution/mutations/ob-payment-delay-one.yaml",
        "preclassified": None,
        "scores": {"graph": 94, "local": 98, "yaml": 62},
        "invariant": "place order completes within the registered deadline",
        "root_cause": "checkout has no bounded payment timeout",
    },
    {
        "candidate_id": "OB-PAYMENT-LOSS-100",
        "project_id": "online-boutique",
        "workload_id": "place-order",
        "service": "paymentservice",
        "edge": "checkout->payment",
        "fault_family": "unavailable",
        "intensity": "100pct-loss",
        "duration": "15s",
        "mutation": "artifacts/experiments/execution/mutations/ob-payment-loss-one.yaml",
        "preclassified": None,
        "scores": {"graph": 93, "local": 97, "yaml": 64},
        "invariant": "place order fails within a bounded deadline",
        "root_cause": "missing payment timeout propagates a hang",
    },
    {
        "candidate_id": "OB-PRODUCTCATALOG-KILL",
        "project_id": "online-boutique",
        "workload_id": "frontend-home",
        "service": "productcatalogservice",
        "edge": "frontend->productcatalog",
        "fault_family": "pod_kill",
        "intensity": "one-pod",
        "duration": "30s",
        "mutation": "artifacts/experiments/execution/mutations/ob-productcatalog-kill-one.yaml",
        "preclassified": None,
        "scores": {"graph": 96, "local": 92, "yaml": 70},
        "invariant": "frontend remains available when one catalog pod is replaced",
        "root_cause": "single replica core dependency causes cascading failure",
    },
    {
        "candidate_id": "OB-PRODUCTCATALOG-DELAY-500",
        "project_id": "online-boutique",
        "workload_id": "frontend-home",
        "service": "productcatalogservice",
        "edge": "frontend->productcatalog",
        "fault_family": "latency",
        "intensity": "500ms",
        "duration": "15s",
        "mutation": "artifacts/experiments/execution/mutations/ob-productcatalog-delay-one.yaml",
        "preclassified": None,
        "scores": {"graph": 92, "local": 84, "yaml": 58},
        "invariant": "frontend latency stays within its registered deadline",
        "root_cause": "catalog latency propagates to the frontend",
    },
    {
        "candidate_id": "OTEL-PAYMENT-DELAY-2000",
        "project_id": "otel-demo",
        "workload_id": "place-order",
        "service": "payment",
        "edge": "checkout->payment",
        "fault_family": "latency",
        "intensity": "2000ms",
        "duration": "15s",
        "mutation": "artifacts/experiments/execution/mutations/otel-payment-delay-one.yaml",
        "preclassified": None,
        "scores": {"graph": 91, "local": 97, "yaml": 60},
        "invariant": "OTel checkout remains within its payment deadline",
        "root_cause": "payment latency propagates through the checkout workflow",
    },
    {
        "candidate_id": "OTEL-PAYMENT-LOSS-100",
        "project_id": "otel-demo",
        "workload_id": "place-order",
        "service": "payment",
        "edge": "checkout->payment",
        "fault_family": "unavailable",
        "intensity": "100pct-loss",
        "duration": "15s",
        "mutation": "artifacts/experiments/execution/mutations/otel-payment-loss-one.yaml",
        "preclassified": None,
        "scores": {"graph": 90, "local": 96, "yaml": 61},
        "invariant": "OTel checkout reports payment failure within a bounded deadline",
        "root_cause": "missing bounded error handling at the payment edge",
    },
    {
        "candidate_id": "OTEL-EMAIL-DELAY-2000",
        "project_id": "otel-demo",
        "workload_id": "place-order",
        "service": "email",
        "edge": "checkout->email",
        "fault_family": "latency",
        "intensity": "2000ms",
        "duration": "15s",
        "mutation": "artifacts/experiments/execution/mutations/otel-email-delay-one.yaml",
        "preclassified": None,
        "scores": {"graph": 72, "local": 86, "yaml": 57},
        "invariant": "email side effect remains bounded without blocking checkout indefinitely",
        "root_cause": "non-critical email latency is not isolated from the order path",
    },
    {
        "candidate_id": "OTEL-EMAIL-LOSS-100",
        "project_id": "otel-demo",
        "workload_id": "place-order",
        "service": "email",
        "edge": "checkout->email",
        "fault_family": "unavailable",
        "intensity": "100pct-loss",
        "duration": "15s",
        "mutation": "artifacts/experiments/execution/mutations/otel-email-loss-one.yaml",
        "preclassified": None,
        "scores": {"graph": 70, "local": 84, "yaml": 59},
        "invariant": "email unavailability does not corrupt the primary order result",
        "root_cause": "missing isolation or fallback for a non-critical side effect",
    },
]


METHODS: list[dict[str, Any]] = [
    {"id": "M0", "name": "random-template", "status": "available", "information_tier": ["I0"], "score": "yaml"},
    {"id": "M1", "name": "ChaosEater-adapter", "status": "blocked_external_reproduction", "information_tier": ["I0"], "blocker": "official repository unavailable in current host network"},
    {"id": "M2", "name": "FastFI-adapter", "status": "blocked_external_reproduction", "information_tier": ["I0", "I2"], "blocker": "official repository unavailable in current host network"},
    {"id": "M3", "name": "graph-only", "status": "available", "information_tier": ["I0", "I1-global"], "score": "graph"},
    {"id": "M4", "name": "ours-full", "status": "available", "information_tier": ["I0", "I1-local", "I2"], "score": "local"},
    {"id": "A0", "name": "ours-yaml-only", "status": "available", "information_tier": ["I0"], "score": "yaml"},
    {"id": "A1", "name": "ours-global-graph", "status": "available", "information_tier": ["I0", "I1-global"], "score": "graph"},
    {"id": "A2", "name": "ours-local-graph", "status": "available", "information_tier": ["I0", "I1-local"], "score": "local"},
    {"id": "A3", "name": "ours-local-graph-runtime-gate", "status": "available", "information_tier": ["I0", "I1-local", "I2"], "score": "local", "runtime_gate": True},
    {"id": "A4", "name": "ours-full-evidence-feedback", "status": "available", "information_tier": ["I0", "I1-local", "I2", "I3"], "score": "local", "runtime_gate": True, "evidence_feedback": True},
]


def validate_plan(plan: dict[str, Any]) -> list[str]:
    errors = [f"missing field: {field}" for field in sorted(REQUIRED_FIELDS - plan.keys())]
    execution = plan.get("execution") or {}
    if execution.get("mutation_path") and plan.get("fault", {}).get("mode") != "one":
        errors.append("executable mutations must use mode one")
    if not isinstance(plan.get("rank"), int) or plan.get("rank", 0) < 1:
        errors.append("rank must be a positive integer")
    if plan.get("project_id") not in {"train-ticket", "online-boutique", "otel-demo"}:
        errors.append("unknown project")
    return errors


def make_plan(method: dict[str, Any], candidate: dict[str, Any], replicate: int, rank: int, elapsed_ms: int) -> dict[str, Any]:
    plan = {
        "plan_id": f"{method['id']}-{candidate['candidate_id']}-r{replicate}-{rank:02d}",
        "method": method["name"],
        "project_id": candidate["project_id"],
        "replicate": replicate,
        "rank": rank,
        "workload_id": candidate["workload_id"],
        "target": {"service": candidate["service"], "endpoint_or_edge": candidate["edge"], "direction": "to"},
        "fault": {"family": candidate["fault_family"], "intensity": candidate["intensity"], "duration": candidate["duration"], "mode": "one"},
        "trigger": "during_workload",
        "predicted_invariant": candidate["invariant"],
        "predicted_root_cause": candidate["root_cause"],
        "information_tier": method["information_tier"],
        "evidence_refs": [],
        "generation_time_ms": elapsed_ms,
        "model_tokens": 0,
        "execution": {
            "candidate_id": candidate["candidate_id"],
            "mutation_path": candidate["mutation"],
            "preclassified": candidate["preclassified"],
            "runtime_gate_required": bool(method.get("runtime_gate")),
            "evidence_feedback": bool(method.get("evidence_feedback")),
        },
    }
    errors = validate_plan(plan)
    if errors:
        raise ValueError(f"invalid plan {plan['plan_id']}: {errors}")
    return plan


def generate(replicate: int, seed: int, candidate_budget: int) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": 1,
        "tool": "generate_deep_comparison_matrix",
        "replicate": replicate,
        "seed": seed,
        "candidate_budget": candidate_budget,
        "candidate_universe": [item["candidate_id"] for item in CORE_CANDIDATES],
        "same_candidate_pool": True,
        "methods": [],
    }
    for method in METHODS:
        method_result = {key: value for key, value in method.items() if key not in {"score"}}
        method_result["plans"] = []
        if method["status"] == "available":
            candidates = CORE_CANDIDATES[:]
            if method["id"] == "M0":
                random.Random(seed).shuffle(candidates)
            else:
                score_name = method.get("score", "local")
                candidates.sort(key=lambda item: (-item["scores"][score_name], item["candidate_id"]))
            started = time.perf_counter()
            for rank, candidate in enumerate(candidates[:candidate_budget], 1):
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                method_result["plans"].append(make_plan(method, candidate, replicate, rank, elapsed_ms))
        result["methods"].append(method_result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replicate", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--candidate-budget", type=int, default=10)
    args = parser.parse_args()
    if args.candidate_budget < 1 or args.candidate_budget > len(CORE_CANDIDATES):
        raise SystemExit(f"candidate budget must be between 1 and {len(CORE_CANDIDATES)}")
    result = generate(args.replicate, args.seed, args.candidate_budget)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "candidate_count": len(result["candidate_universe"]), "methods": len(result["methods"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
