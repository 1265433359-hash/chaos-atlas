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
    "weak_stressor": "INVALID (A1 audit): injection below threshold is a measurement blind spot, not a defense mechanism — retained only for backfill de-duplication",
}

# v1 seed patterns extracted from executed experiments.
# A1 audit fix: weak_stressor entries removed (below-threshold is not a
# defense mechanism); absorbed_by_design entries marked source_verified:false
# (observation-inferred, source not yet confirmed).
SEED_PATTERNS: list[dict[str, Any]] = [
    {
        "pattern_id": "DP-DEFENSE-ABSORBED-001",
        "defense_mechanism": "absorbed_by_design",
        "source_verified": False,
        "source_note": "observation-inferred (1:1 no amplification); requires source/config confirmation",
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
        "source_verified": False,
        "source_note": "observation-inferred (1:1 no amplification); requires source/config confirmation",
        "evidence": {
            "project": "train-ticket",
            "candidate_id": "TT-BASIC-DELAY-100",
            "mutation": "artifacts/train-ticket/runtime/generated_mutations/network/basic-network-delay-candidate-r1.yaml",
            "observation": "100ms injection -> 141ms response, 5/5 HTTP 200",
            "evidence_files": ["m1_batch_tt_basic_delay_100_r1.json"],
        },
        "inference": "weak latency injection on a single-call path; no amplification",
    },
]

# Static edge fingerprint -> mechanism family for downgrade matching.
# A1 audit fix: weak_stressor mapping removed (below-threshold must never
# downgrade); only absorbed_by_design remains and it is an unverified prior.
# C2: this map is now DERIVED from the seed patterns' evidence edges instead
# of hand-curated; the contract inventory is the lookup table for candidate->edge.
EDGE_TO_MECHANISM: dict[str, str] = {
    "basic->station": "absorbed_by_design",
}


def build_edge_index(library: dict[str, Any] | None = None) -> dict[str, str]:
    """C2: derive edge fingerprint -> mechanism from pattern evidence.

    Each pattern's evidence carries candidate_id; the candidate's edge string
    (from extended_candidate_pool) becomes the fingerprint. This replaces
    hand-curation for patterns that carry a resolvable candidate.
    """
    library = library or load_library()
    from extended_candidate_pool import extended_candidate_pool

    edge_by_candidate = {c["candidate_id"]: c.get("edge", "") for c in extended_candidate_pool()}
    index: dict[str, str] = {}
    for pattern in library.get("patterns", []):
        candidate_id = (pattern.get("evidence") or {}).get("candidate_id")
        if not candidate_id:
            continue
        edge = edge_by_candidate.get(candidate_id)
        if not edge:
            continue
        # Do not let a pattern claim a mechanism for an edge it did not verify.
        if pattern.get("source_verified"):
            index.setdefault(edge, pattern["defense_mechanism"])
    # Merge hand-curated priors last (explicit, auditable overrides).
    index.update(EDGE_TO_MECHANISM)
    return index


def load_library(path: Path = LIBRARY_PATH) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"schema_version": 1, "patterns": []}


def save_library(library: dict[str, Any], path: Path = LIBRARY_PATH) -> None:
    path.write_text(json.dumps(library, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def seed(path: Path = LIBRARY_PATH) -> dict[str, Any]:
    """Idempotent seed; also applies the A1 audit migration to an existing library:
    removes weak_stressor patterns and stamps source_verified on absorbed ones."""
    library = load_library(path)
    existing = {p["pattern_id"] for p in library.get("patterns", [])}
    # A1 migration: drop weak_stressor (measurement blind spot, not a defense).
    before = len(library.get("patterns", []))
    library["patterns"] = [
        p for p in library.get("patterns", [])
        if p.get("defense_mechanism") != "weak_stressor"
    ]
    dropped = before - len(library["patterns"])
    # Stamp source_verified on absorbed_by_design entries if absent.
    for pattern in library["patterns"]:
        if pattern.get("defense_mechanism") == "absorbed_by_design" and "source_verified" not in pattern:
            pattern["source_verified"] = False
            pattern["source_note"] = "observation-inferred; requires source/config confirmation"
    for pattern in SEED_PATTERNS:
        if pattern["pattern_id"] not in existing:
            library.setdefault("patterns", []).append(pattern)
    library.setdefault("generated_at", datetime.now(timezone.utc).isoformat())
    library["a1_audit"] = {"weak_stressor_dropped": dropped, "applied_at": datetime.now(timezone.utc).isoformat()}
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
    edge_index = build_edge_index(library)
    mechanism = edge_index.get(edge)
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
