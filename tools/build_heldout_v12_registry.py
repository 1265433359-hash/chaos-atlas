#!/usr/bin/env python3
"""Freeze the pooled v1.2 candidate registry without result-derived filtering."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List


PROJECTS = ("HOTEL", "SOCIALNET", "TEASTORE")
CLASSES = ("protected", "unprotected", "unknown")
REQUIRED_FIELDS = {
    "candidate_id",
    "project_id",
    "fault_family",
    "protection_class",
    "yaml_path",
    "yaml_sha256",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_pool(root: Path, project: str) -> tuple[Path, Dict[str, Any]]:
    path = root / f"{project.lower()}_candidate_pool_formal.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("candidates"), list):
        raise ValueError(f"invalid candidate pool schema: {path}")
    return path, payload


def freeze(root: Path, protocol_json: Path, protocol_md: Path) -> tuple[Dict[str, Any], Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    source_pools: List[Dict[str, Any]] = []
    seen = set()
    per_project: Dict[str, Dict[str, int]] = {}

    for project in PROJECTS:
        path, payload = load_pool(root, project)
        rows = payload["candidates"]
        counts = Counter()
        for candidate in rows:
            missing = REQUIRED_FIELDS - set(candidate)
            if missing:
                raise ValueError(f"{project}: missing fields {sorted(missing)}")
            if candidate["project_id"] != project:
                raise ValueError(f"{project}: project_id mismatch for {candidate['candidate_id']}")
            if candidate["protection_class"] not in CLASSES:
                raise ValueError(f"{project}: invalid protection class")
            if candidate["candidate_id"] in seen:
                raise ValueError(f"duplicate candidate_id: {candidate['candidate_id']}")
            seen.add(candidate["candidate_id"])
            counts[candidate["protection_class"]] += 1
            candidates.append(candidate)
        per_project[project] = {
            **{name: counts[name] for name in CLASSES},
            "legal_total": len(rows),
        }
        source_pools.append(
            {
                "project_id": project,
                "path": str(path).replace("\\", "/"),
                "sha256": sha256(path),
                "source_status": payload.get("status"),
                "candidate_count": len(rows),
            }
        )

    pooled_counts = Counter(candidate["protection_class"] for candidate in candidates)
    pooled = {name: pooled_counts[name] for name in CLASSES}
    pooled["legal_total"] = len(candidates)
    thresholds = {"protected": 16, "unprotected": 16, "unknown": 16, "legal_total": 48}
    pooled_gate = {name: pooled[name] >= minimum for name, minimum in thresholds.items()}
    project_minimums_pass = all(row["legal_total"] >= 8 for row in per_project.values())
    class_project_support = {
        name: sum(row[name] > 0 for row in per_project.values()) for name in CLASSES
    }
    registry = {
        "schema_version": 1,
        "protocol": "heldout_protocol_v1_2",
        "status": "frozen",
        "frozen_at": "2026-08-10",
        "generation_rule": "pooled_static_registry_v1; concatenation of pre-frozen project pools; no result-derived filtering",
        "source_pools": source_pools,
        "projects": list(PROJECTS),
        "per_project_counts": per_project,
        "pooled_counts": pooled,
        "thresholds": thresholds,
        "pooled_gate": pooled_gate,
        "project_minimum_legal": 8,
        "project_minimums_pass": project_minimums_pass,
        "class_project_support": class_project_support,
        "descriptive_only_classes": [
            name for name, count in class_project_support.items() if count < 2
        ],
        "candidate_ids_unique": len(seen) == len(candidates),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "execution_started": False,
        "note": "This v1.2 registry is separate from v1.1 per-project qualification and does not authorize deployment by itself.",
    }
    return registry, {
        "schema_version": 1,
        "protocol": "heldout_protocol_v1_2",
        "status": "frozen",
        "frozen_at": "2026-08-10",
        "protocol_json_sha256": sha256(protocol_json),
        "protocol_md_sha256": sha256(protocol_md),
        "source_pools": source_pools,
        "candidate_count": len(candidates),
        "candidate_ids_sha256": hashlib.sha256(
            "\n".join(sorted(seen)).encode("utf-8")
        ).hexdigest(),
        "pooled_counts": pooled,
        "pooled_gate": pooled_gate,
        "project_minimums_pass": project_minimums_pass,
        "descriptive_only_classes": [
            name for name, count in class_project_support.items() if count < 2
        ],
        "execution_started": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("artifacts/experiments/heldout"))
    parser.add_argument(
        "--protocol-json",
        type=Path,
        default=Path("artifacts/experiments/heldout/heldout_protocol_v1_2.json"),
    )
    parser.add_argument(
        "--protocol-md",
        type=Path,
        default=Path("artifacts/experiments/heldout/heldout_protocol_v1_2.md"),
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("artifacts/experiments/heldout/heldout_v12_candidate_registry.json"),
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=Path("artifacts/experiments/heldout/heldout_v12_freeze_snapshot.json"),
    )
    args = parser.parse_args()
    registry, snapshot = freeze(args.root, args.protocol_json, args.protocol_md)
    args.registry.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    snapshot["registry_sha256"] = sha256(args.registry)
    args.snapshot.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(snapshot, indent=2))
    return 0 if registry["candidate_ids_unique"] and all(registry["pooled_gate"].values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
