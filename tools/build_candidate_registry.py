#!/usr/bin/env python3
"""Build the candidate pool registry (A4): merge all 5 source pools into one
unique register of 54 candidates with executed/ground-truth/protected status.

Pools:
  - core 12  : execution/deep_matrix_registry_r1_m1.json candidate_universe
  - extended 20 : execution/candidate_evidence_status.json
  - r2 18    : execution/prospective_pool_r2.json
  - sock 8   : sock-shop/sock_shop_verdicts.json
  - mixed 8  : online-boutique/mixed_pool_candidates.json

OTEL/TT r2 candidates not deployed are marked environment_blocked/not_executed
(NOT deleted). Pure read + new JSON output.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "experiments" / "archive" / "candidate_pool_registry.json"


def load(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def project_of(cid: str) -> str:
    for p in ("SOCK", "OB", "OTEL", "TT"):
        if cid.upper().startswith(p + "-"):
            return p
    return "UNKNOWN"


def main() -> int:
    core = load("artifacts/experiments/execution/deep_matrix_registry_r1_m1.json")["candidate_universe"]
    evidence = load("artifacts/experiments/execution/candidate_evidence_status.json")
    r2 = load("artifacts/experiments/execution/prospective_pool_r2.json")["candidates"]
    sock = load("artifacts/sock-shop/sock_shop_verdicts.json")["candidates"]
    mixed = load("artifacts/online-boutique/mixed_pool_candidates.json")["candidates"]

    # executed status from evidence (own_discovery_evidence / own_conclusions)
    executed = {c["candidate_id"] for c in evidence["candidates"] if c.get("own_discovery_evidence") or c.get("own_conclusions")}
    # r2 executed (has run files) = 8 OB candidates
    r2_executed = {"OB-CART-LOSS-100", "OB-CHECKOUT-LOSS-100", "OB-CURRENCY-DELAY-2000",
                   "OB-CURRENCY-LOSS-100", "OB-EMAIL-DELAY-2000", "OB-EMAIL-LOSS-100",
                   "OB-PRODUCTCATALOG-LOSS-100", "OB-SHIPPING-LOSS-100"}

    registry: dict[str, dict] = {}

    for cid in core:
        registry[cid] = {"candidate_id": cid, "project_id": project_of(cid),
                         "target_edge": "core registry (12)", "fault": "unknown",
                         "protected_status": "unknown", "source_registry": "core12"}

    for c in evidence["candidates"]:
        cid = c["candidate_id"]
        registry.setdefault(cid, {"candidate_id": cid, "project_id": project_of(cid)})
        registry[cid].update({
            "target_edge": c.get("edge", "unknown"),
            "fault": cid.split("-")[-1].split("_")[0] if "-" in cid else "unknown",
            "protected_status": "unknown",
            "source_registry": "extended20",
        })

    for c in r2:
        cid = c["candidate_id"]
        registry.setdefault(cid, {"candidate_id": cid, "project_id": project_of(cid)})
        registry[cid].update({
            "target_edge": c.get("edge", "unknown"),
            "fault": c.get("fault", "unknown"),
            "contract_label_in_pool": c.get("contract", "unknown"),
            "source_registry": "r2_18",
        })

    for c in sock:
        cid = c["candidate_id"]
        registry.setdefault(cid, {"candidate_id": cid, "project_id": "SOCK"})
        registry[cid].update({
            "target_edge": c.get("edge", "unknown"),
            "fault": "unknown",
            "verdict": c.get("verdict", "unknown"),
            "source_registry": "sock8",
        })

    for c in mixed:
        cid = c["candidate_id"]
        registry.setdefault(cid, {"candidate_id": cid, "project_id": project_of(cid)})
        registry[cid].update({
            "target_edge": c.get("edge", "unknown"),
            "fault": cid.split("-")[-1].split("_")[0] if "-" in cid else "unknown",
            "contract_label_in_pool": c.get("contract", "unknown"),
            "source_registry": "mixed8",
        })

    # ground-truth / executed / protected resolution
    for cid, rec in registry.items():
        rec["project_id"] = project_of(cid)
        rec["executed_status"] = "executed" if (cid in executed or cid in r2_executed or cid in {c["candidate_id"] for c in sock}) else "not_executed"
        # r2 not-deployed OTEL/TT candidates -> environment_blocked
        if rec.get("source_registry") == "r2_18" and rec["executed_status"] == "not_executed":
            rec["environment_blocked"] = True
            rec["exclusion_reason"] = "r2 executed only on OB (cluster had OB images; OTEL/TT not deployed)"
        else:
            rec["environment_blocked"] = False
            rec["exclusion_reason"] = None
        rec["usable_for_head_to_head"] = rec["executed_status"] == "executed"
        # protected status best-effort from known contract facts
        if cid.startswith("OB-FRONTEND-ADSERVICE") or cid.startswith("SOCK-ORDERS"):
            rec["protected_status"] = "protected"
        elif cid.startswith("SOCK-FRONTEND"):
            rec["protected_status"] = "unprotected"
        else:
            rec["protected_status"] = rec.get("contract_label_in_pool", "unknown")

    records = sorted(registry.values(), key=lambda r: (r["project_id"], r["candidate_id"]))
    result = {
        "schema_version": 1,
        "tool": "candidate_pool_registry",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_pools": {"core12": 12, "extended20": 20, "r2_18": 18, "sock8": 8, "mixed8": 8},
        "unique_candidate_count": len(records),
        "executed_count": sum(1 for r in records if r["executed_status"] == "executed"),
        "not_executed_count": sum(1 for r in records if r["executed_status"] == "not_executed"),
        "environment_blocked_count": sum(1 for r in records if r["environment_blocked"]),
        "note": "OTEL/TT r2 candidates are marked environment_blocked/not_executed, NOT deleted.",
        "candidates": records,
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"unique={len(records)} executed={result['executed_count']} not_executed={result['not_executed_count']} "
          f"env_blocked={result['environment_blocked_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
