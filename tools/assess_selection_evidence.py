"""Map every shared-pool candidate to its runtime evidence status.

For each of the 12 core candidates, scan the execution artifacts for any run
that used that candidate's mutation path, then attach the runtime conclusion
(classification + root cause from knowledge cards). This is the evidence
backbone for an honest U@N comparison: only candidates with a completed
runtime conclusion can be judged as "discovery hit / miss"; everything else
must stay "not_executed" and never be counted as either.

Reads only committed artifacts; performs no injection.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from generate_deep_comparison_matrix import CORE_CANDIDATES

ROOT = Path(__file__).resolve().parents[1]
EXECUTION_DIR = ROOT / "artifacts" / "experiments" / "execution"
KNOWLEDGE_ROOTS = {
    "train-ticket": ROOT / "artifacts" / "train-ticket" / "knowledge_base",
    "online-boutique": ROOT / "artifacts" / "online-boutique" / "knowledge_base",
    "otel-demo": ROOT / "artifacts" / "opentelemetry-demo" / "knowledge_base",
}


def normalize(path: str) -> str:
    return path.replace("\\", "/")


def collect_mutation_uses() -> dict[str, list[str]]:
    """Map normalized mutation path -> list of run/classification artifacts."""
    uses: dict[str, list[str]] = {}
    pattern = re.compile(r"(run|report|confirmation|track|smoke|stat|m1_batch).*\.json$", re.IGNORECASE)
    for path in EXECUTION_DIR.glob("*.json"):
        if not pattern.search(path.name):
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        candidates = []
        if isinstance(doc, dict):
            mutation = doc.get("mutation")
            if mutation:
                candidates.append(mutation)
            if doc.get("tool") in ("classify_runtime_result",):
                for ref in doc.get("evidence_refs") or []:
                    candidates.append(ref)
        for mutation in candidates:
            uses.setdefault(normalize(str(mutation)), []).append(path.name)
    return uses


def load_card_conclusions() -> dict[str, dict[str, Any]]:
    """Map candidate-relevant root causes by matching card test_node to candidate."""
    conclusions: dict[str, dict[str, Any]] = {}
    for project, root in KNOWLEDGE_ROOTS.items():
        index_path = root / "index.json"
        if not index_path.exists():
            continue
        index = json.loads(index_path.read_text(encoding="utf-8"))
        for entry in index.get("cards", []):
            card_path = root / str(entry.get("path", ""))
            if not card_path.exists():
                continue
            try:
                card = json.loads(card_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            node = card.get("test_node") or {}
            selector = node.get("selector") or {}
            label = ((selector.get("label") or {}).get("app"))
            runtime = card.get("runtime_result") or {}
            summary = {
                "card_id": card.get("id"),
                "evidence_state": card.get("evidence_state"),
                "classification": runtime.get("classification"),
                "root_cause": card.get("root_cause"),
                "status": card.get("status"),
                "outcome": runtime.get("outcome"),
            }
            conclusions.setdefault(str(label), []).append(summary)
    return conclusions


def match_candidate_mutation(candidate: dict[str, Any], uses: dict[str, list[str]]) -> dict[str, Any]:
    target = normalize(str(candidate.get("mutation", "")))
    hits = uses.get(target, [])
    return {
        "candidate_id": candidate["candidate_id"],
        "mutation": target,
        "execution_records": sorted(hits),
        "executed": bool(hits),
    }


def evidence_status(candidate: dict[str, Any], card_by_label: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    label = str(candidate.get("service", ""))
    cards = card_by_label.get(label, [])
    conclusions = [c for c in cards if c.get("evidence_state") == "runtime_observed"]
    return {
        "candidate_id": candidate["candidate_id"],
        "service": label,
        "cards": conclusions,
        "discovery_evidence": bool(conclusions),
    }


def assess(replicate: int) -> dict[str, Any]:
    uses = collect_mutation_uses()
    card_by_label = load_card_conclusions()
    candidates: list[dict[str, Any]] = []
    for candidate in CORE_CANDIDATES:
        mutation_info = match_candidate_mutation(candidate, uses)
        evidence = evidence_status(candidate, card_by_label)
        # A candidate's own discovery evidence requires ITS mutation to have
        # been executed with a concluded classification. Same-service cards
        # without that candidate's mutation are inherited references only.
        target = normalize(str(candidate.get("mutation", "")))
        own_conclusions: list[dict[str, Any]] = []
        for use_file in uses.get(target, []):
            try:
                doc = json.loads((EXECUTION_DIR / use_file).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            # gRPC runner reports carry result_classification; offline
            # classifier outputs carry classification. Both are conclusions
            # bound to this candidate's own mutation.
            classification = doc.get("result_classification") or doc.get("classification")
            if classification:
                own_conclusions.append({"file": use_file, "classification": str(classification)})
        candidates.append(
            {
                **mutation_info,
                **evidence,
                "own_conclusions": own_conclusions,
                "own_discovery_evidence": bool(own_conclusions),
            }
        )
    return {
        "schema_version": 1,
        "tool": "assess_selection_evidence",
        "assessed_at": datetime.now(timezone.utc).isoformat(),
        "replicate": replicate,
        "candidates": candidates,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Candidate evidence status (ground-truth backbone)", ""]
    lines.append("Only candidates whose OWN mutation was executed with a concluded classification count toward discovery.")
    lines.append("Same-service card conclusions without that candidate's mutation are inherited references, not candidate evidence.")
    lines.append("Not-executed candidates are reported as `not_executed` and never counted as hit or miss.")
    lines.append("")
    lines.append("| Candidate | Executed | Own discovery conclusion | Same-service card root cause |")
    lines.append("|---|---|---|---|")
    for item in report["candidates"]:
        card = item["cards"][0] if item["cards"] else {}
        executed = "yes" if item["executed"] else "no"
        own = item["own_conclusions"][0]["classification"] if item["own_conclusions"] else "not_executed"
        root = card.get("root_cause") or "-"
        lines.append(
            f"| {item['candidate_id']} | {executed} | {own} | {root} |"
        )
    discovered = [
        item for item in report["candidates"] if item["own_discovery_evidence"]
    ]
    not_executed = [item for item in report["candidates"] if not item["executed"]]
    lines.append("")
    lines.append(f"Candidates with own discovery evidence: {len(discovered)}")
    lines.append(f"Not executed: {len(not_executed)} ({', '.join(i['candidate_id'] for i in not_executed)})")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replicate", type=int, default=1)
    parser.add_argument("--output-json", type=Path, default=EXECUTION_DIR / "candidate_evidence_status.json")
    parser.add_argument("--output-md", type=Path, default=EXECUTION_DIR / "candidate_evidence_status.md")
    args = parser.parse_args()
    report = assess(args.replicate)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    args.output_md.write_text(render_markdown(report), encoding="utf-8")
    print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
