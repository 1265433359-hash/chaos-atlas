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


# ---------------------------------------------------------------------------
# Knowledge-snapshot injection (frozen decision-engine replay, 2026-08-10).
#
# The engine's six knowledge consumers read live files by default. For a
# frozen replay we inject an explicit KnowledgeSnapshot so the engine reads
# NOTHING from live files/module registries. A snapshot is a dict:
#
#   {
#     "schema_version": 1,
#     "provenance": {...},                    # kind/source_commit/sha256 etc
#     "contract": {"contracts": {}, "availability": {}, "candidate_map": {}},
#     "selection_experience": {"entries": []},
#     "defense_pattern_library": {"patterns": []},
#     "judgment_experience": {"entries": []},
#   }
#
# When a *_snapshot argument is None the consumer keeps the historical live
# behavior; when non-None it MUST NOT touch live files or module-level
# registries. Unknown/absent fields fail closed with a clear error.
# ---------------------------------------------------------------------------

SNAPSHOT_SCHEMA_VERSION = 1


def _fail_closed(what: str, missing: str) -> None:
    raise ValueError(
        f"knowledge snapshot missing required field '{missing}' in {what}; "
        "refusing to fall back to live knowledge (frozen replay must be isolated)"
    )


def _snapshot_contract(snapshot: dict[str, Any] | None, label: str) -> dict[str, Any]:
    if snapshot is None:
        return {}
    contract = snapshot.get("contract")
    if not isinstance(contract, dict):
        _fail_closed(label, "contract")
    for key in ("contracts", "availability", "candidate_map"):
        if key not in contract:
            _fail_closed(label, f"contract.{key}")
    return contract


def _snapshot_se(snapshot: dict[str, Any] | None, label: str) -> dict[str, Any]:
    if snapshot is None:
        return {}
    se = snapshot.get("selection_experience")
    if not isinstance(se, dict) or "entries" not in se:
        _fail_closed(label, "selection_experience.entries")
    return se


def _snapshot_dp(snapshot: dict[str, Any] | None, label: str) -> dict[str, Any]:
    if snapshot is None:
        return {}
    dp = snapshot.get("defense_pattern_library")
    if not isinstance(dp, dict) or "patterns" not in dp:
        _fail_closed(label, "defense_pattern_library.patterns")
    return dp


def _snapshot_je(snapshot: dict[str, Any] | None, label: str) -> dict[str, Any]:
    if snapshot is None:
        return {}
    je = snapshot.get("judgment_experience")
    if not isinstance(je, dict) or "entries" not in je:
        _fail_closed(label, "judgment_experience.entries")
    return je


# Allowed provenance enums for each of the five knowledge sections.
PROVENANCE_ENUMS = {
    "static_reconstructed_pre_experiment",
    "pre_experiment_commit",
    "posthoc_or_current",
    "unknown",
    "unavailable",
}

PROVENANCE_COMPLETENESS_ENUMS = {"complete", "partial"}

# The five source-provenance fields that must be present and enum-valid.
PROVENANCE_SECTIONS = (
    "contract",
    "availability",
    "selection_experience",
    "defense_pattern_library",
    "judgment_experience",
)


