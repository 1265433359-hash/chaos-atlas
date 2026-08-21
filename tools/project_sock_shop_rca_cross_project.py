"""Project the reviewed sock-shop RCA card into the Online Boutique KB.

Executes the human review decision (human_review_decision.json) through the
existing feedback protocol:

1. fail-closed unless the decision authorizes cross-project projection;
2. rebuild the evidence claim from the archived r4-final artifacts and
   re-verify it programmatically (AllInjected, outage sample, cleanup,
   counterfactual co-proof) instead of trusting filenames;
3. require classify_outcome == confirmed_weakness (>=2 reproductions, full
   evidence chain) before a feedback card may exist;
4. build the human_reviewed audit card, then build_next_kb() so only the
   reviewed abstraction enters the later-project KB snapshot;
5. re-check the projection for forbidden fields/markers and write the
   provisional-prior annotation. No formal KB file is modified.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from feedback_protocol import (  # noqa: E402
    FORBIDDEN_KB_MARKERS,
    build_feedback_card,
    build_next_kb,
    classify_outcome,
    validate_knowledge_card_boundary,
)

REPO = Path(__file__).resolve().parents[1]
ROUND_ROOT = REPO / "artifacts/sock-shop/rca_loop/runtime-live-r4-final"
SOURCE_PROJECT = "sock-shop"
TARGET_PROJECT = "online-boutique"
PROJECT_ORDER = [SOURCE_PROJECT, TARGET_PROJECT]
DECISION_APPROVED = "approved_local_reuse_with_cross_project_projection"

ABSTRACTION = {
    "weakness_family": "pod-kill",
    "target_role": "single-replica deployment",
    "applicability": "single-replica deployment without a pod disruption budget under kill or cpu fault families",
    "expected_effect": "full outage window until a replacement pod becomes Ready and enters Service endpoints",
    "early_success_samples_are_not_defense": "an HTTP success during the kill window can be an observation-window artifact when no ready endpoint exists",
    "verification_recipe": "scale the deployment to two replicas, repeat the same kill, and require a surviving Ready pod UID in Service endpoints serving the business oracle",
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _condition(status: bool, message: str) -> None:
    if not status:
        raise ValueError(f"evidence condition failed: {message}")


def verify_decision(round_root: Path) -> dict[str, Any]:
    decision = _load(round_root / "human_review_decision.json")
    if decision.get("decision") != DECISION_APPROVED:
        raise ValueError(f"decision '{decision.get('decision')}' does not authorize cross-project projection")
    card = _load(round_root / "knowledge_drafts" / "KB-RCA-sock-shop-front-end-podchaos-pod-kill.json")
    if card.get("knowledge_status") != "local_reusable":
        raise ValueError("source card is not local_reusable")
    return decision


def build_verified_result(round_root: Path) -> dict[str, Any]:
    evidence_dir = round_root / "evidence"
    r2 = _load(evidence_dir / "disambiguation-r2/result.json")
    r4 = _load(evidence_dir / "redundancy-r1/result.json")
    timeline = [
        json.loads(line)
        for line in (evidence_dir / "disambiguation-r2/timeline.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    # Re-verify the chain the review approved, from the artifacts themselves.
    conditions = r2["injection_status"]["status"]["conditions"]
    _condition(any(c["type"] == "AllInjected" and c["status"] == "True" for c in conditions), "r2 AllInjected")
    _condition(any((p.get("business") or {}).get("status_code") is None for p in timeline), "r2 outage sample")
    _condition(not r2.get("residual_podchaos") and not r4.get("residual_podchaos"), "cleanup residue empty")
    r4_summary = r4.get("summary") or {}
    _condition(r4_summary.get("classification") == "defended" and int(r4_summary.get("defended_sample_count", 0)) >= 1,
               "r4 counterfactual co-proof")
    _condition((r4.get("restored_replicas") == r4.get("original_replicas")), "replicas restored")

    return {
        "project_id": SOURCE_PROJECT,
        "project_commit": "sock-shop-fixture-commit",
        "round_id": "pilot-r4-redundancy-r1",
        "canonical_signature": "sock-shop:front-end:PodChaos:pod-kill:single-replica-no-pdb",
        "target": "sock-shop-lab/deployment/front-end",
        "target_kind": "deployment",
        "fault_family": "pod-kill",
        "oracle_label": "weakness",
        "availability_label": "availability_degraded",
        "valid_reproductions": 2,
        "evidence": {
            "baseline": {"status": "pass", "source": "evidence/redundancy-r1/before.json"},
            "injection": {"status": "confirmed", "source": "evidence/disambiguation-r2/result.json#injection_status"},
            "observation": {"status": "confirmed", "source": "evidence/disambiguation-r2/timeline.jsonl"},
            "recovery": {"status": "confirmed", "source": "evidence/pods-recovery.json"},
            "cleanup": {"status": "pass", "source": "evidence/disambiguation-r2/result.json#residual_podchaos"},
            "independent_oracle": {"status": "confirmed", "source": "evidence/redundancy-r1/result.json"},
        },
        "abstraction": dict(ABSTRACTION),
        "reviewer": "project-owner",
    }


def project(round_root: Path) -> dict[str, Any]:
    decision = verify_decision(round_root)
    result = build_verified_result(round_root)
    classification = classify_outcome(result)
    if classification != "confirmed_weakness":
        raise ValueError(f"classify_outcome returned '{classification}'; refusing to project")
    card = build_feedback_card(result, review_status="human_reviewed")
    boundary = validate_knowledge_card_boundary(card)
    if not boundary["valid"]:
        raise ValueError(f"knowledge boundary failed: {boundary['errors']}")
    kb = build_next_kb(
        {"kb_version": "v1", "cards": []},
        [card],
        current_project=TARGET_PROJECT,
        target_projects=[TARGET_PROJECT],
        round_id=card["source_round_id"],
        project_order=PROJECT_ORDER,
    )
    accepted_ids = [c["card_id"] for c in kb["cards"]]
    if accepted_ids != [card["card_id"]]:
        raise ValueError(f"projection rejected by build_next_kb: {kb['provenance']['rejected']}")
    for projected in kb["cards"]:
        leaked = sorted(set(projected).intersection({"evidence", "target", "classification"}))
        if leaked:
            raise ValueError(f"projected card leaked forbidden fields: {leaked}")
        for value in json.dumps(projected).lower().split('"'):
            if any(marker in value for marker in FORBIDDEN_KB_MARKERS):
                raise ValueError(f"projected card contains forbidden marker text: {value[:60]}")
    return {
        "schema_version": 1,
        "tool": "project_sock_shop_rca_cross_project",
        "decision": decision,
        "classification": classification,
        "feedback_card": card,
        "kb_projection": kb,
        "projection_mode": "provisional_prior_pending_target_project_validation",
        "target_project": TARGET_PROJECT,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round-root", type=Path, default=ROUND_ROOT)
    parser.add_argument("--output-dir", type=Path,
                        default=REPO / "artifacts/sock-shop/rca_loop/cross-project-r1")
    args = parser.parse_args()
    report = project(args.round_root)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "feedback_card.json").write_text(json.dumps(report["feedback_card"], indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "kb_projection.json").write_text(json.dumps(report["kb_projection"], indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "projection_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    card = report["feedback_card"]
    print(f"card={card['card_id']} classification={report['classification']} "
          f"target={report['target_project']} mode={report['projection_mode']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
