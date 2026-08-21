"""Build the Online Boutique rca_snapshot from the validated cross-project prior.

Bridge between the cross-project projection (sock-shop -> Online Boutique)
and the decision engine's rca_snapshot format. Fail-closed rules:

- the OB validation verdict must be ``prior_validated`` (human-review
  decision + two-arm live validation), otherwise nothing is projected;
- only the reviewed abstraction fields are exposed (no sock-shop runtime
  evidence, no OB runtime samples beyond the validation verdict summary);
- the card keeps full provenance: source card, projection, validation run.

Engine semantics: knowledge_status maps to ``local_reusable`` (validated on
this project) WITHOUT closed_boundary — the OB line is not closed, matching
candidates get the reusable-knowledge priority treatment only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
CROSS_PROJECT_DIR = REPO / "artifacts/sock-shop/rca_loop/cross-project-r1"


def _load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc


def build_snapshot(cross_project_dir: Path) -> dict[str, Any]:
    decision = _load(cross_project_dir / "ob_validation_decision.json")
    if decision.get("verdict") != "prior_validated":
        raise ValueError(f"OB validation verdict '{decision.get('verdict')}' does not allow retrieval projection")
    projection = _load(cross_project_dir / "kb_projection.json")
    cards = projection.get("cards") or []
    if len(cards) != 1:
        raise ValueError(f"expected exactly one projected card, found {len(cards)}")
    projected = cards[0]
    abstraction = projected.get("abstraction") or {}
    if "applicability" not in abstraction or "expected_effect" not in abstraction:
        raise ValueError("projected abstraction lost its applicability/expected_effect fields")

    card = {
        "id": projected["card_id"],
        "knowledge_status": "local_reusable",
        "contested": False,
        "closed_boundary": False,
        "weakness_id": None,
        "project": "online-boutique",
        "edge": None,
        "test_node": {"family": "PodChaos", "operation": "pod-kill", "target_role": "single-replica deployment"},
        "mechanism_claim": f"{abstraction['applicability']}: {abstraction['expected_effect']}",
        "applicability_conditions": [abstraction["applicability"]],
        "stop_rule": None,
        "next_evidence": ["ob single-replica kill/cpu candidates carry the observation-window-artifact caveat"],
        "source": {
            "source_card": decision.get("source_card"),
            "cross_project_dir": str(cross_project_dir),
            "validation_run": decision.get("validation_run"),
            "validation_verdict": decision.get("verdict"),
        },
    }
    return {
        "schema_version": 1,
        "tool": "build_ob_rca_snapshot",
        "project": "online-boutique",
        "cards": [card],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cross-project-dir", type=Path, default=CROSS_PROJECT_DIR)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    snapshot = build_snapshot(args.cross_project_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    for card in snapshot["cards"]:
        print(f"{card['id']}: status={card['knowledge_status']} closed_boundary={card['closed_boundary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
