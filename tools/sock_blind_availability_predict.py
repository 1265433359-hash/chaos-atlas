"""Blind static prediction of availability verdicts (audit round-2 fix #3).

Purpose: the "CE parity" claim suffered confirmation bias - we ran availability
experiments AFTER seeing ChaosEater's front-end verdict. This script redoes the
availability-layer prediction using ONLY static manifest facts (replicas/pdb/
probes), WITHHELD from the CE report entirely.

Prediction rule (pure static, derived from deployment YAML):
  - replicas == 1 AND no PDB  -> kill of the only pod = total outage
                                => prediction: weakness (AD-REDUNDANCY-001)
  - replicas > 1 OR PDB       -> single pod loss absorbed
                                => prediction: defended
  - probe presence affects OUTAGE WINDOW, not the weakness/defended call:
    no readiness probe -> new pod Ready on Running (gate-lack, still a weakness
    class, but the outage "window" is ~0). We predict weakness either way for
    single-replica.

This script does NOT read chaos_eater_deployed_vs_ours.md and does NOT read the
avail_*.json result files - it reads only manifest facts (via contract_inventory
AVAILABILITY, which is itself manifest-derived static data) and then compares
against the frozen runtime verdicts stored in sock_shop_verdicts.json.

Honest caveat: the manifest facts (contract_inventory AVAILABILITY) were
collected in the same session; the prediction is blind w.r.t. the CE report and
w.r.t. the runtime curves, but the static inventory itself was written with
knowledge of the deployment. That is fine - static manifest is a pre-runtime
artifact by nature.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from contract_inventory import AVAILABILITY  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
VERDICTS = ROOT / "artifacts" / "sock-shop" / "sock_shop_verdicts.json"
OUT = ROOT / "artifacts" / "sock-shop" / "sock_blind_availability_predictions.json"

SERVICES = ["front-end", "orders", "user", "carts", "shipping", "payment", "catalogue", "queue-master"]


def static_prediction(profile: dict) -> dict:
    replicas = int(profile.get("replicas", 1))
    pdb = profile.get("pdb")
    redundant = replicas > 1 or bool(pdb)
    if redundant:
        return {"prediction": "defended", "mechanism": f"redundancy (replicas={replicas}, pdb={'yes' if pdb else 'no'})"}
    return {"prediction": "weakness", "mechanism": "single-replica no-PDB -> kill = total outage"}


def main() -> int:
    verdicts = json.loads(VERDICTS.read_text(encoding="utf-8"))
    # runtime verdicts from avail_* experiments (frozen, but we read only the summary
    # verdicts, not the curves, and NOT the CE report)
    runtime: dict[str, str] = {}
    for v in verdicts.get("availability_layer", {}).get("verdicts", []):
        runtime[v["service"]] = v["verdict"]
    # services not runtime-verified but in static inventory: mark static-inferred
    rows = []
    for svc in SERVICES:
        key = {
            "front-end": "FRONTEND", "orders": "ORDER", "user": "USER", "carts": "CART",
            "shipping": "SHIPPING", "payment": "PAYMENT", "catalogue": "CATALOGUE",
            "queue-master": "QUEUE-MASTER",
        }[svc]
        profile = AVAILABILITY["SOCK"].get(key)
        if not profile:
            rows.append({"service": svc, "prediction": "N/A (no static profile)", "runtime": runtime.get(svc)})
            continue
        pred = static_prediction(profile)
        rt = runtime.get(svc)
        rows.append({
            "service": svc,
            "prediction": pred["prediction"],
            "mechanism": pred["mechanism"],
            "replicas": profile["replicas"],
            "pdb": profile["pdb"],
            "runtime_verdict": rt if rt else "static-inferred (not runtime-tested)",
            "aligned": (pred["prediction"] == rt) if rt else None,
        })

    result = {
        "schema_version": 1,
        "tool": "sock_blind_availability_predictions",
        "date": "2026-08-09",
        "audit_fix": "round-2 #3: availability prediction blind w.r.t. ChaosEater report and runtime curves",
        "rule": "replicas==1 and no PDB -> weakness; replicas>1 or PDB -> defended (AD-REDUNDANCY-001, static only)",
        "inputs": "contract_inventory.AVAILABILITY (manifest-derived static facts) ONLY; CE report NOT consulted",
        "rows": rows,
        "summary": {
            "runtime_aligned": sum(1 for r in rows if r.get("aligned") is True),
            "runtime_tested": sum(1 for r in rows if r.get("aligned") is not None),
            "static_inferred_only": sum(1 for r in rows if r.get("aligned") is None),
        },
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], indent=2, ensure_ascii=False))
    for r in rows:
        if r.get("aligned") is True:
            mark = "OK "
        elif r.get("aligned") is False:
            mark = "!! "
        else:
            mark = "-- "
        print(f"{mark}{r['service']:14s} static={r['prediction']:9s} runtime={r.get('runtime_verdict','-')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
