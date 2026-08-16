"""Build a frozen, offline Full/Ablation identity and selection audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.sock_shop_hypothesis_identity import (
    KIND_ALIASES,
    ACTION_ALIASES,
    CALL_CHAIN_ALIASES,
    load_method_records,
    partition_method_sets,
    select_method_representatives,
)


IDENTITY_SCHEMA_VERSION = "sock-shop-hypothesis-identity-v1"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _quantile(values: list[float], quantile: float) -> float:
    if not values:
        return math.inf
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(quantile * len(ordered)) - 1))
    return ordered[index]


def _record_summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "method": record.get("method"),
        "hypothesis_id": (record.get("hypothesis") or {}).get("id"),
        "category": (record.get("hypothesis") or {}).get("category"),
        "target_service": (record.get("hypothesis") or {}).get("target_service"),
        "action_or_target": (record.get("hypothesis") or {}).get("action_or_target"),
        "call_chain_position": (record.get("hypothesis") or {}).get("call_chain_position"),
        "fault_family_key": record.get("fault_family_key"),
        "mutation_instance_key": record.get("mutation_instance_key"),
        "family_size": record.get("family_size"),
        "family_members": record.get("family_members", []),
        "selection_reason": record.get("selection_reason"),
        "confidence_score": record.get("confidence_score"),
        "confidence_source": record.get("confidence_source"),
        "confidence_available": record.get("confidence_available"),
        "structurally_complete": record.get("structurally_complete"),
        "source_order": record.get("source_order"),
        "source_path": record.get("source_path"),
        "mutation_sha256": record.get("mutation_sha256"),
    }


def _selection_entry(
    group: str,
    full: dict[str, Any],
    ablation: dict[str, Any] | None = None,
    *,
    mutation_source: str,
) -> dict[str, Any]:
    source = full if ablation is None else full
    ablation_only = mutation_source == "ablation" and ablation is None
    return {
        "group": group,
        "full_hypothesis_id": None if ablation_only else (full.get("hypothesis") or {}).get("id"),
        "ablation_hypothesis_id": (
            (full.get("hypothesis") or {}).get("id")
            if ablation_only
            else (ablation or {}).get("hypothesis", {}).get("id") if ablation else None
        ),
        "fault_family_key": full.get("fault_family_key"),
        "mutation_instance_key": full.get("mutation_instance_key"),
        "mutation_source": mutation_source,
        "mutation_path": source.get("source_path"),
        "mutation_sha256": source.get("mutation_sha256"),
        "full_confidence_score": None if ablation_only else full.get("confidence_score"),
        "full_confidence_source": None if ablation_only else full.get("confidence_source"),
        "full_selection_reason": None if ablation_only else full.get("selection_reason"),
        "ablation_selection_reason": (
            full.get("selection_reason") if ablation_only else (ablation or {}).get("selection_reason") if ablation else None
        ),
        "full_record": None if ablation_only else _record_summary(full),
        "ablation_record": _record_summary(full) if ablation_only else _record_summary(ablation) if ablation else None,
    }


def select_matched_full_only(
    full_only: list[dict[str, Any]],
    ablation_only: list[dict[str, Any]],
    *,
    threshold: float,
    sample_seed: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    eligible = [
        record for record in full_only
        if record.get("confidence_score") is not None and float(record["confidence_score"]) >= threshold
    ]
    eligible.sort(key=lambda record: (-float(record["confidence_score"]), record["mutation_instance_key"]))
    random_source = sorted(ablation_only, key=lambda record: record["mutation_instance_key"])
    matched_size = min(len(eligible), len(random_source))
    full_selected = eligible[:matched_size]
    rng = random.Random(sample_seed)
    ablation_selected = rng.sample(random_source, matched_size)
    return full_selected, ablation_selected, {
        "full_high_confidence_candidates": len(eligible),
        "ablation_only_candidates": len(random_source),
        "matched_sample_size": matched_size,
    }


def build_identity_audit(
    full_discovery_path: Path,
    ablation_discovery_path: Path,
    full_runtime_plan_path: Path,
    ablation_runtime_plan_path: Path,
    *,
    output_dir: Path,
    sample_seed: int = 20260815,
    high_confidence_quantile: float = 0.75,
) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty output directory: {output_dir}")
    if not 0.0 < high_confidence_quantile <= 1.0:
        raise ValueError("high_confidence_quantile must be in (0, 1]")
    output_dir.mkdir(parents=True, exist_ok=True)

    full_input = load_method_records(full_discovery_path, full_runtime_plan_path, method="native-full")
    ablation_input = load_method_records(
        ablation_discovery_path,
        ablation_runtime_plan_path,
        method="chaosatlas-ablation",
    )
    full_representatives = select_method_representatives(full_input["records"], method="native-full")
    ablation_representatives = select_method_representatives(
        ablation_input["records"], method="chaosatlas-ablation"
    )
    partition = partition_method_sets(full_representatives, ablation_representatives)

    confidence_values = [
        float(record["confidence_score"])
        for record in full_representatives
        if record.get("confidence_score") is not None
    ]
    threshold = _quantile(confidence_values, high_confidence_quantile)
    overlap_high = [
        item for item in partition["strict_overlap"]
        if (item["full"].get("confidence_score") is not None and item["full"]["confidence_score"] >= threshold)
    ]
    full_only_high, ablation_only_sample, matching = select_matched_full_only(
        partition["full_only"],
        partition["ablation_only"],
        threshold=threshold,
        sample_seed=sample_seed,
    )
    sample_size = matching["matched_sample_size"]

    normalization_config = {
        "schema_version": IDENTITY_SCHEMA_VERSION,
        "family_fields": ["kind", "normalized_action", "target_service", "call_chain_position"],
        "instance_fields": ["family_key", "normalized_parameters"],
        "kind_aliases": dict(sorted(KIND_ALIASES.items())),
        "action_aliases": dict(sorted(ACTION_ALIASES.items())),
        "call_chain_aliases": dict(sorted(CALL_CHAIN_ALIASES.items())),
        "metadata_excluded_from_parameters": ["metadata.name", "metadata.namespace"],
    }
    config_hash = _sha256_bytes(_canonical_json(normalization_config))
    _write_json(output_dir / "identity_config.json", {**normalization_config, "sha256": config_hash})

    old_new_audit = {
        "schema_version": IDENTITY_SCHEMA_VERSION,
        "normalization_config_sha256": config_hash,
        "methods": {
            "native-full": {
                "discovery_path": str(full_discovery_path),
                "discovery_sha256": _sha256_file(full_discovery_path),
                "runtime_plan_path": str(full_runtime_plan_path),
                "runtime_plan_sha256": _sha256_file(full_runtime_plan_path),
                "discovery_status": full_input.get("discovery_status"),
                "raw_runtime_candidates": len(full_input["records"]),
                "blocked_runtime_candidates": len(full_input.get("blocked_candidates", [])),
                "representative_family_count": len(full_representatives),
                "ignored_unreferenced_mutation_files": full_input["ignored_mutation_files"],
                "representatives": [_record_summary(record) for record in full_representatives],
            },
            "chaosatlas-ablation": {
                "discovery_path": str(ablation_discovery_path),
                "discovery_sha256": _sha256_file(ablation_discovery_path),
                "runtime_plan_path": str(ablation_runtime_plan_path),
                "runtime_plan_sha256": _sha256_file(ablation_runtime_plan_path),
                "discovery_status": ablation_input.get("discovery_status"),
                "raw_runtime_candidates": len(ablation_input["records"]),
                "blocked_runtime_candidates": len(ablation_input.get("blocked_candidates", [])),
                "representative_family_count": len(ablation_representatives),
                "ignored_unreferenced_mutation_files": ablation_input["ignored_mutation_files"],
                "representatives": [_record_summary(record) for record in ablation_representatives],
            },
        },
        "selection_note": "Full representatives use explicit confidence or stop-posterior complement; Ablation representatives never use confidence or runtime outcomes.",
    }
    _write_json(output_dir / "old_new_key_audit.json", old_new_audit)

    overlap_audit = {
        "normalization_config_sha256": config_hash,
        "family_overlap": [
            {"fault_family_key": item["fault_family_key"], "full": _record_summary(item["full"]), "ablation": _record_summary(item["ablation"])}
            for item in partition["family_overlap"]
        ],
        "strict_overlap": [
            {"mutation_instance_key": item["mutation_instance_key"], "full": _record_summary(item["full"]), "ablation": _record_summary(item["ablation"])}
            for item in partition["strict_overlap"]
        ],
        "full_only": [_record_summary(record) for record in partition["full_only"]],
        "ablation_only": [_record_summary(record) for record in partition["ablation_only"]],
    }
    _write_json(output_dir / "overlap_audit.json", overlap_audit)

    groups = {
        "overlap_high_confidence": [
            _selection_entry(
                "overlap_high_confidence",
                item["full"],
                item["ablation"],
                mutation_source="full",
            )
            for item in overlap_high
        ],
        "full_only_high_confidence": [
            _selection_entry(
                "full_only_high_confidence",
                record,
                mutation_source="full",
            )
            for record in full_only_high
        ],
        "ablation_only_random": [
            _selection_entry(
                "ablation_only_random",
                record,
                mutation_source="ablation",
            )
            for record in ablation_only_sample
        ],
    }
    selection = {
        "schema_version": "sock-shop-r5-dedup-selection-v1",
        "human_review": "pending",
        "knowledge_base_updated": False,
        "normalization_config_sha256": config_hash,
        "config": {
            "sample_seed": sample_seed,
            "high_confidence_quantile": high_confidence_quantile,
            "high_confidence_threshold": None if math.isinf(threshold) else round(threshold, 6),
            "ablation_only_sample_size": sample_size,
            "full_high_confidence_candidates_before_matching": matching["full_high_confidence_candidates"],
            "ablation_only_candidates_before_sampling": matching["ablation_only_candidates"],
            "matched_sample_size": matching["matched_sample_size"],
            "runtime_replicates": 2,
            "prior_runtime_roots": [],
        },
        "groups": groups,
        "gate_blocked_not_resampled": {
            "native_full": len(full_input.get("blocked_candidates", [])),
            "ablation": len(ablation_input.get("blocked_candidates", [])),
        },
    }
    selection_bytes = _canonical_json(selection)
    selection["selection_content_sha256"] = _sha256_bytes(selection_bytes)
    _write_json(output_dir / "selection_manifest.json", selection)
    selection_file_sha256 = _sha256_file(output_dir / "selection_manifest.json")
    (output_dir / "selection_manifest.sha256").write_text(
        selection_file_sha256 + "  selection_manifest.json\n",
        encoding="utf-8",
    )

    summary = {
        "schema_version": IDENTITY_SCHEMA_VERSION,
        "human_review": "pending",
        "knowledge_base_updated": False,
        "normalization_config_sha256": config_hash,
        "sets": {
            "full_family_count": len(full_representatives),
            "ablation_family_count": len(ablation_representatives),
            "family_overlap_count": len(partition["family_overlap"]),
            "strict_overlap_count": len(partition["strict_overlap"]),
            "full_only_count": len(partition["full_only"]),
            "ablation_only_count": len(partition["ablation_only"]),
        },
        "selection_counts": {name: len(items) for name, items in groups.items()},
        "confidence": {
            "threshold": None if math.isinf(threshold) else round(threshold, 6),
            "quantile": high_confidence_quantile,
            "full_sources": sorted({record.get("confidence_source") for record in full_representatives}),
        },
    }
    _write_json(output_dir / "audit_summary.json", summary)
    (output_dir / "README.md").write_text(
        "# Sock Shop R5 identity audit\n\n"
        "Offline-only audit. No Full runtime was rerun and no knowledge-base update was performed.\n"
        "The four old stratified Ablation reports are excluded from this manifest.\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full-discovery", type=Path, required=True)
    parser.add_argument("--ablation-discovery", type=Path, required=True)
    parser.add_argument("--full-runtime-plan", type=Path, required=True)
    parser.add_argument("--ablation-runtime-plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample-seed", type=int, default=20260815)
    parser.add_argument("--high-confidence-quantile", type=float, default=0.75)
    args = parser.parse_args()
    summary = build_identity_audit(
        args.full_discovery,
        args.ablation_discovery,
        args.full_runtime_plan,
        args.ablation_runtime_plan,
        output_dir=args.output,
        sample_seed=args.sample_seed,
        high_confidence_quantile=args.high_confidence_quantile,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
