"""Generate method-neutral candidate plans for the comparison pilot."""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path
from typing import Any


REQUIRED_PLAN_FIELDS = {
    "plan_id",
    "method",
    "project_id",
    "replicate",
    "rank",
    "workload_id",
    "target",
    "fault",
    "trigger",
    "predicted_invariant",
    "predicted_root_cause",
    "information_tier",
    "evidence_refs",
    "generation_time_ms",
    "model_tokens",
    "execution",
}


BANK: list[dict[str, Any]] = [
    {
        "candidate_id": "TT-K1-STATION-DELAY",
        "project_id": "train-ticket",
        "workload_id": "station-lookup",
        "service": "ts-station-service",
        "edge": "client->station",
        "fault_family": "latency",
        "intensity": "100ms",
        "duration": "20s",
        "mutation": "artifacts/train-ticket/runtime/generated_mutations/network-station/station-network-delay-candidate-r1.yaml",
        "preclassified": None,
        "graph_score": 70,
        "ours_score": 96,
        "predicted_invariant": "station lookup preserves its response contract within the client deadline",
        "predicted_root_cause": "unbounded latency propagation to the station endpoint",
        "information_tier": ["I0", "I1-local", "I2"],
    },
    {
        "candidate_id": "TT-K1-STATION-DELAY-DUPLICATE",
        "project_id": "train-ticket",
        "workload_id": "station-lookup",
        "service": "ts-station-service",
        "edge": "client->station",
        "fault_family": "latency",
        "intensity": "500ms",
        "duration": "20s",
        "mutation": "artifacts/train-ticket/runtime/generated_mutations/network-station/station-network-delay-candidate-r2.yaml",
        "preclassified": "duplicate_known_mechanism",
        "graph_score": 69,
        "ours_score": 12,
        "predicted_invariant": "station lookup remains within the registered deadline",
        "predicted_root_cause": "same station latency mechanism as the 100ms candidate",
        "information_tier": ["I0", "I1-local", "I2", "I3"],
    },
    {
        "candidate_id": "TT-BASIC-DELAY",
        "project_id": "train-ticket",
        "workload_id": "basic-to-station",
        "service": "ts-basic-service",
        "edge": "basic->station",
        "fault_family": "latency",
        "intensity": "100ms",
        "duration": "20s",
        "mutation": "artifacts/train-ticket/runtime/generated_mutations/network/basic-network-delay-candidate-r1.yaml",
        "preclassified": None,
        "graph_score": 82,
        "ours_score": 90,
        "predicted_invariant": "basic query remains successful within the client deadline",
        "predicted_root_cause": "downstream latency propagates without a bounded fallback",
        "information_tier": ["I0", "I1-local", "I2"],
    },
    {
        "candidate_id": "TT-STATION-CPU",
        "project_id": "train-ticket",
        "workload_id": "station-lookup",
        "service": "ts-station-service",
        "edge": "station-process",
        "fault_family": "cpu_stress",
        "intensity": "1-worker-80pct",
        "duration": "45s",
        "mutation": "artifacts/train-ticket/runtime/generated_mutations/stress-station/station-stress-cpu-candidate-r1.yaml",
        "preclassified": None,
        "graph_score": 65,
        "ours_score": 62,
        "predicted_invariant": "station lookup remains available under bounded CPU contention",
        "predicted_root_cause": "single replica saturation increases tail latency",
        "information_tier": ["I0", "I1-local", "I2"],
    },
    {
        "candidate_id": "TT-K2-ORDER-UNREACHABLE",
        "project_id": "train-ticket",
        "workload_id": "order-refresh",
        "service": "ts-order-service",
        "edge": "order->station",
        "fault_family": "latency",
        "intensity": "500ms",
        "duration": "20s",
        "mutation": None,
        "preclassified": "invalid_unreachable",
        "graph_score": 93,
        "ours_score": 1,
        "predicted_invariant": "order refresh calls station lookup",
        "predicted_root_cause": "station dependency latency",
        "information_tier": ["I0", "I1-local"],
    },
    {
        "candidate_id": "TT-K3-HTTP-PLATFORM",
        "project_id": "train-ticket",
        "workload_id": "order-query",
        "service": "ts-order-service",
        "edge": "client->order",
        "fault_family": "http_error",
        "intensity": "404",
        "duration": "60s",
        "mutation": "artifacts/train-ticket/runtime/injections/order-http-code-nonexistent.yaml",
        "preclassified": None,
        "graph_score": 88,
        "ours_score": 2,
        "predicted_invariant": "order query rejects an injected response error cleanly",
        "predicted_root_cause": "missing API error handling",
        "information_tier": ["I0", "I1-local", "I2"],
    },
    {
        "candidate_id": "OB-K4-PAYMENT-DELAY",
        "project_id": "online-boutique",
        "workload_id": "place-order",
        "service": "paymentservice",
        "edge": "checkout->payment",
        "fault_family": "latency",
        "intensity": "2000ms",
        "duration": "15s",
        "mutation": "artifacts/experiments/execution/mutations/ob-payment-delay-one.yaml",
        "preclassified": None,
        "graph_score": 96,
        "ours_score": 98,
        "predicted_invariant": "place order completes within the registered deadline",
        "predicted_root_cause": "checkout has no bounded payment timeout",
        "information_tier": ["I0", "I1-local", "I2"],
    },
    {
        "candidate_id": "OB-K4-PAYMENT-LOSS",
        "project_id": "online-boutique",
        "workload_id": "place-order",
        "service": "paymentservice",
        "edge": "checkout->payment",
        "fault_family": "unavailable",
        "intensity": "100pct-loss",
        "duration": "15s",
        "mutation": "artifacts/experiments/execution/mutations/ob-payment-loss-one.yaml",
        "preclassified": None,
        "graph_score": 95,
        "ours_score": 97,
        "predicted_invariant": "place order fails within a bounded deadline",
        "predicted_root_cause": "missing payment timeout propagates a hang",
        "information_tier": ["I0", "I1-local", "I2"],
    },
    {
        "candidate_id": "OB-K5-PRODUCTCATALOG-KILL",
        "project_id": "online-boutique",
        "workload_id": "frontend-home",
        "service": "productcatalogservice",
        "edge": "frontend->productcatalog",
        "fault_family": "pod_kill",
        "intensity": "one-pod",
        "duration": "30s",
        "mutation": "artifacts/experiments/execution/mutations/ob-productcatalog-kill-one.yaml",
        "preclassified": None,
        "graph_score": 99,
        "ours_score": 94,
        "predicted_invariant": "frontend remains available when one catalog pod is replaced",
        "predicted_root_cause": "single replica core dependency causes cascading failure",
        "information_tier": ["I0", "I1-local", "I2"],
    },
    {
        "candidate_id": "OB-PRODUCTCATALOG-DELAY",
        "project_id": "online-boutique",
        "workload_id": "frontend-home",
        "service": "productcatalogservice",
        "edge": "frontend->productcatalog",
        "fault_family": "latency",
        "intensity": "500ms",
        "duration": "15s",
        "mutation": "artifacts/experiments/execution/mutations/ob-productcatalog-delay-one.yaml",
        "preclassified": None,
        "graph_score": 98,
        "ours_score": 75,
        "predicted_invariant": "frontend latency stays within its registered deadline",
        "predicted_root_cause": "catalog latency propagates to the frontend",
        "information_tier": ["I0", "I1-local", "I2"],
    },
    {
        "candidate_id": "OB-K6-ADSERVICE-NEGATIVE",
        "project_id": "online-boutique",
        "workload_id": "frontend-home",
        "service": "adservice",
        "edge": "frontend->adservice",
        "fault_family": "unavailable",
        "intensity": "service-absent",
        "duration": "baseline-window",
        "mutation": None,
        "preclassified": "negative_control_observation",
        "graph_score": 35,
        "ours_score": 40,
        "predicted_invariant": "frontend remains available without advertisements",
        "predicted_root_cause": "non-core dependency is guarded by timeout and error swallowing",
        "information_tier": ["I0", "I1-local", "I2"],
    },
    {
        "candidate_id": "OB-K7-PROBE-RESTART",
        "project_id": "online-boutique",
        "workload_id": "place-order",
        "service": "paymentservice",
        "edge": "probe->payment",
        "fault_family": "latency",
        "intensity": "2000ms",
        "duration": "150s",
        "mutation": "artifacts/experiments/execution/mutations/ob-payment-probe-escape-one.yaml",
        "preclassified": "control_already_executed",
        "graph_score": 55,
        "ours_score": 99,
        "predicted_invariant": "probe restart does not amplify or escape the injected fault",
        "predicted_root_cause": "probe deadline is shorter than injected service latency",
        "information_tier": ["I0", "I1-local", "I2", "I3"],
    },
]


