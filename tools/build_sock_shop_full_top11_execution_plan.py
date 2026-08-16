"""Resolve reusable evidence and fresh work for the frozen Full Top 11."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.build_sock_shop_r5_evidence_selection import load_full_evidence
from tools.review_sock_shop_r5_dedup import executable_mutation_key


def _path_key(value: str) -> str:
    return value.replace("\\", "/")


def _evidence_is_reusable(evidence: dict[str, Any] | None) -> bool:
    reports = (evidence or {}).get("reports") or []
    return (
        len(reports) == 2
        and {int(item.get("replicate") or 0) for item in reports} == {1, 2}
        and all(item.get("valid") is True for item in reports)
    )


def _historical_evidence_matches_record(evidence: dict[str, Any], record: dict[str, Any]) -> bool:
    expected_instance = str(record.get("mutation_instance_key") or "")
    if evidence.get("mutation_instance_key") not in {None, "", expected_instance}:
        return False
    expected_sha = str(record.get("mutation_sha256") or "")
    return all(str(report.get("mutation_sha256") or "") == expected_sha for report in evidence.get("reports") or [])


def classify_execution_entries(
    top_entries: list[dict[str, Any]],
    gate_by_path: dict[str, dict[str, Any]],
    evidence_by_executable_key: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    gate_lookup = {_path_key(path): value for path, value in gate_by_path.items()}
    result = []
    for record in top_entries:
        source_path = str(record.get("source_path") or "")
        gate = gate_lookup.get(_path_key(source_path))
        if gate is None:
            raise ValueError(f"missing gate result: {source_path}")
        item = dict(record)
        item["gate_decision"] = gate.get("decision")
        item["gate_errors"] = list(gate.get("errors") or [])
        gate_sha = gate.get("mutation_sha256")
        if gate_sha and gate_sha != record.get("mutation_sha256"):
            raise ValueError(f"gate mutation SHA-256 mismatch: {source_path}")
        executable_key = str(record.get("executable_mutation_key") or executable_mutation_key(
            str(record.get("mutation_instance_key") or "")
        ))
        evidence = evidence_by_executable_key.get(executable_key)
        if gate.get("decision") != "ready_for_injection":
            item["execution_status"] = "blocked"
            item["historical_evidence"] = None
            item["fresh_units"] = []
        elif evidence is not None and _evidence_is_reusable(evidence) and not _historical_evidence_matches_record(evidence, record):
            raise ValueError(f"historical mutation SHA-256 or identity mismatch: {record.get('hypothesis_id')}")
        elif _evidence_is_reusable(evidence):
            item["execution_status"] = "reused_historical"
            item["historical_evidence"] = evidence
            item["fresh_units"] = []
        else:
            item["execution_status"] = "fresh_required"
            item["historical_evidence"] = None
            item["fresh_units"] = [
                {"hypothesis_id": record.get("hypothesis_id"), "replicate": replicate}
                for replicate in (1, 2)
            ]
        result.append(item)
    return result


def build_execution_plan(
    manifest_path: Path,
    gate_path: Path,
    full_discovery_path: Path,
    full_reports_root: Path,
    output_path: Path,
) -> dict[str, Any]:
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite execution plan: {output_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    for key in ("selection_manifest_sha256", "manifest_sha256"):
        recorded = gate.get(key)
        if recorded and recorded != manifest_sha:
            raise ValueError(f"gate {key} does not match manifest SHA-256")
    gate_by_path = {str(item.get("mutation") or ""): item for item in gate.get("results") or []}
    expected_paths = {str(item.get("source_path") or "") for item in manifest.get("top11") or []}
    missing_gate_paths = sorted(expected_paths - set(gate_by_path))
    if missing_gate_paths:
        raise ValueError(f"gate is missing Top 11 mutation provenance: {missing_gate_paths[0]}")

    loaded = load_full_evidence(full_discovery_path, full_reports_root)
    evidence_by_executable: dict[str, dict[str, Any]] = {}
    for instance_key, evidence in sorted(loaded["eligible_by_instance"].items()):
        key = executable_mutation_key(instance_key)
        current = evidence_by_executable.get(key)
        if current is None or str(evidence.get("hypothesis_id")) < str(current.get("hypothesis_id")):
            evidence_by_executable[key] = evidence

    entries = classify_execution_entries(manifest.get("top11") or [], gate_by_path, evidence_by_executable)
    result = {
        "schema_version": "sock-shop-full-top11-execution-plan-v1",
        "manifest": str(manifest_path),
        "manifest_sha256": manifest_sha,
        "gate": str(gate_path),
        "gate_sha256": hashlib.sha256(gate_path.read_bytes()).hexdigest(),
        "gate_provenance": {
            "manifest_sha256": manifest_sha,
            "gate_results_match_top11_paths": True,
        },
        "full_discovery": str(full_discovery_path),
        "full_reports_root": str(full_reports_root),
        "entries": entries,
        "summary": {
            "total": len(entries),
            "blocked": sum(item["execution_status"] == "blocked" for item in entries),
            "reused_historical": sum(item["execution_status"] == "reused_historical" for item in entries),
            "fresh_required": sum(item["execution_status"] == "fresh_required" for item in entries),
            "fresh_replicates": sum(len(item["fresh_units"]) for item in entries),
            "historical_reports_scanned": loaded["reports_scanned"],
            "historical_invalid_reports": len(loaded["invalid_reports"]),
            "historical_incomplete_mutations": len(loaded["incomplete_mutations"]),
        },
        "human_review": "pending",
        "knowledge_base_updated": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    output_path.with_suffix(".sha256").write_text(
        f"{hashlib.sha256(output_path.read_bytes()).hexdigest()}  {output_path.name}\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--full-discovery", type=Path, required=True)
    parser.add_argument("--full-reports", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_execution_plan(
        args.manifest,
        args.gate,
        args.full_discovery,
        args.full_reports,
        args.output,
    )
    print(json.dumps(result["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
