"""P0: knowledge_updater - closed-loop evidence backfill with audit log.

The first gear of the learning loop (knowledge_closed_loop.md). New experiment
evidence flows back into the three knowledge libraries automatically:

- SE-* (selection experience): which candidate families are worth testing
- JE-* (judgment experience): what a symptom means
- DP-* (defense patterns): what mechanisms absorbed faults

Backfill rules are EXPLICIT heuristic matches (candidate edge/fault/project ->
entry), auditable, and never force an unlinked evidence into an entry. Every
change (enhance) is recorded in an audit log with timestamp, source, entry id,
and what changed. Confidence upgrades: >=3 corroborating cases -> high.

This makes the library 'learn' from every new experiment instead of being a
static seed. It does NOT auto-delete or auto-rewrite rules (that is P1
counter-example handling, which must be human-adjudicated).
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXECUTION_DIR = ROOT / "artifacts" / "experiments" / "execution"
SE_PATH = ROOT / "artifacts" / "experiments" / "selection_experience.json"
JE_PATH = ROOT / "artifacts" / "experiments" / "judgment_experience.json"
DP_PATH = ROOT / "artifacts" / "experiments" / "defense_pattern_library.json"
AUDIT_PATH = ROOT / "artifacts" / "experiments" / "knowledge_audit_log.json"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save(doc: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def load_audit() -> list[dict[str, Any]]:
    if AUDIT_PATH.exists():
        doc = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
        return doc.get("entries", [])
    return []


def append_audit(entries: list[dict[str, Any]]) -> None:
    log = load_audit()
    log.extend(entries)
    save({"schema_version": 1, "tool": "knowledge_audit_log", "entries": log}, AUDIT_PATH)


def evidence_from_candidate(cid: str, severity: int, verdict: str, contract: str | None) -> dict[str, Any]:
    """Normalize a candidate's executed outcome into backfill evidence."""
    cid_upper = cid.upper()
    project = "OB" if cid_upper.startswith("OB-") else ("OTEL" if cid_upper.startswith("OTEL-") else "TT")
    fault = "loss" if "LOSS" in cid_upper else ("kill" if "KILL" in cid_upper else "delay")
    service = cid_upper.replace(f"{project}-", "", 1).split("-DELAY")[0].split("-LOSS")[0].split("-KILL")[0].split("-CPU")[0]
    return {
        "candidate_id": cid,
        "project": project,
        "service": service,
        "fault": fault,
        "severity": severity,
        "verdict": verdict,
        "contract": contract,
    }


def match_selection(ev: dict[str, Any]) -> list[tuple[str, str]]:
    """Return (entry_id, reason) pairs this evidence supports (SE library)."""
    hits: list[tuple[str, str]] = []
    if ev["fault"] in ("delay", "loss") or ev["service"] in ("PAYMENT", "CART", "CHECKOUT", "ORDER"):
        hits.append(("SE-NETWORK-FAMILY-001", "network-fault weakness"))
    if ev["fault"] == "loss":
        hits.append(("SE-LOSS-STRONGEST-001", "loss weakness"))
    if ev["service"] in ("PAYMENT", "CART", "CHECKOUT"):
        hits.append(("SE-CORE-CHAIN-001", "core-chain weakness"))
    if ev["service"] in ("EMAIL",):
        hits.append(("SE-SIDEEFFECT-COUPLING-001", "side-effect coupling weakness"))
    return hits


def match_judgment(ev: dict[str, Any]) -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []
    if ev["service"] in ("EMAIL",):
        hits.append(("JE-COUPLING-001", "coupling weakness"))
    if ev["verdict"] == "weakness" and ev["fault"] in ("delay", "loss"):
        hits.append(("JE-CONTRACT-001", "no-timeout weakness"))
    return hits


def _entry_by_id(doc: dict[str, Any], entry_id: str, key: str) -> dict[str, Any] | None:
    for entry in doc.get("entries", []):
        if entry.get(key) == entry_id:
            return entry
    return None


def enhance_entry(entry: dict[str, Any], evidence_label: str, field: str, audit: list[dict[str, Any]], source: str) -> bool:
    """Append evidence (dedup) and bump evidence_count. Returns True if changed."""
    cases = entry.setdefault(field, [])
    if any(evidence_label in str(c) for c in cases):
        return False  # already present; not a new learning event
    cases.append(evidence_label)
    entry["evidence_count"] = int(entry.get("evidence_count", 0)) + 1
    # simple confidence state machine: >=3 corroborating cases -> high
    if entry["evidence_count"] >= 3 and entry.get("confidence") in ("medium", "low"):
        audit.append({
            "at": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "entry_id": entry.get("id") or entry.get("pattern_id"),
            "change": "confidence_upgrade",
            "from": entry["confidence"],
            "to": "high",
            "reason": f"evidence_count reached {entry['evidence_count']}",
        })
        entry["confidence"] = "high"
    return True