METHODS = [
    {"id": "M0", "name": "random-template", "status": "available"},
    {
        "id": "M1",
        "name": "ChaosEater-adapter",
        "status": "blocked_external_reproduction",
        "blocker": "official repository download unavailable in the current host network",
        "source": "https://github.com/ntt-dkiku/chaos-eater",
    },
    {
        "id": "M2",
        "name": "FastFI-adapter",
        "status": "blocked_external_reproduction",
        "blocker": "official repository download unavailable in the current host network",
        "source": "https://github.com/TanYuzhen/TOSEM-FastFI-Code",
    },
    {"id": "M3", "name": "graph-only", "status": "available"},
    {"id": "M4", "name": "ours-full", "status": "available"},
]


def validate_plan(plan: dict[str, Any]) -> list[str]:
    errors = [f"missing field: {field}" for field in sorted(REQUIRED_PLAN_FIELDS - plan.keys())]
    if plan.get("fault", {}).get("mode") != "one" and plan.get("execution", {}).get("mutation_path"):
        errors.append("executable mutations must use mode one")
    if not isinstance(plan.get("rank"), int) or int(plan.get("rank", 0)) < 1:
        errors.append("rank must be a positive integer")
    return errors


def ordered_candidates(method_id: str, project_id: str, seed: int) -> list[dict[str, Any]]:
    candidates = [item for item in BANK if item["project_id"] == project_id]
    if method_id == "M0":
        result = candidates[:]
        random.Random(seed).shuffle(result)
        return result
    score = "graph_score" if method_id == "M3" else "ours_score"
    return sorted(candidates, key=lambda item: (-item[score], item["candidate_id"]))


