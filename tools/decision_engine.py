"""P2: decision_engine - combine the three knowledge libraries into candidate priority.

The toolified 'reusable methodology' (knowledge_closed_loop.md): given a set
of candidate injections for a NEW project, produce a priority ranking +
skip recommendations by composing:

1. SELECTION experience (SE-*): which families/paths are worth testing first
   (corpus + experiment backed). Contested rules are downgraded to weight 0
   (adjudication pending) unless accepted.
2. DEFENSE patterns (DP-*): skip/prioritize-low edges whose mechanism is
   source-verified on a same-fingerprint edge.
3. JUDGMENT experience (JE-*): severity_adjustment hints (coupling upgrades,
   no-contract downgrades) for the ranking.

Dual-track hard filters (2026-08-09, availability_defense_design.md):
- availability_hard_filter: KILL/CPU candidate on a single-replica no-PDB
  service is a CONFIRMED single-point-of-failure - verdict known a priori
  (AD-REDUNDANCY-001), routes the candidate to the availability track.
- contract_hard_filter: DELAY candidate on a source-verified explicit_timeout
  edge is protected (timeout covers delay), plus LOSS when the edge is
  loss_bounded (Future.get-style defenses bound loss too).

This runs WITHOUT the LLM — it is the auditable rule layer of the method.
The LLM layer (M1/M5) is a separate, optional enhancer.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / "artifacts" / "experiments"
SE_PATH = EXPERIMENTS / "selection_experience.json"
DP_PATH = EXPERIMENTS / "defense_pattern_library.json"
JE_PATH = EXPERIMENTS / "judgment_experience.json"

# Default weights (auditable; a score-0 candidate gets base score + selection hits).
BASE = 10.0
CONTESTED_PENALTY = 5.0  # contested-but-not-adjudicated rules get halved weight


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _se_weight(entry: dict[str, Any]) -> float:
    """Weight of a selection rule: confidence-scaled, contested halved."""
    w = {"high": 1.0, "medium": 0.6, "low": 0.3}.get(entry.get("confidence"), 0.5)
    if entry.get("contested") and not entry.get("adjudicated"):
        w *= 0.5
    return w


def selection_hits(candidate: dict[str, Any]) -> list[tuple[str, float]]:
    """Which SE rules this candidate matches, with effective weight."""
    from project_registry import fault_of, normalize_service

    se = load(SE_PATH)
    cid = candidate.get("candidate_id", "")
    service = normalize_service(cid, strict=True)
    fault = fault_of(cid)
    hits: list[tuple[str, float]] = []
    for entry in se.get("entries", []):
        eid = entry.get("id", "")
        matched = False
        if eid == "SE-NETWORK-FAMILY-001" and fault in ("delay", "loss"):
            matched = True
        elif eid == "SE-LOSS-STRONGEST-001" and fault == "loss":
            matched = True
        elif eid == "SE-CORE-CHAIN-001" and service in ("PAYMENT", "CART", "CHECKOUT"):
            matched = True
        elif eid == "SE-SIDEEFFECT-COUPLING-001" and service == "EMAIL":
            matched = True
        elif eid == "SE-CROSSPROJECT-REPLICATION-001":
            # only applies when a same-service weakness was confirmed elsewhere
            matched = candidate.get("cross_project_replication", False)
        if matched:
            hits.append((eid, _se_weight(entry)))
    return hits


def defense_downgrade(candidate: dict[str, Any]) -> dict[str, Any]:
    """Skip/priority-low recommendation from the defense-pattern library."""
    from defense_pattern_library import query_downgrade, load_library

    lib = load_library(DP_PATH)
    return query_downgrade(candidate, lib)


def judgment_hint(candidate: dict[str, Any]) -> str:
    """Severity-adjustment hint from judgment experience, or empty."""
    from project_registry import normalize_service

    je = load(JE_PATH)
    service = normalize_service(candidate.get("candidate_id", "") or "")
    for entry in je.get("entries", []):
        if entry.get("id") == "JE-COUPLING-001" and service == "EMAIL":
            return f"JE-COUPLING-001: {entry['severity_adjustment']} (coupling)"
        if entry.get("id") == "JE-CONTRACT-002" and entry.get("severity_adjustment") == "downgrade":
            pass  # contract downgrade applied via contract_inventory, not here
    return ""


def availability_hard_filter(candidate: dict[str, Any]) -> dict[str, Any]:
    """Availability-layer hard constraint (dual-track, 2026-08-09).

    A KILL/CPU candidate on a service whose static deployment profile shows NO
    redundancy (replicas==1 and no PDB) is a CONFIRMED single-point-of-failure:
    killing the only pod = total outage, by definition. This is a hard skip on
    budget (we already know the verdict from static evidence) and routes the
    candidate to the availability track instead of the contract track.

    NOT a copy of ChaosEater's hardcoded availableReplicas check: the profile
    comes from the contract-inventory AVAILABILITY registry (manifest facts),
    the rule is an auditable rule in this engine, and the evidence is
    static(manifest) + runtime(kill) dual-chain, not a single threshold.
    """
    from project_registry import project_of, normalize_service, fault_of

    cid = candidate.get("candidate_id", "")
    if not cid:
        return {}
    if fault_of(cid) not in ("kill", "cpu"):
        return {}
    from contract_inventory import availability_for_service

    # Phase-4: strict=True so an unknown project fails closed instead of being
    # silently routed into the train-ticket availability universe.
    profile = availability_for_service(project_of(cid, strict=True), normalize_service(cid, strict=True))
    if not profile:
        return {}
    redundant = int(profile.get("replicas", 1)) > 1 or bool(profile.get("pdb"))
    if not redundant:
        return {
            "hard_skip": True,
            "availability": True,
            "reason": (
                f"service {profile['service']} is single-replica no-PDB "
                f"(static manifest): {cid.split('-')[0]} kill/cpu of the only pod = "
                f"total outage, verdict known a priori (AD-REDUNDANCY-001); "
                f"execute only for evidence-chain completeness, not for selection"
            ),
            "evidence": profile.get("static_prediction", "")[:100],
        }
    return {"redundant": True, "reason": f"service {profile['service']} has redundancy (replicas={profile['replicas']})"}


def contract_hard_filter(candidate: dict[str, Any]) -> dict[str, Any]:
    """Contract inventory as a HARD constraint (not a hint): a delay candidate
    on a source-verified explicit_timeout edge is protected (timeout covers
    delay) and must be skipped before any scoring. Loss faults are NOT
    protected by a timeout. Returns the skip decision or empty dict."""
    inv_path = EXPERIMENTS / "contract_inventory.json"
    if not inv_path.exists():
        return {}
    inv = json.loads(inv_path.read_text(encoding="utf-8"))
    cand_map = inv.get("candidate_map", {})
    cid = candidate.get("candidate_id", "")
    # Prefer the candidate->contract-edge map (business edge strings like
    # 'frontend->productcatalog' are NOT the contract keys); fall back to the
    # candidate-provided edge only if no map entry exists.
    edge = cand_map.get(cid) or candidate.get("edge")
    contracts = inv.get("contracts", {})
    contract = contracts.get(edge or "")
    if not contract:
        return {}
    upper = cid.upper()
    is_delay = "DELAY" in upper
    # Future.get-style async defenses also bound LOSS (connection-refused
    # fast-fails; blackhole times out at the same deadline) - NEVER an infinite
    # hang. Only edges explicitly marked loss_bounded in the inventory get the
    # LOSS hard-skip; ordinary timeouts (e.g. OB adservice 100ms) do NOT cover
    # loss in the default model (loss == 100% packet drop is still high value).
    is_loss = "LOSS" in upper
    loss_covered = is_loss and bool(contract.get("loss_bounded"))
    if contract.get("contract") == "explicit_timeout" and (is_delay or loss_covered):
        return {
            "hard_skip": True,
            "reason": f"edge {edge} is source-verified explicit_timeout; "
                      f"{'delay' if is_delay else 'loss'} is covered by the timeout"
                      f"{' (loss_bounded)' if loss_covered else ''} (contract_inventory)",
            "evidence": contract.get("evidence", "")[:80],
        }
    return {}


def score_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """Score a candidate from the three libraries (no LLM)."""
    # Hard constraint 1: availability layer — single-replica no-PDB kill/cpu
    # verdict is known a priori (AD-REDUNDANCY-001), route to availability track.
    avail = availability_hard_filter(candidate)
    if avail.get("hard_skip"):
        return {
            "candidate_id": candidate.get("candidate_id"),
            "edge": candidate.get("edge"),
            "score": -999.0,
            "priority": "availability_known",
            "reasons": [avail["reason"]],
            "hard_skip": True,
            "availability_track": True,
        }
    # Hard constraint 2: contract layer — timeout-protected delay is excluded.
    hard = contract_hard_filter(candidate)
    if hard.get("hard_skip"):
        return {
            "candidate_id": candidate.get("candidate_id"),
            "edge": candidate.get("edge"),
            "score": -999.0,
            "priority": "skip_protected",
            "reasons": [hard["reason"]],
            "hard_skip": True,
        }
    hits = selection_hits(candidate)
    base = float(candidate.get("base_score", BASE))
    se_score = sum(weight for _, weight in hits) * 10.0
    downgrade = defense_downgrade(candidate)
    score = base + se_score
    priority = "high"
    reasons = [f"base {base:.0f}"]
    for eid, w in hits:
        reasons.append(f"{eid} (w={w:.2f})")
    if downgrade.get("downgrade"):
        # skip-recommended beats everything (defense pattern verified).
        if downgrade.get("skip_recommended"):
            priority = "skip_recommended"
            score = -999.0
            reasons.append(f"DP skip: {downgrade.get('mechanism')} ({downgrade.get('matching_patterns')})")
        else:
            score -= 10.0
            priority = "low"
            reasons.append(f"DP downgrade: {downgrade.get('mechanism')}")
    hint = judgment_hint(candidate)
    if hint:
        if "upgrade" in hint:
            score += 10.0
            priority = "high"
        reasons.append(hint)
    if downgrade.get("execution_override"):
        score += 30.0
        priority = "high"
        reasons.append("execution override: behavior shows weakness")
    return {
        "candidate_id": candidate.get("candidate_id"),
        "edge": candidate.get("edge"),
        "score": round(score, 1),
        "priority": priority,
        "reasons": reasons,
    }


def rank(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted((score_candidate(c) for c in candidates), key=lambda r: (-r["score"], r["candidate_id"]))
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    return ranked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True,
                        help="JSON: {\"candidates\": [{candidate_id, edge, base_score?, cross_project_replication?}]}")
    parser.add_argument("--output", type=Path, default=EXPERIMENTS / "execution" / "decision_engine_ranking.json")
    args = parser.parse_args()
    doc = json.loads(args.candidates.read_text(encoding="utf-8"))
    ranked = rank(doc.get("candidates", []))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"schema_version": 1, "tool": "decision_engine", "ranking": ranked}, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    for r in ranked:
        print(f"{r['rank']:>2} {r['priority']:<16} {r['candidate_id']:<32} score={r['score']:<7} {'; '.join(r['reasons'][:4])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
