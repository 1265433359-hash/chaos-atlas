"""Fail-closed checks for the ChaosAtlas paired and cross-project protocols.

This validator is offline-only. It checks frozen input artifacts and feedback
metadata before any model call or runtime mutation is allowed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from tools.contamination_audit import audit_repository
    from tools.feedback_protocol import validate_ablation_pair, validate_knowledge_card_boundary
except ModuleNotFoundError:
    from contamination_audit import audit_repository
    from feedback_protocol import validate_ablation_pair, validate_knowledge_card_boundary


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "artifacts/experiments/chaosatlas_10_projects"
PROJECT_ORDER = [f"P{i:02d}" for i in range(1, 11)]


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def validate_inputs(root: Path = EXPERIMENT) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    checked_pairs = 0
    # The formal ablation applies to the open-discovery bundles. The legacy
    # fixed-pool input_bundles have a different schema and are validated by
    # protocol-v1 gates.
    bundles = root / "open_discovery_bundles"
    for project_dir in sorted(bundles.glob("P*")):
        for seed_dir in sorted(project_dir.glob("seed-*")):
            kb_path = seed_dir / "chaosatlas-kb-open.json"
            nokb_path = seed_dir / "chaosatlas-nokb-open.json"
            if not kb_path.exists() or not nokb_path.exists():
                continue
            result = validate_ablation_pair(load(kb_path), load(nokb_path))
            nokb_prompt = seed_dir / "chaosatlas-nokb-open.prompt.txt"
            if nokb_prompt.exists():
                prompt_text = nokb_prompt.read_text(encoding="utf-8-sig").lower()
                for marker in ("knowledge view", "knowledge_card", "knowledge_cards/"):
                    if marker in prompt_text:
                        result["errors"].append(f"nokb_prompt_leak:{marker}")
                        result["valid"] = False
            checked_pairs += 1
            if not result["valid"]:
                errors.append({"scope": str(kb_path), "errors": result["errors"]})
    contamination = audit_repository(root)
    if contamination["status"] != "pass":
        errors.append({"scope": "contamination_audit", "errors": sorted({error for record in contamination["records"] for error in record.get("errors", [])})})
    return {"valid": not errors, "checked_ablation_pairs": checked_pairs, "errors": errors, "contamination_audit": contamination}


def validate_feedback_manifest(manifest: dict[str, Any], common_input: dict[str, Any] | None = None) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    order = manifest.get("project_order")
    if order != PROJECT_ORDER:
        errors.append({"reason": "project_order_must_be_preregistered", "actual": order})
    current = manifest.get("target_project")
    if current not in PROJECT_ORDER:
        errors.append({"reason": "unknown_target_project", "target_project": current})
    for card in manifest.get("cards", []):
        source = card.get("project_id")
        if source not in PROJECT_ORDER:
            errors.append({"card_id": card.get("card_id"), "reason": "unknown_source_project"})
            continue
        if current and PROJECT_ORDER.index(source) >= PROJECT_ORDER.index(current):
            errors.append({"card_id": card.get("card_id"), "reason": "future_or_same_project_feedback"})
        if card.get("source_round_id") != manifest.get("round_id"):
            errors.append({"card_id": card.get("card_id"), "reason": "round_mismatch"})
        boundary = validate_knowledge_card_boundary(card, common_input)
        if not boundary["valid"]:
            errors.append({"card_id": card.get("card_id"), "reason": "knowledge_boundary_failed", "errors": boundary["errors"]})
    return {"valid": not errors, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=EXPERIMENT)
    args = parser.parse_args()
    result = validate_inputs(args.root)
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
