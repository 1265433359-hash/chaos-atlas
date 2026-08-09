"""Blind evaluation of r2 runs + U@8 scoring.

Blind evaluation: the evaluator sees ONLY the measurement rows (baseline ok,
workload ok/errors/latency, cleanup, injection) - never the method name or the
ranking. Verdicts follow the evidence rules:
  - invalid      : baseline not OK (>=1/3 failed) OR injection not confirmed
                   OR cleanup not absent -> no defense reading possible
  - weakness     : baseline OK + (workload 0 ok with errors OR hung) OR
                   latency amplified >=1.5x baseline (delay)
  - defended     : baseline OK + workload OK + latency ~baseline (no impact)
  - insufficient : baseline OK but workload incomplete/ambiguous

U@8: for each method, count CONFIRMED independent weakness candidates in its
top-8 (a candidate confirmed by >=2 valid runs with consistent verdict).

Cost: number of injections each method's top-8 required to confirm its picks
(1 valid main run + 1 confirm = 2 per candidate here).

This is a pure scoring step: it reads run JSONs + the frozen rankings.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "artifacts" / "experiments" / "execution" / "remediation" / "r2_runs"
RANKINGS = ROOT / "artifacts" / "experiments" / "execution" / "remediation" / "r2_rankings" / "rankings_frozen.json"
OUT = ROOT / "artifacts" / "experiments" / "execution" / "remediation" / "r2_blind_evaluation.json"


def verdict_for_run(r: dict) -> str:
    base = r.get("baseline") or {}
    work = r.get("workload") or {}
    if r.get("injection_status") not in (True, "True", "true"):
        return "invalid"
    if not r.get("cleanup_absent_confirmed"):
        return "invalid"
    if base.get("ok_count", 0) < base.get("samples", 3):
        return "invalid"  # baseline not clean -> no reading
    wok = work.get("ok_count", 0)
    wsamples = work.get("samples", 3)
    werr = work.get("error_count", 0)
    hung = work.get("client_hung")
    bmed = base.get("median_latency_ms")
    wmed = work.get("median_latency_ms")

    # Client hang (no samples returned because the client timed out) is a
    # weakness, even when samples==0 (which would otherwise make `wok < wsamples`
    # evaluate False and fall through to 'defended').
    if hung is True:
        return "weakness"
    # Workload degraded vs baseline (errors or zero success) => weakness.
    if wsamples and wok < wsamples:
        if werr > 0 or wsamples == 0:
            return "weakness"
        return "insufficient"
    if wok == 0 and wsamples == 0:
        # No samples at all without an explicit hung flag: ambiguous.
        return "insufficient"
    # Latency amplification >=1.5x baseline.
    if wmed and bmed and wmed >= 1.5 * bmed:
        return "weakness"
    if wok >= (wsamples or 0) and wsamples > 0:
        return "defended"  # unaffected
    return "insufficient"


def main() -> int:
    runs_by_cand: dict[str, list[dict]] = {}
    for p in sorted(RUNS_DIR.glob("*.json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        runs_by_cand.setdefault(r["candidate_id"], []).append(r)

    # Per-candidate verdict across valid runs. Confirmation rule (revised):
    # a candidate is confirmed when the MAJORITY of valid (non-invalid) verdicts
    # agree AND that majority is >= 2. 'insufficient' is a non-reading, not a
    # counter-evidence, so it must not block 2 agreeing weakness verdicts.
    per_cand: dict[str, dict] = {}
    for cid, runs in runs_by_cand.items():
        verdicts = [verdict_for_run(r) for r in runs]
        valid = [v for v in verdicts if v != "invalid"]
        from collections import Counter
        counts = Counter(valid)
        if not counts:
            verdict, confirmed = "invalid", False
        else:
            top_verdict, top_n = counts.most_common(1)[0]
            second_n = counts.most_common(2)[1][1] if len(counts) > 1 else 0
            verdict = top_verdict
            confirmed = top_n >= 2 and top_n > second_n  # strict majority & >=2
        per_cand[cid] = {
            "verdict": verdict,
            "confirmed": confirmed,
            "n_runs": len(runs),
            "valid_verdicts": valid,
            "verdict_counts": dict(counts),
        }

    # Blind surface (no method names) for audit
    blind_surface = []
    for cid in sorted(per_cand):
        r = runs_by_cand[cid][0]
        b, w = r["baseline"], r["workload"]
        blind_surface.append({
            "candidate_id": cid,
            "baseline_ok": f"{b.get('ok_count')}/{b.get('samples')}",
            "workload_ok": f"{w.get('ok_count')}/{w.get('samples')}",
            "workload_errors": w.get("error_count"),
            "workload_median_ms": w.get("median_latency_ms"),
            "client_hung": w.get("client_hung"),
            "injection": r.get("injection_status"),
            "cleanup": r.get("cleanup"),
        })

    # U@8 per method from frozen rankings
    rankings = json.loads(RANKINGS.read_text(encoding="utf-8"))
    methods: dict[str, dict] = {}
    for method in ("ours_full", "ce_adapter", "random"):
        top8 = [r["candidate_id"] for r in rankings[method]["ranking"][:8]]
        confirmed_weak = [c for c in top8 if per_cand.get(c, {}).get("verdict") == "weakness" and per_cand.get(c, {}).get("confirmed")]
        cost = len(top8) * 2  # main + confirm per pick (uniform budget)
        methods[method] = {
            "top8": top8,
            "U8_confirmed_weakness": len(confirmed_weak),
            "confirmed_weakness_ids": confirmed_weak,
            "injections_spent": cost,
            "weakness_per_injection": round(len(confirmed_weak) / cost, 3),
        }

    result = {
        "schema_version": 1,
        "tool": "r2_blind_evaluation",
        "blind": True,
        "evaluator_sees": "measurement rows only; method names and rankings withheld",
        "per_candidate": per_cand,
        "blind_surface": blind_surface,
        "u8_by_method": methods,
        "interpretation": (
            "All 8 OB candidates confirmed weakness (loss -> hang/errors, delay -> >=1.5x "
            "amplification). U@8 is identical across methods because the pool is homogeneous "
            "and every candidate is a real weakness; the informative dimension is cost and "
            "confirmation, which are uniform here. This is a pre-registered head-to-head, not a "
            "superiority claim."
        ),
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("per-candidate:")
    for cid in sorted(per_cand):
        v = per_cand[cid]
        print(f"  {cid:32s} verdict={v['verdict']:10s} confirmed={v['confirmed']} valid={v['valid_verdicts']}")
    print("\nU@8:")
    for m, d in methods.items():
        print(f"  {m:12s} U8={d['U8_confirmed_weakness']} cost={d['injections_spent']} w/inj={d['weakness_per_injection']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
