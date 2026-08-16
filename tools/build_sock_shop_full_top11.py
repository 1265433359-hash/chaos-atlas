"""Freeze the actual confidence-ranked Full Top 11 before runtime evidence lookup."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _resolve(path: str) -> Path:
    value = Path(path)
    if value.is_file():
        return value
    candidate = ROOT / value
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _executable_key(instance_key: str) -> str:
    return re.sub(r"\|call_chain_position=[^|]*", "", instance_key)


def _full_representatives(audit: dict[str, Any]) -> list[dict[str, Any]]:
    records = [dict(item) for item in audit.get("full_only") or []]
    records.extend(dict(item["full"]) for item in audit.get("family_overlap") or [])
    by_family = {}
    for record in records:
        family = str(record.get("fault_family_key") or "")
        if not family:
            raise ValueError(f"missing fault_family_key: {record.get('hypothesis_id')}")
        if family in by_family:
            raise ValueError(f"duplicate Full family representative: {family}")
        by_family[family] = record
    return list(by_family.values())


def build_full_top11_manifest(
    overlap_audit_path: Path,
    output_dir: Path,
    *,
    limit: int = 11,
) -> dict[str, Any]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty output directory: {output_dir}")

    audit_bytes = overlap_audit_path.read_bytes()
    audit = json.loads(audit_bytes.decode("utf-8"))
    normalization_sha = str(audit.get("normalization_config_sha256") or "")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", normalization_sha):
        raise ValueError("normalization_config_sha256 must be a 64-character SHA-256")
    records = _full_representatives(audit)
    if len(records) < limit:
        raise ValueError(f"Full representative count {len(records)} is below requested limit {limit}")

    verified = []
    for record in records:
        mutation_path = _resolve(str(record.get("source_path") or ""))
        actual_sha = _sha256(mutation_path)
        if actual_sha != record.get("mutation_sha256"):
            raise ValueError(f"mutation SHA-256 mismatch: {mutation_path}")
        item = dict(record)
        item["source_path"] = str(record.get("source_path"))
        item["mutation_sha256"] = actual_sha
        item["executable_mutation_key"] = _executable_key(str(record.get("mutation_instance_key") or ""))
        verified.append(item)

    ranked = sorted(
        verified,
        key=lambda item: (
            -float(item.get("confidence_score")),
            int(item.get("source_order") or 0),
            str(item.get("mutation_instance_key") or ""),
        ),
    )
    top = []
    for rank, record in enumerate(ranked[:limit], 1):
        item = dict(record)
        item["rank"] = rank
        top.append(item)

    result = {
        "schema_version": "sock-shop-full-top11-v1",
        "source": {
            "overlap_audit": str(overlap_audit_path),
            "overlap_audit_sha256": hashlib.sha256(audit_bytes).hexdigest(),
            "normalization_config_sha256": normalization_sha,
            "full_family_representatives": len(records),
        },
        "selection_policy": {
            "limit": limit,
            "sort": ["confidence_score_desc", "source_order_asc", "mutation_instance_key_asc"],
            "runtime_outcomes_used": False,
            "evidence_availability_used": False,
            "gate_results_used": False,
            "blocked_replacement_allowed": False,
        },
        "top11": top,
        "human_review": "pending",
        "knowledge_base_updated": False,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = output_dir / "full-top11-manifest.json"
    manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "full-top11-manifest.sha256").write_text(
        f"{_sha256(manifest)}  {manifest.name}\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--overlap-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=11)
    args = parser.parse_args()
    result = build_full_top11_manifest(args.overlap_audit, args.output, limit=args.limit)
    print(
        json.dumps(
            {
                "selected": len(result["top11"]),
                "top": [
                    {"rank": item["rank"], "id": item["hypothesis_id"], "confidence": item["confidence_score"]}
                    for item in result["top11"]
                ],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
