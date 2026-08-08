"""P3: issue_tracker - external-feedback loop state machine.

Closes the 'external ground truth' loop (knowledge_closed_loop.md cycle 3):
a discovery becomes a submittable issue; once submitted, the upstream
maintainer's response (confirmed / rejected / no response) flows back into
the knowledge libraries:

- confirmed  -> the underlying finding's evidence is externally validated;
                bump confidence to high and add an external-confirmation
                marker to the audit log (and to matching SE/JE entries).
- rejected   -> the finding was wrong (or the upstream disagrees); mark the
                underlying knowledge contested for human adjudication.
- no_response-> recorded honestly; no confidence change (cannot claim
                external acceptance without it).

This tool tracks state only; the actual `gh issue create` call is a separate
outward-facing action that stays gated on explicit user approval.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / "artifacts" / "experiments"
TRACKER_PATH = EXPERIMENTS / "issue_tracker.json"
AUDIT_PATH = EXPERIMENTS / "knowledge_audit_log.json"
SE_PATH = EXPERIMENTS / "selection_experience.json"
JE_PATH = EXPERIMENTS / "judgment_experience.json"

DEFAULT_ISSUES: list[dict[str, Any]] = [
    {
        "issue_id": "ISSUE-001",
        "repo": "open-telemetry/opentelemetry-demo",
        "title": "quoteShipping reports 'failed POST to email service' when the failing call is to the shipping service (copy-paste error)",
        "draft_path": "reporting/opentelemetry-demo/issues/2026-08-09_quote-shipping-error-message.md",
        "finding_candidate": None,  # source-code bug, not an experiment candidate
        "supported_by": ["KB-OTEL-CHECKOUT-EMAIL-FAILURE-001", "OTEL-SHIPPING-DELAY-2000"],
        "status": "ready",
        "status_updated_at": None,
        "url": None,
        "external_response": None,
    },
    {
        "issue_id": "ISSUE-002",
        "repo": "FudanSELab/train-ticket",
        "title": "queryOrdersForRefresh disables its only downstream call (queryForStationId) in both order services",
        "draft_path": "reporting/train-ticket/issues/2026-08-05_disabled-downstream-call-in-refresh.md",
        "finding_candidate": None,
        "supported_by": ["TT-ORDER-DELAY-2000"],
        "status": "ready",
        "status_updated_at": None,
        "url": None,
        "external_response": None,
    },
]


def load(path: Path = TRACKER_PATH) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"schema_version": 1, "tool": "issue_tracker", "issues": []}


def save(doc: dict[str, Any], path: Path = TRACKER_PATH) -> None:
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def append_audit(entry: dict[str, Any]) -> None:
    if AUDIT_PATH.exists():
        log = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    else:
        log = {"schema_version": 1, "entries": []}
    log.setdefault("entries", []).append(entry)
    AUDIT_PATH.write_text(json.dumps(log, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def init(path: Path = TRACKER_PATH) -> dict[str, Any]:
    """Initialize the tracker. DEFAULT_ISSUES is the authoritative definition;
    existing entries keep their static fields (title/draft_path/supported_by)
    but runtime state (status/url/external_response) is reset to ready — init
    means 'start from a clean state', so a prior test/run that marked issues
    submitted must not leak into the next initialization."""
    doc = load(path)
    existing = {i["issue_id"]: i for i in doc.get("issues", [])}
    for issue in DEFAULT_ISSUES:
        prev = existing.get(issue["issue_id"], {})
        merged = {**issue}
        for field in ("title", "draft_path", "supported_by", "repo"):
            if field in prev:
                merged[field] = prev[field]
        # runtime state always resets on init
        merged["status"] = "ready"
        merged["url"] = None
        merged["external_response"] = None
        merged["status_updated_at"] = None
        existing[issue["issue_id"]] = merged
    doc["issues"] = [existing[iid] for iid in sorted(existing)]
    save(doc, path)
    return doc


def set_submitted(issue_id: str, url: str, path: Path = TRACKER_PATH) -> dict[str, Any]:
    doc = load(path)
    for issue in doc["issues"]:
        if issue["issue_id"] == issue_id:
            issue["status"] = "submitted"
            issue["url"] = url
            issue["status_updated_at"] = datetime.now(timezone.utc).isoformat()
            append_audit({
                "at": datetime.now(timezone.utc).isoformat(),
                "source": f"issue_tracker::{issue_id}",
                "entry_id": issue_id,
                "change": "submitted",
                "url": url,
                "note": "external submission recorded; upstream response pending",
            })
    save(doc, path)
    return doc


def record_response(issue_id: str, response: str, note: str = "", path: Path = TRACKER_PATH) -> dict[str, Any]:
    """response: confirmed | rejected | no_response. Reflows into knowledge."""
    if response not in ("confirmed", "rejected", "no_response"):
        raise SystemExit("--response must be confirmed | rejected | no_response")
    doc = load(path)
    target = next((i for i in doc["issues"] if i["issue_id"] == issue_id), None)
    if not target:
        raise SystemExit(f"issue not found: {issue_id}")
    target["external_response"] = response
    target["status_updated_at"] = datetime.now(timezone.utc).isoformat()
    append_audit({
        "at": datetime.now(timezone.utc).isoformat(),
        "source": f"issue_tracker::{issue_id}",
        "entry_id": issue_id,
        "change": f"external_{response}",
        "note": note or f"upstream responded: {response}",
    })
    # Reflow into knowledge confidence.
    if response == "confirmed":
        _reflow_confirmed(target)
    elif response == "rejected":
        _reflow_rejected(target)
    save(doc, path)
    return doc


def _reflow_confirmed(issue: dict[str, Any]) -> None:
    """External confirmation is the strongest evidence: bump matching entries
    in SE and JE and persist them."""
    supported = issue.get("supported_by", [])
    for path in (SE_PATH, JE_PATH):
        if not path.exists():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for entry in doc.get("entries", []):
            cited = [str(c) for c in entry.get("experiment_evidence", []) + entry.get("evidence_cases", [])]
            if not any(cand in " ".join(cited) for cand in supported):
                continue
            # external confirmation marker is UNCONDITIONAL (strongest evidence
            # tier) - independent of confidence, which may already be high from
            # internal evidence.
            confirmed_by = entry.setdefault("external_confirmation", [])
            if issue["issue_id"] not in confirmed_by:
                confirmed_by.append(issue["issue_id"])
                changed = True
            if entry.get("confidence") != "high":
                append_audit({
                    "at": datetime.now(timezone.utc).isoformat(),
                    "source": f"issue_tracker::{issue['issue_id']}",
                    "entry_id": entry.get("id") or entry.get("pattern_id"),
                    "change": "confidence_upgrade_external",
                    "from": entry.get("confidence"),
                    "to": "high",
                    "note": "upstream confirmed a finding this entry's evidence cites",
                })
                entry["confidence"] = "high"
        if changed:
            path.write_text(json.dumps(doc, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _reflow_rejected(issue: dict[str, Any]) -> None:
    supported = issue.get("supported_by", [])
    for path in (SE_PATH, JE_PATH):
        if not path.exists():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for entry in doc.get("entries", []):
            cited = [str(c) for c in entry.get("experiment_evidence", []) + entry.get("evidence_cases", [])]
            if not any(cand in " ".join(cited) for cand in supported):
                continue
            entry["contested"] = True
            entry["contested_reason"] = (
                f"upstream rejected finding {issue['issue_id']} citing supported evidence; "
                "revalidate before trusting this rule"
            )
            append_audit({
                "at": datetime.now(timezone.utc).isoformat(),
                "source": f"issue_tracker::{issue['issue_id']}",
                "entry_id": entry.get("id") or entry.get("pattern_id"),
                "change": "contested_external",
                "note": "upstream rejection flowed back as contested",
            })
            changed = True
        if changed:
            path.write_text(json.dumps(doc, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--init", action="store_true", help="initialize tracker with the two ready issues")
    parser.add_argument("--list", action="store_true", help="show tracker state")
    parser.add_argument("--mark-submitted", default=None, help="issue id + --url")
    parser.add_argument("--url", default=None)
    parser.add_argument("--respond", default=None, help="issue id + --response")
    parser.add_argument("--response", choices=("confirmed", "rejected", "no_response"), default=None)
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    if args.init:
        doc = init()
        print(json.dumps({"issues": [i["issue_id"] + ":" + i["status"] for i in doc["issues"]]}, indent=2))
        return 0
    if args.list:
        doc = load()
        for i in doc["issues"]:
            print(f"{i['issue_id']}: [{i['status']}] {i['title'][:70]} url={i.get('url')} response={i.get('external_response')}")
        return 0
    if args.mark_submitted:
        if not args.url:
            raise SystemExit("--url is required for --mark-submitted")
        doc = set_submitted(args.mark_submitted, args.url)
        print(json.dumps({"issue": args.mark_submitted, "status": "submitted"}, indent=2))
        return 0
    if args.respond:
        doc = record_response(args.respond, args.response or "no_response", args.note)
        print(json.dumps({"issue": args.respond, "response": args.response, "reflowed": True}, indent=2))
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
