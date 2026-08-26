"""Orchestration helpers for explicit, conflict-safe defense promotion."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from tools.defense_knowledge import promote_repeated_defense


REQUIRED_RUN_ARTIFACTS = (
    "run_manifest.json",
    "classify.json",
    "observe.json",
    "cleanup_report.json",
)


def select_history_children(root: Path) -> dict[str, Any]:
    """Select only immediate, complete run directories below an explicit root."""

    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError(f"defense history root must be a real directory: {root}")
    selected: list[Path] = []
    rejected: list[dict[str, str]] = []
    for child in sorted(root.iterdir(), key=lambda path: path.name):
        if child.is_symlink() or not child.is_dir():
            rejected.append({"path": child.name, "reason": "not_directory"})
            continue
        if not all((child / name).is_file() for name in REQUIRED_RUN_ARTIFACTS):
            rejected.append({"path": child.name, "reason": "missing_required_artifacts"})
            continue
        selected.append(child)
    return {"selected": selected, "rejected": rejected}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


def _stage_payload(*, status: str, selected: list[Path], rejected: list[dict[str, str]], **extra: Any) -> dict[str, Any]:
    return {
        "schema_version": "chaosatlas-defense-promotion-stage-v1",
        "status": status,
        "selected_runs": [path.name for path in selected],
        "rejected_inputs": rejected,
        **extra,
    }


def promote_from_history(
    *,
    history_root: Path,
    output_root: Path,
    knowledge_write_root: Path | None = None,
) -> dict[str, Any]:
    """Promote only explicitly selected history runs and record the result."""

    selection = select_history_children(Path(history_root))
    selected = list(selection["selected"])
    rejected = list(selection["rejected"])
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    if len(selected) < 2:
        payload = _stage_payload(
            status="not_run",
            selected=selected,
            rejected=rejected,
            reason="fewer_than_two_complete_runs",
        )
        write_json(output_root / "knowledge_promotion.json", payload)
        return payload

    promotion_artifacts = output_root / "promotion_artifacts"
    try:
        result = promote_repeated_defense(run_roots=selected, output_root=promotion_artifacts)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        payload = _stage_payload(
            status="contested",
            selected=selected,
            rejected=rejected,
            reason=str(exc),
            guard_intents=[],
        )
        existing_card = (
            Path(knowledge_write_root) / "defense_card.json"
            if knowledge_write_root is not None
            else None
        )
        if existing_card is not None and existing_card.is_file():
            conflict = record_promotion_conflict(
                old_card=existing_card,
                run_root=selected[-1],
                reason=str(exc),
                output_root=output_root,
            )
            payload.update(
                {
                    "old_snapshot_sha256": conflict["old_snapshot_sha256"],
                    "reusable_card_preserved": True,
                    "run_fingerprint": conflict["run_fingerprint"],
                }
            )
        write_json(output_root / "knowledge_conflict.json", payload)
        write_json(output_root / "knowledge_promotion.json", payload)
        return payload

    payload = _stage_payload(
        status="promoted",
        selected=selected,
        rejected=rejected,
        knowledge_status=result.get("knowledge_status"),
        classification=result.get("classification"),
        defense_claim_type=result.get("defense_claim_type"),
        card_id=result.get("id"),
        run_ids=result.get("valid_reproductions"),
        regression=result.get("regression"),
    )
    write_json(output_root / "knowledge_promotion.json", payload)
    if knowledge_write_root is not None:
        destination = Path(knowledge_write_root)
        destination.mkdir(parents=True, exist_ok=True)
        for artifact in promotion_artifacts.glob("*.json"):
            shutil.copyfile(artifact, destination / artifact.name)
    return {"status": "promoted", **result, "stage": payload}


def record_promotion_conflict(
    *,
    old_card: Path,
    run_root: Path,
    reason: str,
    output_root: Path,
) -> dict[str, Any]:
    """Record a counterexample without modifying the existing knowledge card."""

    old_card = Path(old_card)
    payload = {
        "schema_version": "chaosatlas-defense-conflict-v1",
        "status": "contested",
        "reason": str(reason),
        "old_card": str(old_card),
        "old_snapshot_sha256": sha256_file(old_card),
        "run_root": str(Path(run_root)),
        "run_fingerprint": sha256_file(Path(run_root) / "classify.json") if (Path(run_root) / "classify.json").is_file() else None,
        "guard_intents": [],
        "reusable_card_preserved": True,
    }
    write_json(Path(output_root) / "knowledge_conflict.json", payload)
    return payload