def backfill(candidate_ids: list[str] | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Backfill executed candidate outcomes into SE/JE (+DP). Returns change report.

    P1: below_threshold evidence that CONTRADICTS a rule's predicted weakness
    is recorded as a counter-example on the matched entry and marks it
    'contested' (human-adjudicated later) — never silently rewritten.
    """
    se = load(SE_PATH)
    je = load(JE_PATH)
    dp = load(DP_PATH)

    # Source of truth: candidate evidence status (severity + verdict).
    ev_doc = json.loads((EXECUTION_DIR / "candidate_evidence_status.json").read_text(encoding="utf-8"))
    from compare_selection_methods import SEVERITY

    audit: list[dict[str, Any]] = []
    linked: list[str] = []
    unlinked: list[str] = []
    counter_examples: list[dict[str, Any]] = []

    for item in ev_doc.get("candidates", []):
        cid = item["candidate_id"]
        if candidate_ids and cid not in candidate_ids:
            continue
        conclusions = item.get("own_conclusions") or []
        if not conclusions:
            continue
        severity = SEVERITY.get(cid, 1)
        verdict = "weakness" if severity >= 2 else "below_threshold"
        ev = evidence_from_candidate(cid, severity, verdict, None)
        label = f"{cid} ({ev['fault']} sev{severity})"

        matched_any = False
        # P1: only a STRONG injection that stayed at 1:1 (no amplification) is a
        # genuine counter-example. Weak injections (100ms / CPU) that don't
        # break are measurement-blind-spot (A1), not contradictions.
        strong_below = verdict == "below_threshold" and ("500" in cid or "2000" in cid)
        for entry_id, reason in match_selection(ev):
            entry = _entry_by_id(se, entry_id, "id")
            if not entry:
                continue
            if strong_below:
                counter = entry.setdefault("counter_examples", [])
                if label not in counter:
                    counter.append(label)
                    entry.setdefault("contested", True)
                    entry["contested_reason"] = (
                        f"strong injection stayed 1:1 no-amplification ({label}), contradicting "
                        "the rule's implied 'delay on this family amplifies'; human adjudication required"
                    )
                    counter_examples.append({"entry_id": entry_id, "candidate": label, "reason": reason})
                    audit.append({
                        "at": datetime.now(timezone.utc).isoformat(),
                        "source": f"counterexample::{cid}",
                        "entry_id": entry_id,
                        "change": "contested",
                        "evidence": label,
                        "reason": reason,
                    })
                    matched_any = True
                continue
            if verdict == "below_threshold":
                # weak injection: record as boundary note on counter_examples, no contest.
                counter = entry.setdefault("counter_examples", [])
                if label not in counter:
                    counter.append(label)
                continue
            changed = enhance_entry(entry, label, "experiment_evidence", audit, f"selection_experience::{cid}")
            if changed:
                audit.append({"at": datetime.now(timezone.utc).isoformat(), "source": f"selection_experience::{cid}",
                              "entry_id": entry_id, "change": "evidence_added", "evidence": label, "reason": reason})
            matched_any = matched_any or changed
        for entry_id, reason in match_judgment(ev):
            entry = _entry_by_id(je, entry_id, "id")
            if entry:
                changed = enhance_entry(entry, label, "evidence_cases", audit, f"judgment_experience::{cid}")
                if changed:
                    audit.append({"at": datetime.now(timezone.utc).isoformat(), "source": f"judgment_experience::{cid}",
                                  "entry_id": entry_id, "change": "evidence_added", "evidence": label, "reason": reason})
                matched_any = matched_any or changed

        if matched_any:
            linked.append(cid)
        else:
            unlinked.append(cid)

    if dry_run:
        return {"dry_run": True, "linked": linked, "unlinked": unlinked, "counter_examples": counter_examples, "audit_entries": len(audit)}

    save(se, SE_PATH)
    save(je, JE_PATH)
    append_audit(audit)
    return {"linked": linked, "unlinked": unlinked, "counter_examples": counter_examples, "audit_entries": len(audit), "patterns_unchanged": len(dp.get("patterns", []))}


def adjudicate(entry_id: str, decision: str, note: str = "") -> dict[str, Any]:
    """P1: human adjudication of a contested rule.

    accept: the counter-example is real — keep the contest, demote confidence,
            and append the adjudication note (rule needs revision).
    reject: the counter-example is noise — clear the contest marker.
    Either way, the action is recorded in the audit log.
    """
    if decision not in ("accept", "reject"):
        raise SystemExit(f"--decision must be accept or reject, got {decision}")
    se = load(SE_PATH)
    entry = _entry_by_id(se, entry_id, "id")
    if not entry:
        raise SystemExit(f"entry not found in selection_experience: {entry_id}")
    audit: list[dict[str, Any]] = []
    if decision == "accept":
        entry["contested"] = True
        entry["adjudicated"] = "accepted"
        entry["adjudication_note"] = note or "counter-example accepted; rule requires revision"
        if entry.get("confidence") == "high":
            audit.append({
                "at": datetime.now(timezone.utc).isoformat(), "source": "adjudication",
                "entry_id": entry_id, "change": "confidence_demote", "from": "high", "to": "medium",
                "reason": f"accepted counter-example ({note or 'revise rule'})",
            })
            entry["confidence"] = "medium"
    else:
        entry["contested"] = False
        entry["contested_reason"] = ""
        entry["adjudicated"] = "rejected"
        entry["adjudication_note"] = note or "counter-example rejected as noise"
    audit.append({
        "at": datetime.now(timezone.utc).isoformat(), "source": "adjudication",
        "entry_id": entry_id, "change": f"adjudicated_{decision}", "note": note,
    })
    save(se, SE_PATH)
    append_audit(audit)
    return {"entry_id": entry_id, "decision": decision, "audit_entries": len(audit)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", nargs="+", default=None, help="limit backfill to these candidate ids")
    parser.add_argument("--dry-run", action="store_true", help="report what would change without writing")
    parser.add_argument("--adjudicate", default=None, help="entry id to adjudicate (P1)")
    parser.add_argument("--decision", choices=("accept", "reject"), default=None, help="adjudication decision")
    parser.add_argument("--note", default="", help="adjudication note")
    args = parser.parse_args()
    if args.adjudicate:
        report = adjudicate(args.adjudicate, args.decision or "reject", args.note)
    else:
        report = backfill(args.candidates, dry_run=args.dry_run)
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