def validate_knowledge_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Validate the full snapshot schema; fail closed on any missing section or
    an illegal source-provenance enum.

    A snapshot whose SE/DP/JE provenance is anything other than
    static_reconstructed_pre_experiment / pre_experiment_commit cannot support
    a full experiment-pre frozen engine replay -> callers should treat the
    replay as blocked (see sock_frozen_knowledge_rerun).
    """
    label = "knowledge_snapshot"
    if not isinstance(snapshot, dict):
        raise ValueError("knowledge_snapshot must be a dict")
    if snapshot.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(
            f"knowledge_snapshot schema_version must be {SNAPSHOT_SCHEMA_VERSION}, "
            f"got {snapshot.get('schema_version')!r}"
        )
    if not isinstance(snapshot.get("provenance"), dict) or not snapshot["provenance"].get("kind"):
        _fail_closed(label, "provenance.kind")
    completeness = snapshot["provenance"].get("provenance_completeness")
    if completeness not in PROVENANCE_COMPLETENESS_ENUMS:
        _fail_closed(label, "provenance.provenance_completeness")
    # Require the five source-provenance fields with a legal enum.
    source_prov = snapshot.get("source_provenance")
    if not isinstance(source_prov, dict):
        _fail_closed(label, "source_provenance")
    for section in PROVENANCE_SECTIONS:
        value = source_prov.get(section)
        if value not in PROVENANCE_ENUMS:
            _fail_closed(label, f"source_provenance.{section} (must be one of {sorted(PROVENANCE_ENUMS)})")
    _snapshot_contract(snapshot, label)
    _snapshot_se(snapshot, label)
    _snapshot_dp(snapshot, label)
    _snapshot_je(snapshot, label)
    return snapshot


def snapshot_is_full_experiment_pre(snapshot: dict[str, Any]) -> bool:
    """True only when ALL five source-provenance fields are provably
    experiment-pre (static_reconstructed_pre_experiment or pre_experiment_commit).
    SE/DP/JE posthoc_or_current -> False (full four-source replay must be blocked)."""
    validate_knowledge_snapshot(snapshot)
    provenance = snapshot["provenance"]
    if provenance.get("provenance_completeness") != "complete":
        return False
    hashes = provenance.get("sha256")
    if not isinstance(hashes, dict) or not hashes:
        return False
    if any(value in (None, "", "unknown", "unavailable") for value in hashes.values()):
        return False
    source_prov = snapshot.get("source_provenance") or {}
    pre_ok = {"static_reconstructed_pre_experiment", "pre_experiment_commit"}
    return all(
        source_prov.get(section) in pre_ok
        for section in PROVENANCE_SECTIONS
    )


def _se_weight(entry: dict[str, Any]) -> float:
    """Weight of a selection rule: confidence-scaled, contested halved."""
    w = {"high": 1.0, "medium": 0.6, "low": 0.3}.get(entry.get("confidence"), 0.5)
    if entry.get("contested") and not entry.get("adjudicated"):
        w *= 0.5
    return w


def selection_hits(candidate: dict[str, Any], se_snapshot: dict[str, Any] | None = None) -> list[tuple[str, float]]:
    """Which SE rules this candidate matches, with effective weight.

    se_snapshot=None -> live selection_experience.json (historical behavior).
    se_snapshot given -> use ONLY the snapshot; never read the live file.
    """
    from project_registry import fault_of, normalize_service

    se = _snapshot_se(se_snapshot, "selection_hits") or load(SE_PATH)
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


def defense_downgrade(candidate: dict[str, Any], dp_snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    """Skip/priority-low recommendation from the defense-pattern library.

    dp_snapshot=None -> live defense_pattern_library.json (historical).
    dp_snapshot given -> use ONLY the snapshot patterns.
    """
    from defense_pattern_library import query_downgrade, load_library

    if dp_snapshot is not None:
        lib = _snapshot_dp(dp_snapshot, "defense_downgrade")
    else:
        lib = load_library(DP_PATH)
    return query_downgrade(candidate, lib)


def judgment_hint(candidate: dict[str, Any], je_snapshot: dict[str, Any] | None = None) -> str:
    """Severity-adjustment hint from judgment experience, or empty.

    je_snapshot=None -> live judgment_experience.json (historical).
    je_snapshot given -> use ONLY the snapshot entries.
    """
    from project_registry import normalize_service

    je = _snapshot_je(je_snapshot, "judgment_hint") or load(JE_PATH)
    service = normalize_service(candidate.get("candidate_id", "") or "")
    for entry in je.get("entries", []):
        if entry.get("id") == "JE-COUPLING-001" and service == "EMAIL":
            return f"JE-COUPLING-001: {entry['severity_adjustment']} (coupling)"
        if entry.get("id") == "JE-CONTRACT-002" and entry.get("severity_adjustment") == "downgrade":
            pass  # contract downgrade applied via contract_inventory, not here
    return ""


def availability_hard_filter(candidate: dict[str, Any], contract_snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
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

    contract_snapshot=None -> live behavior via contract_inventory.
    contract_snapshot given -> use ONLY snapshot.contract.availability, NEVER
    the module-level AVAILABILITY constant in contract_inventory.py.
    """
    from project_registry import project_of, normalize_service, fault_of

    # Native deployment nodes are preferred when supplied.  Their static
    # prior is a routing hint only; runtime availability/recovery oracles still
    # decide the outcome.  The legacy candidate path below remains compatible
    # with existing contract-inventory snapshots.
    native_node = candidate.get("deployment_node") if isinstance(candidate.get("deployment_node"), dict) else None
    if native_node:
        deployment = native_node.get("deployment") or {}
        profile = native_node.get("availability_profile") or {}
        replicas = deployment.get("desired_replicas")
        if isinstance(replicas, bool) or not isinstance(replicas, int):
            return {"availability_status": "static_blocked", "runtime_required": True, "reason": "deployment replica fact unavailable; no static prior"}
        if replicas == 1 and not profile.get("pdb"):
            return {"availability_static_prior": True, "runtime_required": True, "availability_status": "static_prior", "reason": "single-replica no-PDB deployment requires runtime availability/recovery validation"}
        return {"availability_static_prior": False, "runtime_required": True, "availability_status": "redundant", "reason": "deployment manifest shows redundancy; runtime oracle remains authoritative"}

    cid = candidate.get("candidate_id", "")
    if not cid:
        return {}
    if fault_of(cid) not in ("kill", "cpu"):
        return {}
    project = project_of(cid, strict=True)
    service_key = normalize_service(cid, strict=True)
    if contract_snapshot is not None:
        contract = _snapshot_contract(contract_snapshot, "availability_hard_filter")
        availability = contract.get("availability") or {}
        avail_profile = availability.get(project) or {}
        profile = avail_profile.get(service_key)
    else:
        from contract_inventory import availability_for_service

        profile = availability_for_service(project, service_key)
    if not profile:
        return {}
    redundant = int(profile.get("replicas", 1)) > 1 or bool(profile.get("pdb"))
    service_name = profile.get("service", service_key)
    if not redundant:
        return {
            "hard_skip": True,
            "availability": True,
            "reason": (
                f"service {service_name} is single-replica no-PDB "
                f"(static manifest): {cid.split('-')[0]} kill/cpu of the only pod = "
                f"total outage, verdict known a priori (AD-REDUNDANCY-001); "
                f"execute only for evidence-chain completeness, not for selection"
            ),
            "evidence": profile.get("static_prediction", "")[:100],
        }
    return {"redundant": True, "reason": f"service {service_name} has redundancy (replicas={profile.get('replicas')})"}


