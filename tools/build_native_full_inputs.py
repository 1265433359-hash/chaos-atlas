"""Build fresh native-project knowledge inputs without projection or runtime feedback."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEEDS = (1001, 1002, 1003)
METHOD_ID = "ChaosAtlas-native-full"


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _display_path(path: Path) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(resolved).replace("\\", "/")


def build_native_knowledge_view(project_id: str, knowledge_root: Path) -> dict[str, Any]:
    """Embed the frozen project KB cards as a prompt input, preserving provenance."""
    knowledge_root = Path(knowledge_root)
    index_path = knowledge_root / "index.json"
    index = _load_json(index_path)
    cards: list[dict[str, Any]] = []
    for entry in index.get("cards", []):
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ValueError(f"invalid knowledge index card entry: {entry}")
        card_path = knowledge_root / entry["path"]
        card = _load_json(card_path)
        cards.append(
            {
                "id": card.get("id", entry.get("id")),
                "path": entry["path"],
                "sha256": hashlib.sha256(card_path.read_bytes()).hexdigest(),
                "content": card,
            }
        )
    view = {
        "schema_version": "chaosatlas-native-project-knowledge-v1",
        "project_id": project_id,
        "source_index_sha256": hashlib.sha256(index_path.read_bytes()).hexdigest(),
        "source_index": index,
        "cards": cards,
        "projection_used": False,
        "pollution_intentionally_not_excluded": True,
        "human_review": "pending",
        "knowledge_base_updated": False,
    }
    return view


def write_native_bundle_root(
    *,
    project_id: str,
    common_inputs: dict[int, dict[str, Any]],
    native_knowledge: dict[str, Any],
    output_root: Path,
    seeds: Iterable[int] = DEFAULT_SEEDS,
) -> dict[str, Any]:
    output_root = Path(output_root)
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"refusing non-empty directory: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    selected_seeds = tuple(seeds)
    if not selected_seeds:
        raise ValueError("at least one seed is required")
    if native_knowledge.get("projection_used") is not False:
        raise ValueError("native knowledge must not use a projection")

    snapshot_dir = output_root / "knowledge_snapshots" / project_id
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshot_dir / "native-knowledge.json"
    snapshot_path.write_text(json.dumps(native_knowledge, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    records: list[dict[str, Any]] = []
    for seed in selected_seeds:
        common = common_inputs.get(seed)
        if not isinstance(common, dict):
            raise ValueError(f"missing common input for seed {seed}")
        bundle = {
            "schema_version": "chaosatlas-native-full-input-v1",
            "project_id": project_id,
            "seed": seed,
            "method_id": METHOD_ID,
            "common_input": common,
            "common_input_sha256": canonical_sha256(common),
            "knowledge_view": native_knowledge,
            "projection_used": False,
            "pollution_intentionally_not_excluded": True,
            "human_review": "pending",
            "knowledge_base_updated": False,
        }
        seed_dir = output_root / "input_bundles" / project_id / f"seed-{seed}"
        seed_dir.mkdir(parents=True, exist_ok=True)
        (seed_dir / "common.json").write_text(json.dumps(common, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        bundle_path = seed_dir / "chaosatlas-native-full.json"
        bundle_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        (seed_dir / "chaosatlas-native-full.prompt.txt").write_text(
            "ChaosAtlas native-full discovery input. Return JSON only. Use the supplied "
            "frozen topology, business oracle, and native project knowledge. Do not "
            "invent runtime observations or executable commands.\n\n"
            + json.dumps(bundle, indent=2, ensure_ascii=True)
            + "\n",
            encoding="utf-8",
        )
        records.append(
            {
                "seed": seed,
                "bundle": _display_path(bundle_path),
                "bundle_sha256": hashlib.sha256(bundle_path.read_bytes()).hexdigest(),
                "common_input_sha256": bundle["common_input_sha256"],
            }
        )

    manifest = {
        "schema_version": "chaosatlas-native-full-input-manifest-v1",
        "project_id": project_id,
        "method": METHOD_ID,
        "seeds": list(selected_seeds),
        "knowledge_snapshot": _display_path(snapshot_path),
        "knowledge_snapshot_sha256": hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),
        "projection_used": False,
        "pollution_intentionally_not_excluded": True,
        "human_review": "pending",
        "model_calls": False,
        "runtime_started": False,
        "knowledge_base_updated": False,
        "records": records,
    }
    (output_root / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--common-root", type=Path, required=True)
    parser.add_argument("--knowledge-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, action="append")
    args = parser.parse_args()
    seeds = tuple(args.seed or DEFAULT_SEEDS)
    common_inputs = {
        seed: _load_json(args.common_root / f"seed-{seed}" / "common.json")
        for seed in seeds
    }
    result = write_native_bundle_root(
        project_id=args.project_id,
        common_inputs=common_inputs,
        native_knowledge=build_native_knowledge_view(args.project_id, args.knowledge_root),
        output_root=args.output,
        seeds=seeds,
    )
    print(json.dumps({"status": "completed", "project_id": args.project_id, "seeds": result["seeds"]}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
