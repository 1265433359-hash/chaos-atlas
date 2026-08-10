#!/usr/bin/env python3
"""Build the Sock Shop STATIC-RECONSTRUCTED knowledge snapshot for frozen replay.

Provenance honesty (2026-08-10):
  - contract   : reconstructed from PRE-experiment static evidence only:
                 jar javap bytecode (Future.get(timeout,SECONDS) x3 at bytecode
                 offsets 153/178/201 + class constant "${http.timeout:5}" +
                 TimeoutException string) for orders->payment/shipping, and
                 front-end api/cart+api/catalogue synchronous request() with no
                 downstream timeout for front-end->carts/catalogue.
                 loss_bounded is a STATIC INFERENCE from Future.get semantics
                 (connection-refused fast-fail / blackhole bound at the same
                 deadline); it is NOT claimed to pre-exist in the live registry.
                 Marked source: "static_inferred".
  - availability : manifest facts (replicas=1, no PDB) reconstructed from the
                 deployment YAML; static, pre-experiment.
  - SE / DP / JE: NO pre-Sock-experiment clean version exists in git history
                 (f870e32 already contains Sock Shop entries; dade158/3f68115/
                 182f995 predate it). These are copied from the CURRENT working
                 tree and marked provenance "posthoc_or_current". A full
                 four-source frozen engine replay therefore CANNOT claim
                 experiment-pre knowledge for these three sources -> the replay
                 product must be marked blocked (see sock_frozen_knowledge_rerun).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / "artifacts" / "experiments"
OUT = ROOT / "artifacts" / "sock-shop" / "sock_knowledge_snapshot_static.json"

# --- contract: STATIC-RECONSTRUCTED (pre-experiment evidence) ---
CONTRACTS_STATIC = {
    "SOCK-orders->payment": {
        "contract": "explicit_timeout",
        "loss_bounded": True,
        "loss_bounded_source": "static_inferred",
        "evidence": "STATIC: orders jar OrdersController.newOrder bytecode offsets 153/178/201 invoke Future.get(timeout, TimeUnit.SECONDS); class constant '${http.timeout:5}'; TimeoutException in catch. No experiment data used.",
        "note": "5s Future.get timeout; loss_bounded = static inference from Future.get semantics (bounded, never infinite hang), NOT claimed as pre-existing live registry field.",
    },
    "SOCK-orders->shipping": {
        "contract": "explicit_timeout",
        "loss_bounded": True,
        "loss_bounded_source": "static_inferred",
        "evidence": "STATIC: same OrdersController.newOrder bytecode (shared http.timeout); Future.get at bytecode offset 178 (shipping).",
        "note": "Shared 5s Future.get with orders->payment; loss_bounded = static_inferred.",
    },
    "SOCK-frontend->carts": {
        "contract": "no_timeout",
        "loss_bounded": False,
        "evidence": "STATIC: front-end api/cart/index.js uses synchronous request() with no per-request timeout on downstream fetch.",
        "note": "No timeout -> loss hangs caller, delay amplifies 1:1 (unprotected).",
    },
    "SOCK-frontend->catalogue": {
        "contract": "no_timeout",
        "loss_bounded": False,
        "evidence": "STATIC: front-end api/catalogue uses synchronous request() with no timeout.",
        "note": "No timeout -> unprotected.",
    },
}

AVAILABILITY_STATIC = {
    "SOCK": {
        "FRONTEND": {"replicas": 1, "pdb": None, "hpa": None, "static_prediction": "single-replica no-PDB -> kill = total outage", "service": "FRONTEND"},
        "ORDER": {"replicas": 1, "pdb": None, "hpa": None, "static_prediction": "single-replica no-PDB no-probes -> kill = total outage", "service": "ORDER"},
        "PAYMENT": {"replicas": 1, "pdb": None, "hpa": None, "static_prediction": "single-replica no-PDB -> kill = total outage", "service": "PAYMENT"},
        "SHIPPING": {"replicas": 1, "pdb": None, "hpa": None, "static_prediction": "single-replica no-PDB no-probes -> kill = total outage", "service": "SHIPPING"},
        "USER": {"replicas": 1, "pdb": None, "hpa": None, "static_prediction": "single-replica no-PDB -> kill = total outage", "service": "USER"},
        "CART": {"replicas": 1, "pdb": None, "hpa": None, "static_prediction": "single-replica no-PDB no-probes -> kill = total outage", "service": "CART"},
        "CATALOGUE": {"replicas": 1, "pdb": None, "hpa": None, "static_prediction": "single-replica no-PDB -> kill = total outage", "service": "CATALOGUE"},
        "QUEUE-MASTER": {"replicas": 1, "pdb": None, "hpa": None, "static_prediction": "single-replica no-PDB -> kill = total outage", "service": "QUEUE-MASTER"},
    }
}

CANDIDATE_MAP_STATIC = {
    "SOCK-ORDERS-PAYMENT-DELAY-2000": "SOCK-orders->payment",
    "SOCK-ORDERS-PAYMENT-LOSS-100": "SOCK-orders->payment",
    "SOCK-ORDERS-SHIPPING-DELAY-2000": "SOCK-orders->shipping",
    "SOCK-ORDERS-SHIPPING-LOSS-100": "SOCK-orders->shipping",
    "SOCK-FRONTEND-CARTS-DELAY-2000": "SOCK-frontend->carts",
    "SOCK-FRONTEND-CARTS-LOSS-100": "SOCK-frontend->carts",
    "SOCK-FRONTEND-CATALOGUE-DELAY-2000": "SOCK-frontend->catalogue",
    "SOCK-FRONTEND-CATALOGUE-LOSS-100": "SOCK-frontend->catalogue",
}


def _load_current(rel: str) -> dict:
    return json.loads((EXPERIMENTS / rel).read_text(encoding="utf-8"))


def main() -> int:
    # SE/DP/JE are copied from CURRENT working tree; provenance marks posthoc.
    se = _load_current("selection_experience.json")
    dp = _load_current("defense_pattern_library.json")
    je = _load_current("judgment_experience.json")

    snapshot = {
        "schema_version": 1,
        "provenance": {
            "kind": "sock_static_reconstructed",
            "source_commit": "unknown-or-commit",  # see note: no pre-Sock commit exists
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_files": [
                "orders:0.4.7 jar javap (bytecode offsets 153/178/201, ${http.timeout:5})",
                "front-end api/cart/index.js + api/catalogue (synchronous request, no timeout)",
                "sock-shop deployment YAML (replicas=1, no PDB)",
            ],
            "sha256": {},
            "note": (
                "contract + availability are STATIC-RECONSTRUCTED from pre-experiment evidence; "
                "loss_bounded marked static_inferred. SE/DP/JE have NO pre-Sock-experiment clean "
                "commit (f870e32 is r2-pre, not Sock-pre, and already contains Sock entries) -> "
                "marked posthoc_or_current. Full four-source frozen engine replay is BLOCKED; "
                "only static prediction audit is valid."
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
            "selection_experience": "posthoc_or_current",
            "defense_pattern_library": "posthoc_or_current",
            "judgment_experience": "posthoc_or_current",
        },
    }
    OUT.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    print("provenance:", snapshot["source_provenance"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
