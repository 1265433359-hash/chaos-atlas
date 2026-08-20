"""Compile RCA cases into provisional knowledge drafts and regression intents.

Offline projection only: drafts live under the RCA loop artifact root and are
never written into a formal knowledge base. Cross-project reuse continues to go
through the existing feedback protocol. No cluster, container, LLM or network
access happens here.

Usage:
    python tools/compile_rca_regression.py --rca-root artifacts/sock-shop/rca_loop \
        --output artifacts/sock-shop/rca_loop/knowledge_drafts
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.rca_loop import _contains_sensitive_value, evidence_polarity_counts, sha256_json

DEFAULT_STOP_RULE = "stop after two valid reproductions or one clean falsification"
GUARD_STOP_RULE = "guard: closed_runtime_boundary_no_reinjection"

_APPLICABILITY_BY_FAMILY = {
    "single_replica_podkill": [
        "single-replica deployment without pod disruption budget",
        "kill or cpu fault families",
    ],
    "catalogue_db_podkill": [
        "stateful dependency with a single instance",
        "business path crossing the dependency boundary",
    ],
    "http_abort_propagation": [
        "abort or loss fault families on a measured service edge",
        "real business path crossing the same edge",
    ],
}


def project_knowledge_draft(
    case: dict[str, Any],
    hypotheses: list[dict[str, Any]],
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Project one RCA case into a knowledge-card draft without secrets."""

    evidence_refs = case.get("evidence_refs", [])
    counts = evidence_polarity_counts(evidence_refs)
    top_hypothesis = hypotheses[0] if hypotheses else {}
    selected = None
    for entry in actions or []:
        plan = entry if entry.get("status") == "planned" else None
        if plan:
            selected = plan.get("selected") or {}
    next_evidence = sorted(
        {
            claim
            for hypothesis in hypotheses
            for claim in hypothesis.get("unsupported_claims", [])
        }
    ) or [str(selected.get("output_schema") or "next_bounded_evidence")]

    promotion = case.get("knowledge_promotion_audit")
    if isinstance(promotion, dict) and promotion.get("next_status") == "local_reusable" and promotion.get("allowed"):
        knowledge_status = "local_reusable"
    elif case.get("knowledge_status") == "contested":
        knowledge_status = "contested"
    else:
        knowledge_status = "provisional"

    edge = case.get("test_node", {}).get("target_role", "")
    draft = {
        "schema_version": "chaosatlas-rca-knowledge-draft-v1",
        "id": "KB-RCA-" + str(case.get("weakness_id", "unknown")).removeprefix("WS-"),
        "version": 1,
        "status": knowledge_status,
        "evidence_state": {
            "supports": counts["supports"],
            "contradicts": counts["contradicts"],
            "unavailable": counts["unavailable"],
            "neutral": counts["neutral"],
        },
        "project": case.get("project_id"),
        "project_commit": case.get("project_commit"),
        "round_id": case.get("round_id"),
        "weakness_id": case.get("weakness_id"),
        "case_family": case.get("case_family"),
        "weakness_status": case.get("weakness_status"),
        "rca_status": case.get("rca_status"),
        "knowledge_status": knowledge_status,
        "mechanism_claim": top_hypothesis.get("claim"),
        "mechanism_level": top_hypothesis.get("mechanism_level", "service_boundary"),
        "test_node": dict(case.get("test_node", {})),
        "test_node_centered_graph": {
            "edge": edge,
            "scope": top_hypothesis.get("scope", {}),
        },
        "four_layer_validation": {
            "availability": case.get("case_family") == "single_replica_podkill",
            "contract": case.get("case_family") == "http_abort_propagation",
            "business_path": counts["supports"] > 0,
            "recovery": any(
                ev.get("polarity") == "supports" and "recover" in str(ev.get("interpretation", "")).lower()
                for ev in evidence_refs
            ),
        },
        "applicability_conditions": _APPLICABILITY_BY_FAMILY.get(
            case.get("case_family"), ["same project and commit"]
        ),
        "exclusion_conditions": [
            "cross_project_transfer_requires_existing_feedback_protocol",
            "must_not_be_promoted_to_timeout_mechanism_without_source_evidence",
        ],
        "counter_evidence": sorted(
            {
                ev_id
                for hypothesis in hypotheses
                for ev_id in hypothesis.get("evidence_against", [])
            }
        ),
        "evidence_refs": [
            {
                "evidence_id": ev.get("evidence_id"),
                "kind": ev.get("kind"),
                "polarity": ev.get("polarity"),
                "source_ref": ev.get("source_ref"),
            }
            for ev in evidence_refs
        ],
        "regression_recipe": {
            "oracle": case.get("symptom", {}).get("oracle"),
            "selected_next_action": selected.get("action_id") if selected else None,
        },
        "next_evidence": next_evidence,
        "regression_intents": [],
        "stop_rule": DEFAULT_STOP_RULE,
    }
    if _contains_sensitive_value(json.dumps(draft, ensure_ascii=True)):
        raise ValueError(f"refusing to project card {draft['id']} with sensitive values")
    return draft