def contract_hard_filter(candidate: dict[str, Any], contract_snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    """Contract inventory as a HARD constraint (not a hint): a delay candidate
    on a source-verified explicit_timeout edge is protected (timeout covers
    delay) and must be skipped before any scoring. Loss faults are NOT
    protected by a timeout. Returns the skip decision or empty dict.

    contract_snapshot=None -> live contract_inventory.json (historical).
    contract_snapshot given -> use ONLY snapshot.contract.{contracts,candidate_map};
    NEVER read the live JSON file.
    """
    if contract_snapshot is not None:
        contract = _snapshot_contract(contract_snapshot, "contract_hard_filter")
        cand_map = contract.get("candidate_map") or {}
        contracts = contract.get("contracts") or {}
    else:
        inv_path = EXPERIMENTS / "contract_inventory.json"
        if not inv_path.exists():
            return {}
        inv = json.loads(inv_path.read_text(encoding="utf-8"))
        cand_map = inv.get("candidate_map", {})
        contracts = inv.get("contracts", {})
    cid = candidate.get("candidate_id", "")
    # Prefer the candidate->contract-edge map (business edge strings like
    # 'frontend->productcatalog' are NOT the contract keys); fall back to the
    # candidate-provided edge only if no map entry exists.
    edge = cand_map.get(cid) or candidate.get("edge")
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
    # Provenance label in the reason: snapshot-injected vs live registry.
    source_label = "knowledge_snapshot.contract" if contract_snapshot is not None else "contract_inventory"
    if contract.get("contract") == "explicit_timeout" and (is_delay or loss_covered):
        return {
            "hard_skip": True,
            "reason": f"edge {edge} is source-verified explicit_timeout; "
                      f"{'delay' if is_delay else 'loss'} is covered by the timeout"
                      f"{' (loss_bounded)' if loss_covered else ''} ({source_label})",
            "evidence": contract.get("evidence", "")[:80],
        }
    return {}


def _score_native_candidate(
    candidate: dict[str, Any],
    knowledge_snapshot: dict[str, Any] | None,
    rca_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score manifest-derived candidates without invoking legacy project rules.

    Native deployment/edge/scenario candidates have no historical project
    prefix.  Knowledge can raise priority or add diagnostics, but this path
    never emits a runtime verdict and never turns static facts into weakness.
    """
    candidate_id = candidate.get("candidate_id") or candidate.get("target")
    target_kind = str(candidate.get("target_kind") or "")
    family = str(candidate.get("fault_family") or "")
    base = float(candidate.get("base_score", BASE))
    score = base
    reasons = [f"native {target_kind} candidate", f"static applicability: {candidate.get('status', 'unknown')}"]
    diagnostics = [
        "confirm namespace-local selector and target readiness",
        "use independent business oracle and recovery evidence",
    ]
    if candidate.get("status") == "blocked":
        reasons.extend(f"blocked: {reason}" for reason in candidate.get("blocked_reasons", []))
        return {
            "candidate_id": candidate_id,
            "edge": candidate.get("edge"),
            "score": -999.0,
            "priority": "static_blocked",
            "reasons": reasons,
            "required_diagnostics": diagnostics,
            "runtime_verdict": None,
        }
    if knowledge_snapshot is not None:
        entries = _snapshot_se(knowledge_snapshot, "_score_native_candidate").get("entries", [])
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if entry.get("fault_family") == family or entry.get("target_kind") == target_kind:
                weight = _se_weight(entry)
                score += weight * 10.0
                reasons.append(f"native knowledge {entry.get('id', '<unknown>')} (w={weight:.2f})")
                diagnostics.extend(str(item) for item in entry.get("diagnostics", []))
    rca = _rca_influence(candidate, rca_snapshot)
    score += rca["bonus"]
    reasons.extend(rca["reasons"])
    diagnostics.extend(rca["diagnostics"])
    return {
        "candidate_id": candidate_id,
        "edge": candidate.get("edge"),
        "score": round(score, 1),
        "priority": "high" if score > base else "normal",
        "reasons": reasons,
        "required_diagnostics": sorted(set(diagnostics)),
        "runtime_verdict": None,
    }


RCA_SNAPSHOT_SCHEMA_VERSION = 1
RCA_REUSABLE_BONUS = 20.0


def _rca_cards(rca_snapshot: dict[str, Any] | None) -> list[dict[str, Any]]:
    if rca_snapshot is None:
        return []
    if rca_snapshot.get("schema_version") != RCA_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("rca_snapshot schema_version must be 1")
    cards = rca_snapshot.get("cards")
    if not isinstance(cards, list):
        raise ValueError("rca_snapshot.cards must be a list")
    return cards


def _rca_card_matches(card: dict[str, Any], candidate: dict[str, Any]) -> bool:
    tn = card.get("test_node") or {}
    card_target = str(card.get("target") or tn.get("target") or "")
    candidate_target = str(candidate.get("target") or candidate.get("service_target") or "")
    if card_target and candidate_target and card_target != candidate_target:
        return False
    edge = str(card.get("edge") or "")
    cid = str(candidate.get("candidate_id") or "").upper()
    family = str(tn.get("family") or "").upper().replace("CHAOS", "")
    operation = str(tn.get("operation") or "").upper()
    candidate_family = str(candidate.get("fault_family") or "").upper().replace("CHAOS", "")
    candidate_operation = str(candidate.get("operation") or candidate.get("fault_family") or "").upper()
    strict_identity = str(card.get("classification") or "") == "availability_weakness" or str(card.get("schema_version") or "").startswith("chaosatlas-weakness-")
    if edge and edge == candidate.get("edge"):
        if not strict_identity:
            return True
        if family and candidate_family and family != candidate_family:
            return False
        if operation and candidate_operation and operation != candidate_operation:
            return False
        return bool(family or operation)
    if strict_identity and family and candidate_family and family != candidate_family:
        return False
    return bool(family and operation and operation in cid and family in cid)


def _rca_influence(candidate: dict[str, Any], rca_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    """Minimal compatible RCA-loop integration (2026-08-20 design, section 10).

    Only knowledge_status=local_reusable cards without a contested flag may
    change scoring; provisional/cross_project_pending cards contribute an
    explanation note only and must not alter hard filters, protected skips or
    the ranking.
    """
    reasons: list[str] = []
    bonus = 0.0
    diagnostics: list[str] = []
    for card in _rca_cards(rca_snapshot):
        if not _rca_card_matches(card, candidate):
            continue
        card_id = card.get("id", "<unknown>")
        status = card.get("knowledge_status")
        if status == "local_reusable" and not card.get("contested"):
            if card.get("closed_boundary"):
                # The runtime line was closed by its guard regression intent
                # (closed_runtime_boundary_no_reinjection): the knowledge is a
                # guard, not a priority boost. Re-injection stays blocked while
                # the next-evidence diagnostics remain retrievable.
                reasons.append(f"RCA {card_id}: local_reusable closed runtime boundary; re-injection guarded (no score change)")
                diagnostics.extend(str(item) for item in card.get("next_evidence", []))
            else:
                bonus += RCA_REUSABLE_BONUS
                reasons.append(f"RCA {card_id}: local_reusable boundary knowledge raises priority")
                diagnostics.extend(str(item) for item in card.get("next_evidence", []))
        elif status == "contested" or card.get("contested"):
            reasons.append(f"RCA {card_id}: contested card ignored as a strong prior")
        else:
            reasons.append(f"RCA {card_id}: {status} card noted for context only (no score change)")
    return {"reasons": reasons, "bonus": bonus, "diagnostics": diagnostics}


def score_candidate(
    candidate: dict[str, Any],
    knowledge_snapshot: dict[str, Any] | None = None,
    rca_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score a candidate from the three libraries (no LLM).

    knowledge_snapshot=None -> historical live behavior.
    knowledge_snapshot given -> pass the SAME snapshot to every downstream
    helper so the engine reads nothing from live files/module registries.
    rca_snapshot (optional) -> local_reusable RCA cards may boost the score;
    provisional/contested cards only add explanation notes.
    """
    if knowledge_snapshot is not None:
        validate_knowledge_snapshot(knowledge_snapshot)
    if str(candidate.get("target_kind") or "") in {"dependency_edge", "deployment", "scenario"}:
        return _score_native_candidate(candidate, knowledge_snapshot, rca_snapshot)
    # Hard constraint 1: availability layer — single-replica no-PDB kill/cpu
    # verdict is known a priori (AD-REDUNDANCY-001), route to availability track.
    avail = availability_hard_filter(candidate, contract_snapshot=knowledge_snapshot)
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
    hard = contract_hard_filter(candidate, contract_snapshot=knowledge_snapshot)
    if hard.get("hard_skip"):
        return {
            "candidate_id": candidate.get("candidate_id"),
            "edge": candidate.get("edge"),
            "score": -999.0,
            "priority": "skip_protected",
            "reasons": [hard["reason"]],
            "hard_skip": True,
        }
    hits = selection_hits(candidate, se_snapshot=knowledge_snapshot)
    base = float(candidate.get("base_score", BASE))
    se_score = sum(weight for _, weight in hits) * 10.0
    downgrade = defense_downgrade(candidate, dp_snapshot=knowledge_snapshot)
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
    hint = judgment_hint(candidate, je_snapshot=knowledge_snapshot)
    if hint:
        if "upgrade" in hint:
            score += 10.0
            priority = "high"
        reasons.append(hint)
    if downgrade.get("execution_override"):
        score += 30.0
        priority = "high"
        reasons.append("execution override: behavior shows weakness")
    rca = _rca_influence(candidate, rca_snapshot)
    if rca["bonus"]:
        score += rca["bonus"]
        priority = "high"
    reasons.extend(rca["reasons"])
    return {
        "candidate_id": candidate.get("candidate_id"),
        "edge": candidate.get("edge"),
        "score": round(score, 1),
        "priority": priority,
        "reasons": reasons,
        "required_diagnostics": rca["diagnostics"],
    }


def rank(
    candidates: list[dict[str, Any]],
    knowledge_snapshot: dict[str, Any] | None = None,
    rca_snapshot: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Rank candidates; when a snapshot is given it is forwarded to EVERY
    score_candidate call so the replay reads nothing from live knowledge."""
    ranked = sorted(
        (
            score_candidate(c, knowledge_snapshot=knowledge_snapshot, rca_snapshot=rca_snapshot)
            for c in candidates
        ),
        key=lambda r: (-r["score"], r["candidate_id"]),
    )
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
