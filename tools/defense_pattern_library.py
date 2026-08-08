"""Defense-pattern library: extract, store, and query defense mechanisms.

The second knowledge asset of the dual-track methodology (see
artifacts/experiments/defense_pattern_methodology.md): when an injection is
defended, we record WHY (the mechanism) so that future projects can DOWNGRADE
candidates on edges with the same mechanism — saving injection budget.

A pattern is a (defense_mechanism, evidence) pair. Downranking is a prior:
if static/behavior evidence in the new project suggests the mechanism may be
missing, the downgrade is overridden (patterns are priors, behavior can
override them).
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LIBRARY_PATH = ROOT / "artifacts" / "experiments" / "defense_pattern_library.json"

MECHANISMS = {
    "bounded_timeout": "downstream call has an explicit timeout with degradation after it",
    "retry_fast_fail": "fast fail + bounded retry, no hang",
    "circuit_breaker": "circuit breaker isolates a failing dependency",
    "redundancy": "multiple replicas / redundancy absorb single-point failure",
    "isolation_non_critical": "non-critical side effect decoupled from the primary path (async/independent budget)",
    "absorbed_by_design": "single-call path propagates latency 1:1 with no compounding (structure is simple, nothing amplifies)",
    "weak_stressor": "injection intensity below the trigger threshold (e.g. 1 worker 80% CPU does not saturate)",
}

# v1 seed patterns extracted from executed experiments.
SEED_PATTERNS: list[dict[str, Any]] = [
    {
        "pattern_id": "DP-DEFENSE-ABSORBED-001",
        "defense_mechanism": "absorbed_by_design",
        "evidence": {
            "project": "train-ticket",
            "candidate_id": "TT-BASIC-DELAY-500",
            "mutation": "artifacts/experiments/execution/mutations_extended/tt-basic-delay-500-one.yaml",
            "observation": "500ms injection -> 517-535ms response (1:1, no amplification), 5/5 HTTP 200 x3",
            "evidence_files": [
                "m1_ext_tt_basic_delay_500_r1.json",
                "m1_ext_tt_basic_delay_500_r2.json",
                "m1_ext_tt_basic_delay_500_r3.json",
            ],
        },
        "inference": "basic->station is a single downstream call; latency propagates 1:1 with no fan-out compounding",
    },
    {
        "pattern_id": "DP-DEFENSE-ABSORBED-002",
        "defense_mechanism": "absorbed_by_design",
        "evidence": {
            "project": "train-ticket",
            "candidate_id": "TT-BASIC-DELAY-100",
            "mutation": "artifacts/train-ticket/runtime/generated_mutations/network/basic-network-delay-candidate-r1.yaml",
            "observation": "100ms injection -> 141ms response, 5/5 HTTP 200",
            "evidence_files": ["m1_batch_tt_basic_delay_100_r1.json"],
        },
        "inference": "weak latency injection on a single-call path; no amplification",
    },
    {
        "pattern_id": "DP-DEFENSE-WEAK-001",
        "defense_mechanism": "weak_stressor",
        "evidence": {
            "project": "train-ticket",
            "candidate_id": "TT-STATION-DELAY-100",
            "mutation": "artifacts/train-ticket/runtime/generated_mutations/network-station/station-network-delay-candidate-r1.yaml",
            "observation": "100ms injection -> ~124ms response (near injection, no compounding), 5/5 HTTP 200 x4",
            "evidence_files": [
                "confirmation_tt_station_r2.json",
                "confirmation_tt_station_r3.json",
                "confirmation_tt_station_r4.json",
                "smoke_station_r1.json",
            ],
        },
        "inference": "100ms on station boundary is below any trigger threshold; response tracks injection 1:1",
    },
    {
        "pattern_id": "DP-DEFENSE-WEAK-002",
        "defense_mechanism": "weak_stressor",
        "evidence": {
            "project": "train-ticket",
            "candidate_id": "TT-STATION-CPU-80",
            "mutation": "artifacts/train-ticket/runtime/generated_mutations/stress-station/station-stress-cpu-candidate-r1.yaml",
            "observation": "1 worker 80% CPU -> 39-100ms responses (near baseline), 5/5 HTTP 200 x3",
            "evidence_files": [
                "m1_batch_tt_station_cpu_80_r1.json",
                "m1_batch_tt_station_cpu_80_r2.json",
                "m1_batch_tt_station_cpu_80_r3.json",
            ],
        },
        "inference": "single-worker 80% does not saturate a multi-core pod; CPU stress below trigger threshold",
    },
]

# Static edge fingerprint -> mechanism family for downgrade matching.
# For v1 these are hand-curated from the pattern evidence; they document the
# intended migration, not a claim that every edge of this kind is defended.
EDGE_TO_MECHANISM: dict[str, str] = {
    "basic->station": "absorbed_by_design",
    "client->station": "weak_stressor",  # low-intensity boundary only
}


def load_library(path: Path = LIBRARY_PATH) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"schema_version": 1, "patterns": []}


def save_library(library: dict[str, Any], path: Path = LIBRARY_PATH) -> None:
    path.write_text(json.dumps(library, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def seed(path: Path = LIBRARY_PATH) -> dict[str, Any]:
    library = load_library(path)
    existing = {p["pattern_id"] for p in library.get("patterns", [])}
    for pattern in SEED_PATTERNS:
        if pattern["pattern_id"] not in existing:
            library.setdefault("patterns", []).append(pattern)
    library.setdefault("generated_at", datetime.now(timezone.utc).isoformat())
    save_library(library, path)
    return library


def query_downgrade(
    candidate: dict[str, Any],
    library: dict[str, Any] | None = None,
    execution_verdict: str | None = None,
    execution_severity: int | None = None,
) -> dict[str, Any]:
    """Return a downgrade recommendation for a candidate based on its edge.

    Match rule (v1): the candidate's 'edge' string is looked up in
    EDGE_TO_MECHANISM. A match yields a prior downgrade, but execution
    evidence overrides the prior: if the candidate was already executed and
    showed a weakness (severity >= 2), the downgrade is REVOKED. Patterns are
    priors; behavior (execution) evidence wins.
    """
    library = library or load_library()
    edge = str(candidate.get("edge", ""))
    mechanism = EDGE_TO_MECHANISM.get(edge)
    if not mechanism:
        return {
            "candidate_id": candidate.get("candidate_id"),
            "edge": edge,
            "downgrade": False,
            "reason": "no defense pattern for this edge fingerprint",
            "matching_patterns": [],
        }
    patterns = [
        p for p in library.get("patterns", [])
        if p.get("defense_mechanism") == mechanism
    ]
    # Execution evidence overrides the pattern prior.
    if execution_severity is not None and execution_severity >= 2:
        return {
            "candidate_id": candidate.get("candidate_id"),
            "edge": edge,
            "downgrade": False,
            "mechanism": mechanism,
            "reason": (
                f"pattern {mechanism} applies but execution evidence shows a weakness "
                f"(severity {execution_severity}, verdict {execution_verdict}); behavior overrides prior"
            ),
            "matching_patterns": [p["pattern_id"] for p in patterns],
            "execution_override": True,
        }
    return {
        "candidate_id": candidate.get("candidate_id"),
        "edge": edge,
        "downgrade": True,
        "mechanism": mechanism,
        "candidate_priority": "low",
        "skip_recommended": True,
        "reason": f"defense pattern {mechanism} verified on a same-fingerprint edge",
        "matching_patterns": [p["pattern_id"] for p in patterns],
        "override_note": "pattern is a prior; static/behavior evidence that the mechanism is missing overrides this downgrade",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", action="store_true", help="seed the library with v1 patterns")
    parser.add_argument("--query", type=str, help="edge fingerprint to query (e.g. basic->station)")
    parser.add_argument("--library", type=Path, default=LIBRARY_PATH)
    args = parser.parse_args()

    if args.seed:
        library = seed(args.library)
        print(json.dumps({"seeded": len(library.get("patterns", [])), "path": str(args.library)}, indent=2))
        return 0

    if args.query:
        library = load_library(args.library)
        candidate = {"candidate_id": "QUERY", "edge": args.query}
        print(json.dumps(query_downgrade(candidate, library), indent=2, ensure_ascii=True))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
