"""Frozen-knowledge replay for Sock Shop: TWO products (2026-08-10).

The old script called score_candidate() (which read live knowledge) and then
overrode the prediction with a hardcoded FROZEN_KNOWLEDGE value. That is a
STATIC PREDICTION AUDIT, not an engine replay. This rewrite splits into two
independent products:

  1. sock_frozen_static_prediction_audit.json (KEPT, renamed from
     sock_frozen_knowledge_predictions.json semantics): compares the static
     prediction (derived only from pre-experiment bytecode/manifest) against
     the experiment ground truth. This is evaluation reproducibility of the
     STATIC KNOWLEDGE, not of the engine.

  2. sock_frozen_decision_engine_replay.json (NEW): runs the REAL engine
     (score_candidate / rank) with a knowledge_snapshot injected so that NO
     live JSON and NO module-level registry is read. The engine's actual
     output (hard_skip/priority/score/reasons) is recorded; the static
     prediction and ground truth are recorded SEPARATELY. hard_skip=False is
     NOT interpreted as weakness. Because SE/DP/JE in the snapshot are marked
     posthoc_or_current (no pre-Sock-experiment clean commit exists), the
     replay product is marked status=blocked for a full four-source
     experiment-pre claim — the engine-replay mechanism itself works, but it
     cannot claim experiment-pre knowledge for SE/DP/JE.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from decision_engine import (  # noqa: E402
    rank,
    score_candidate,
    snapshot_is_full_experiment_pre,
    validate_knowledge_snapshot,
)

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "artifacts" / "sock-shop" / "sock_knowledge_snapshot_static.json"
AUDIT_OUT = ROOT / "artifacts" / "sock-shop" / "sock_frozen_static_prediction_audit.json"
REPLAY_OUT = ROOT / "artifacts" / "sock-shop" / "sock_frozen_decision_engine_replay.json"

# Static predictions derived ONLY from pre-experiment evidence (jar javap /
# manifest), independent of the engine.
STATIC_PREDICTIONS = {
    "SOCK-ORDERS-PAYMENT-DELAY-2000": "defended",
    "SOCK-ORDERS-PAYMENT-LOSS-100": "defended",
    "SOCK-ORDERS-SHIPPING-DELAY-2000": "defended",
    "SOCK-ORDERS-SHIPPING-LOSS-100": "defended",
    "SOCK-FRONTEND-CARTS-DELAY-2000": "weakness",
    "SOCK-FRONTEND-CARTS-LOSS-100": "weakness",
    "SOCK-FRONTEND-CATALOGUE-DELAY-2000": "weakness",
    "SOCK-FRONTEND-CATALOGUE-LOSS-100": "weakness",
}

# Ground truth from the real-chain / availability experiments (frozen).
GROUND_TRUTH = {
    "SOCK-ORDERS-PAYMENT-DELAY-2000": "defended",
    "SOCK-ORDERS-PAYMENT-LOSS-100": "defended",
    "SOCK-ORDERS-SHIPPING-DELAY-2000": "defended",
    "SOCK-ORDERS-SHIPPING-LOSS-100": "defended",
    "SOCK-FRONTEND-CARTS-DELAY-2000": "weakness",
    "SOCK-FRONTEND-CARTS-LOSS-100": "weakness",
    "SOCK-FRONTEND-CATALOGUE-DELAY-2000": "weakness",
    "SOCK-FRONTEND-CATALOGUE-LOSS-100": "weakness",
}

# Alignment rule: hard_skip=True on a contract edge whose static prediction is
# 'defended' is an aligned protected-skip; hard_skip=False on an unprotected
# edge (static 'weakness') means 'would execute' which is aligned with weakness
# discovery. But hard_skip=False does NOT itself mean weakness — the engine
# only recommends execution; the ground truth is the authority.
def align_engine(engine: dict, static_pred: str, truth: str) -> tuple[bool, str]:
    if static_pred == "defended":
        # protected edge: engine should hard-skip
        ok = bool(engine.get("hard_skip"))
        return ok, "protected_skip_aligned" if ok else "protected_skip_missed"
    # unprotected edge: engine should recommend execution (no hard skip)
    ok = not engine.get("hard_skip")
    return ok, "unprotected_execute_aligned" if ok else "unprotected_wrongly_skipped"


def main() -> int:
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    validate_knowledge_snapshot(snapshot)
    full_pre = snapshot_is_full_experiment_pre(snapshot)
    candidates = [{"candidate_id": cid, "edge": "unknown"} for cid in STATIC_PREDICTIONS]

    # ---------------- product 1: static prediction audit ----------------
    audit_rows = []
    for cid in STATIC_PREDICTIONS:
        pred = STATIC_PREDICTIONS[cid]
        truth = GROUND_TRUTH[cid]
        audit_rows.append({
            "candidate_id": cid,
            "static_prediction": pred,
            "experiment_ground_truth": truth,
            "aligned": pred == truth,
        })
    audit = {
        "schema_version": 1,
        "tool": "sock_frozen_static_prediction_audit",
        "date": "2026-08-10",
        "status": "valid",
        "product_note": (
            "STATIC PREDICTION AUDIT (NOT engine replay): static predictions are "
            "derived ONLY from pre-experiment bytecode/manifest (orders jar javap "
            "Future.get x3 + ${http.timeout:5}; front-end synchronous request no-timeout). "
            "This proves the static knowledge itself predicts the observed ground truth "
            "(evaluation reproducibility of the knowledge), not that the engine was re-run "
            "with frozen inputs."
        ),
        "aligned_count": sum(1 for r in audit_rows if r["aligned"]),
        "total": len(audit_rows),
        "rows": audit_rows,
    }
    AUDIT_OUT.write_text(json.dumps(audit, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    # ---------------- product 2: engine replay ----------------
    # Run the REAL engine with the injected snapshot. The engine reads nothing
    # live when a snapshot is present. Because SE/DP/JE provenance is
    # posthoc_or_current, the full experiment-pre replay is BLOCKED; the
    # engine-vs-static alignment is reported ONLY as a diagnostic, never as a
    # validated replay accuracy.
    replay_rows = []
    for cid in STATIC_PREDICTIONS:
        cand = {"candidate_id": cid, "edge": "unknown"}
        engine = score_candidate(cand, knowledge_snapshot=snapshot)
        pred = STATIC_PREDICTIONS[cid]
        truth = GROUND_TRUTH[cid]
        aligned, rule = align_engine(engine, pred, truth)
        replay_rows.append({
            "candidate_id": cid,
            "engine_output": {
                "hard_skip": bool(engine.get("hard_skip")),
                "priority": engine.get("priority"),
                "score": engine.get("score"),
                "reasons": engine.get("reasons", [])[:4],
            },
            "static_prediction": pred,
            "experiment_ground_truth": truth,
            "alignment_definition": rule,
            # Blocked snapshots retain diagnostic alignment only. A genuinely
            # experiment-pre snapshot may expose the same comparison as validated.
            "aligned": aligned if full_pre else None,
            "diagnostic_aligned": aligned,
            "provenance_status": snapshot["source_provenance"],
        })
    # Replay validity is DERIVED from provenance, not hardcoded.
    replay_status = "valid" if full_pre else "blocked"
    if full_pre:
        status_reason = (
            "All five knowledge sections are experiment-pre and provenance is complete; "
            "the engine replay used the injected snapshot with zero live reads."
        )
        alignment_status = "validated_replay"
        aligned_count = sum(1 for r in replay_rows if r["diagnostic_aligned"])
    else:
        status_reason = (
            "Engine-replay mechanism is implemented and runs with zero live reads "
            "(snapshot injected into all six consumers + rank). "
            "full_experiment_pre=False derived from source_provenance/completeness. "
            "SE/DP/JE are posthoc_or_current - no pre-Sock-experiment clean commit "
            "exists (f870e32 is r2-pre, not Sock-pre). A full four-source "
            "experiment-pre frozen engine replay therefore CANNOT claim experiment-pre "
            "knowledge. Only the static prediction audit (product 1) is a valid "
            "evaluation-reproducibility claim."
        )
        alignment_status = "diagnostic_only_not_claimed"
        aligned_count = None
    replay = {
        "schema_version": 1,
        "tool": "sock_frozen_decision_engine_replay",
        "date": "2026-08-10",
        "status": replay_status,
        "status_reason": status_reason,
        "zero_live_read": True,
        "engine_outputs_are_engine": True,
        "static_prediction_not_overriding_engine": True,
        # Diagnostic fields (NOT validated replay accuracy):
        "alignment_status": alignment_status,
        "diagnostic_alignment_count": sum(1 for r in replay_rows if r["diagnostic_aligned"]),
        "diagnostic_total": len(replay_rows),
        "aligned_count": aligned_count,
        "total": len(replay_rows),
        "rows": replay_rows,
    }
    REPLAY_OUT.write_text(json.dumps(replay, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    print(f"audit: {AUDIT_OUT.name} aligned {audit['aligned_count']}/{audit['total']}")
    print(f"replay: {REPLAY_OUT.name} status={replay['status']} diagnostic {replay['diagnostic_alignment_count']}/{replay['diagnostic_total']}")
    for r in replay_rows:
        print(f"  {r['candidate_id']:38s} hard_skip={r['engine_output']['hard_skip']} "
              f"prio={r['engine_output']['priority']:<16} static={r['static_prediction']:9s} "
              f"truth={r['experiment_ground_truth']:9s} {r['alignment_definition']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
