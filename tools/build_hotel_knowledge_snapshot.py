#!/usr/bin/env python3
"""Build the Hotel Reservation PRE-experiment knowledge snapshot (P2).

Provenance honesty:
  - contract / availability : STATIC-RECONSTRUCTED from canonical Hotel source
    intake (delimitrou/DeathStarBench @ 6ecb0970, hotelReservation/). Edges
    observed from source call graph; connection-level dial timeout 120s is
    explicitly marked connection-level, NOT a per-request contract.
  - SE / DP / JE : generic cross-project rule libraries. They contain evidence
    from OTHER projects (TT/OB/OTEL/Sock) but NO Hotel evidence — relative to
    Hotel they are experiment-pre. Marked pre_experiment_commit.
  - candidate_map : candidate pool is NOT yet constructed (frozen AFTER this
    snapshot per protocol). Left empty with an explicit note.

Compatible with validate_knowledge_snapshot() / snapshot_is_full_experiment_pre().
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / "artifacts" / "experiments"
OUT = ROOT / "artifacts" / "experiments" / "heldout" / "hotel_knowledge_snapshot_pre.json"

HOTEL_COMMIT = "6ecb09706140f8730b5385c08f1386c654c3c526"
HOTEL_URL = "https://github.com/delimitrou/DeathStarBench (hotelReservation/)"

# --- contract: STATIC from Hotel source intake ---
CONTRACTS_STATIC = {
    "HOTEL-frontend->search": {
        "contract": "no_timeout",
        "loss_bounded": False,
        "evidence": "STATIC: frontend server.go initSearchClient('srv-search') gRPC; no per-request timeout on downstream call. dialer/dialer.go Timeout=120s is CONNECTION-level (dial), not per-request.",
        "note": "gRPC edge without explicit per-request deadline; unprotected (delay 1:1, loss hang until client boundary).",
    },
    "HOTEL-frontend->profile": {
        "contract": "no_timeout",
        "loss_bounded": False,
        "evidence": "STATIC: frontend server.go initProfileClient('srv-profile') gRPC; no per-request timeout.",
        "note": "unprotected gRPC edge.",
    },
    "HOTEL-frontend->recommendation": {
        "contract": "no_timeout",
        "loss_bounded": False,
        "evidence": "STATIC: frontend server.go initRecommendationClient('srv-recommendation') gRPC; no per-request timeout.",
        "note": "unprotected gRPC edge.",
    },
    "HOTEL-search->geo": {
        "contract": "no_timeout",
        "loss_bounded": False,
        "evidence": "STATIC: search service uses geo.GeoClient (geo proto); no per-request timeout.",
        "note": "unprotected gRPC edge (search -> geo).",
    },
    "HOTEL-search->rate": {
        "contract": "no_timeout",
        "loss_bounded": False,
        "evidence": "STATIC: search service uses rate.RateClient (rate proto); no per-request timeout.",
        "note": "unprotected gRPC edge (search -> rate).",
    },
}

# --- availability: STATIC from compose (single replica) + kubernetes dir present ---
AVAILABILITY_STATIC = {
    "HOTEL": {
        "FRONTEND": {"replicas": 1, "pdb": None, "hpa": None, "service": "FRONTEND", "static_prediction": "compose single-replica no-PDB -> kill = total outage"},
        "RESERVATION": {"replicas": 1, "pdb": None, "hpa": None, "service": "RESERVATION", "static_prediction": "compose single-replica no-PDB -> kill = total outage"},
        "RATE": {"replicas": 1, "pdb": None, "hpa": None, "service": "RATE", "static_prediction": "compose single-replica no-PDB -> kill = total outage"},
        "PROFILE": {"replicas": 1, "pdb": None, "hpa": None, "service": "PROFILE", "static_prediction": "compose single-replica no-PDB -> kill = total outage"},
        "GEO": {"replicas": 1, "pdb": None, "hpa": None, "service": "GEO", "static_prediction": "compose single-replica no-PDB -> kill = total outage"},
        "SEARCH": {"replicas": 1, "pdb": None, "hpa": None, "service": "SEARCH", "static_prediction": "compose single-replica no-PDB -> kill = total outage"},
        "RECOMMENDATION": {"replicas": 1, "pdb": None, "hpa": None, "service": "RECOMMENDATION", "static_prediction": "compose single-replica no-PDB -> kill = total outage"},
        "REVIEW": {"replicas": 1, "pdb": None, "hpa": None, "service": "REVIEW", "static_prediction": "compose single-replica no-PDB -> kill = total outage"},
        "ATTRACTIONS": {"replicas": 1, "pdb": None, "hpa": None, "service": "ATTRACTIONS", "static_prediction": "compose single-replica no-PDB -> kill = total outage"},
        "USER": {"replicas": 1, "pdb": None, "hpa": None, "service": "USER", "static_prediction": "compose single-replica no-PDB -> kill = total outage"},
    }
}

# candidate_map is intentionally EMPTY: the candidate pool is frozen AFTER this
# snapshot per protocol (anti-contamination pipeline order). Populated in a
# later freeze step, never from results.
CANDIDATE_MAP_STATIC: dict[str, str] = {}


def _load_current(rel: str) -> dict:
    return json.loads((EXPERIMENTS / rel).read_text(encoding="utf-8"))


def _sha256(rel: str) -> str:
    import hashlib

    # rel is relative to repo root, e.g. "artifacts/experiments/selection_experience.json"
    path = ROOT / rel
    if not path.exists():
        return "unavailable"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    # SE/DP/JE: generic cross-project rule libraries. They carry evidence from
    # other projects but NO Hotel evidence -> experiment-pre relative to Hotel.
    se = _load_current("selection_experience.json")
    dp = _load_current("defense_pattern_library.json")
    je = _load_current("judgment_experience.json")

    snapshot = {
        "schema_version": 1,
        "status": "blocked",
        "status_reason": (
            "五源 source_provenance 均已验证为 experiment-pre (contract/availability = "
            "static_reconstructed_pre_experiment; SE/DP/JE = pre_experiment_commit, 无 Hotel 证据)。"
            "但 provenance_completeness=partial: availability 仅静态确认 docker-compose 单副本, "
            "kubernetes/ manifest 的 replicas/PDB 未逐文件确认。机制完整性不足 -> 完整 frozen "
            "engine replay 暂 blocked; 待扩展静态检查 kubernetes manifest 后才可提升。"
        ),
        "provenance": {
            "kind": "hotel_static_reconstructed",
            "source_commit": HOTEL_COMMIT,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_files": [
                f"{HOTEL_URL} (docker-compose.yml, README.md, go.mod, services/{'frontend,search'}, kubernetes/README.md)",
            ],
            "sha256": {
                "docker_compose_yml": "988b3e3d4c0c01c5032f47d6ff69db56a8245966ddb7dcaaef1b726ff641bc12",
                "README_md": "6696c99eb4f698efb76c4360cc74bcb2ed6db8cdab5959cd7166433030463346",
                "go_mod": "a5a886b6b67cea384f09f4497cc273b1d710dbe719d9904bd9258446fa38ce90",
                "kubernetes_README_md": "8c8c3a1fb1a9ad7bb41b1727545e4d4252e2b8a6c59b0be8e662a9692371ef53",
                "selection_experience_live": _sha256("artifacts/experiments/selection_experience.json"),
                "defense_pattern_library_live": _sha256("artifacts/experiments/defense_pattern_library.json"),
                "judgment_experience_live": _sha256("artifacts/experiments/judgment_experience.json"),
            },
            "provenance_completeness": "partial",
            "note": (
                "contract/availability STATIC-RECONSTRUCTED from canonical Hotel source "
                f"@{HOTEL_COMMIT[:12]} (pre-experiment; no Hotel runtime evidence). "
                "SE/DP/JE are generic cross-project rule libraries with NO Hotel evidence "
                "-> pre-experiment relative to Hotel. candidate_map intentionally empty "
                "(pool frozen after this snapshot per protocol). dialer 120s timeout is "
                "connection-level, NOT a per-request contract."
            ),
        },
        "contract": {
            "contracts": CONTRACTS_STATIC,
            "availability": AVAILABILITY_STATIC,
            "candidate_map": CANDIDATE_MAP_STATIC,
        },
        "selection_experience": se,
        "defense_pattern_library": dp,
        "judgment_experience": je,
        "source_provenance": {
            "contract": "static_reconstructed_pre_experiment",
            "availability": "static_reconstructed_pre_experiment",
            "selection_experience": "pre_experiment_commit",
            "defense_pattern_library": "pre_experiment_commit",
            "judgment_experience": "pre_experiment_commit",
        },
    }
    OUT.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    print("provenance:", snapshot["source_provenance"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