def make_plan(
    method: dict[str, Any],
    candidate: dict[str, Any],
    replicate: int,
    rank: int,
    generation_ms: int,
) -> dict[str, Any]:
    plan = {
        "plan_id": f"{method['id']}-{candidate['project_id']}-r{replicate}-{rank:02d}",
        "method": method["name"],
        "project_id": candidate["project_id"],
        "replicate": replicate,
        "rank": rank,
        "workload_id": candidate["workload_id"],
        "target": {
            "service": candidate["service"],
            "endpoint_or_edge": candidate["edge"],
            "direction": "to",
        },
        "fault": {
            "family": candidate["fault_family"],
            "intensity": candidate["intensity"],
            "duration": candidate["duration"],
            "mode": "one",
        },
        "trigger": "during_workload",
        "predicted_invariant": candidate["predicted_invariant"],
        "predicted_root_cause": candidate["predicted_root_cause"],
        "information_tier": (
            ["I0"] if method["id"] == "M0" else
            ["I0", "I1-global"] if method["id"] == "M3" else
            candidate["information_tier"]
        ),
        "evidence_refs": [],
        "generation_time_ms": generation_ms,
        "model_tokens": 0,
        "execution": {
            "candidate_id": candidate["candidate_id"],
            "mutation_path": candidate["mutation"],
            "preclassified": candidate["preclassified"],
        },
    }
    errors = validate_plan(plan)
    if errors:
        raise ValueError(f"invalid generated plan {plan['plan_id']}: {errors}")
    return plan


def generate(replicate: int, seed: int, limit: int) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": 1,
        "tool": "generate_comparison_pilot",
        "replicate": replicate,
        "seed": seed,
        "candidate_budget_per_project": limit,
        "methods": [],
    }
    for method in METHODS:
        method_result = dict(method)
        method_result["plans"] = []
        if method["status"] == "available":
            started = time.perf_counter()
            for project in ("train-ticket", "online-boutique"):
                ordered = ordered_candidates(method["id"], project, seed)
                for rank, candidate in enumerate(ordered[:limit], 1):
                    elapsed_ms = int((time.perf_counter() - started) * 1000)
                    method_result["plans"].append(
                        make_plan(method, candidate, replicate, rank, elapsed_ms)
                    )
        result["methods"].append(method_result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replicate", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--limit", type=int, default=6)
    args = parser.parse_args()
    result = generate(args.replicate, args.seed, args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "methods": len(result["methods"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