def _intent(
    *,
    kind: str,
    card: dict[str, Any],
    snapshot_sha256: str,
    required_evidence: list[str],
    stop_rule: str,
) -> dict[str, Any]:
    oracle = (
        (card.get("regression_recipe") or {}).get("oracle")
        or card.get("oracle")
        or "project business oracle"
    )
    return {
        "kind": kind,
        "source_card_id": card.get("id"),
        "weakness_id": card.get("weakness_id"),
        "snapshot_sha256": snapshot_sha256,
        "oracle": oracle,
        "required_evidence": required_evidence,
        "stop_rule": stop_rule,
        "applicability_conditions": list(card.get("applicability_conditions", [])),
    }


def compile_regression_intents(
    cards: list[dict[str, Any]],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Compile eligible cards into bounded next-round regression intents."""

    snapshot_sha256 = sha256_json(snapshot)
    intents: list[dict[str, Any]] = []
    rejected_cards: list[str] = []
    for card in cards:
        status = card.get("knowledge_status")
        required = list(card.get("next_evidence") or []) or [
            "business_oracle_reproduction",
            "recovery_after_fault_removal",
        ]
        stop_rule = str(card.get("stop_rule") or DEFAULT_STOP_RULE)
        if status == "contested":
            rejected_cards.append(str(card.get("id")))
            continue
        if status == "local_reusable":
            intents.append(
                _intent(
                    kind="reproduce",
                    card=card,
                    snapshot_sha256=snapshot_sha256,
                    required_evidence=required,
                    stop_rule=stop_rule,
                )
            )
            intents.append(
                _intent(
                    kind="guard",
                    card=card,
                    snapshot_sha256=snapshot_sha256,
                    required_evidence=required,
                    stop_rule=f"{GUARD_STOP_RULE}; {stop_rule}",
                )
            )
        elif status == "provisional":
            # provisional knowledge may only plan evidence work, never reuse
            if card.get("rca_status") == "confirmed" and not required_is_discriminating(required):
                kind = "reproduce"
            else:
                kind = "discriminate"
            intents.append(
                _intent(
                    kind=kind,
                    card=card,
                    snapshot_sha256=snapshot_sha256,
                    required_evidence=required,
                    stop_rule=stop_rule,
                )
            )
        else:
            rejected_cards.append(str(card.get("id")))
    return {
        "schema_version": "chaosatlas-rca-regression-intents-v1",
        "snapshot_sha256": snapshot_sha256,
        "intents": intents,
        "rejected_cards": rejected_cards,
    }


def required_is_discriminating(required: list[str]) -> bool:
    return not required or all("reproduc" in item.lower() for item in required)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rca-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    rca_root: Path = args.rca_root
    output: Path = args.output
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output {output} already exists and is not empty; refusing to overwrite")

    drafts = []
    for path in sorted((rca_root / "cases").glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        drafts.append(project_knowledge_draft(case, case.get("hypotheses", []), case.get("next_actions", [])))
    if not drafts:
        raise ValueError(f"no RCA cases found under {rca_root / 'cases'}")

    for draft in drafts:
        text = json.dumps(draft, indent=2, ensure_ascii=True) + "\n"
        if _contains_sensitive_value(text):
            raise ValueError(f"refusing to write sensitive values into {draft['id']}")
        output.mkdir(parents=True, exist_ok=True)
        (output / f"{draft['id']}.json").write_text(text, encoding="utf-8")

    compiled = compile_regression_intents(drafts, snapshot={"cards": drafts})
    output.mkdir(parents=True, exist_ok=True)
    (output / "regression_intents.json").write_text(
        json.dumps(compiled, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(drafts)} knowledge drafts and {len(compiled['intents'])} regression intents to {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
