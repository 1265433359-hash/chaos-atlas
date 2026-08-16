"""Freeze an evidence-backed R5 selection without rerunning Full."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.sock_shop_hypothesis_identity import mutation_instance_key


def _resolve(path: str) -> Path:
    value = Path(path)
    if value.is_file():
        return value
    candidate = ROOT / value
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(path)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_runtime_report(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    reasons = []
    checks = {
        "status_completed": value.get("status") == "completed",
        "baseline_pass": bool((value.get("baseline") or {}).get("pass")),
        "injection_applied": bool((value.get("injection") or {}).get("applied")),
        "injection_confirmed": bool((value.get("injection") or {}).get("injected")),
        "recovered": bool((value.get("recovery") or {}).get("recovered")),
        "cleanup_absent": bool((value.get("cleanup") or {}).get("absent_confirmed")),
        "cleanup_no_residuals": not bool((value.get("cleanup") or {}).get("residual_resources")),
        "cleanup_no_scan_errors": not bool((value.get("cleanup") or {}).get("global_scan_errors")),
        "washout_stable": bool((value.get("washout") or {}).get("stable")),
        "diagnostics_captured": (value.get("diagnostics") or {}).get("status") == "captured",
        "human_review_pending": value.get("human_review") == "pending",
        "knowledge_base_not_updated": value.get("knowledge_base_updated") is False,
    }
    for key, passed in checks.items():
        if not passed:
            reasons.append(key)

    mutation_path = None
    mutation_sha = None
    mutation = value.get("mutation") or {}
    try:
        mutation_path = _resolve(str(mutation.get("path") or ""))
        mutation_sha = _sha(mutation_path)
        if mutation_sha != mutation.get("sha256"):
            reasons.append("mutation_sha256_mismatch")
    except Exception as exc:
        reasons.append(f"mutation_unavailable:{type(exc).__name__}:{exc}")

    diagnostic_files = []
    for item in (value.get("diagnostics") or {}).get("files") or []:
        try:
            diagnostic_path = _resolve(str(item.get("path") or ""))
            actual = _sha(diagnostic_path)
            match = actual == item.get("sha256")
        except Exception as exc:
            diagnostic_path = None
            actual = None
            match = False
            reasons.append(f"diagnostic_unavailable:{type(exc).__name__}:{exc}")
        if not match:
            reasons.append(f"diagnostic_sha256_mismatch:{item.get('path')}")
        diagnostic_files.append(
            {
                "path": item.get("path"),
                "expected_sha256": item.get("sha256"),
                "actual_sha256": actual,
                "match": match,
            }
        )
    return {
        "path": str(path),
        "report_sha256": _sha(path),
        "valid": not reasons,
        "reasons": reasons,
        "checks": checks,
        "classification": (value.get("observation") or {}).get("classification"),
        "mutation_id": value.get("mutation_id"),
        "replicate": value.get("replicate"),
        "mutation_path": str(mutation_path) if mutation_path else mutation.get("path"),
        "mutation_sha256": mutation_sha,
        "diagnostic_files": diagnostic_files,
    }


def load_full_evidence(discovery_path: Path, reports_root: Path) -> dict[str, Any]:
    discovery = json.loads(discovery_path.read_text(encoding="utf-8"))
    hypotheses = {str(item.get("id")): item for item in discovery.get("hypotheses") or []}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    invalid = []
    for path in sorted(reports_root.glob("*.json")):
        evidence = validate_runtime_report(path)
        hypothesis = hypotheses.get(str(evidence.get("mutation_id")))
        if not evidence["valid"] or hypothesis is None:
            invalid.append({"report": evidence, "hypothesis_found": hypothesis is not None})
            continue
        mutation_path = _resolve(str(evidence["mutation_path"]))
        mutation = yaml.safe_load(mutation_path.read_text(encoding="utf-8"))
        evidence["mutation_instance_key"] = mutation_instance_key(hypothesis, mutation)
        grouped[str(evidence["mutation_id"])].append(evidence)

    eligible: dict[str, dict[str, Any]] = {}
    incomplete = []
    for hypothesis_id, reports in sorted(grouped.items()):
        reports = sorted(reports, key=lambda item: int(item.get("replicate") or 0))
        instances = {item["mutation_instance_key"] for item in reports}
        replicates = {int(item.get("replicate") or 0) for item in reports}
        if len(reports) != 2 or replicates != {1, 2} or len(instances) != 1:
            incomplete.append({"hypothesis_id": hypothesis_id, "reports": reports})
            continue
        instance = next(iter(instances))
        eligible[instance] = {
            "hypothesis_id": hypothesis_id,
            "mutation_instance_key": instance,
            "reports": reports,
        }
    return {
        "eligible_by_instance": eligible,
        "invalid_reports": invalid,
        "incomplete_mutations": incomplete,
        "reports_scanned": sum(len(items) for items in grouped.values()) + len(invalid),
    }


def _load_ablation_evidence(progress_path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in progress.get("rows") or []:
        report_path = _resolve(str(row.get("report_path") or ""))
        grouped[(str(row.get("group")), str(row.get("hypothesis_id")))].append(
            validate_runtime_report(report_path)
        )
    result = {}
    for key, reports in grouped.items():
        reports.sort(key=lambda item: int(item.get("replicate") or 0))
        result[key] = {
            "valid": len(reports) == 2 and all(item["valid"] for item in reports),
            "reports": reports,
        }
    return result


def build_evidence_selection(
    audit_dir: Path,
    full_discovery_path: Path,
    full_reports_root: Path,
    ablation_progress_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    overlap = json.loads((audit_dir / "overlap_audit.json").read_text(encoding="utf-8"))
    base_selection = json.loads((audit_dir / "selection_manifest.json").read_text(encoding="utf-8"))
    threshold = float(base_selection["config"]["high_confidence_threshold"])
    sample_seed = int(base_selection["config"]["sample_seed"])
    full_evidence = load_full_evidence(full_discovery_path, full_reports_root)

    strict_overlap = [
        item for item in overlap.get("strict_overlap") or []
        if item["full"].get("confidence_score") is not None
        and float(item["full"]["confidence_score"]) >= threshold
        and item["full"]["mutation_instance_key"] in full_evidence["eligible_by_instance"]
    ]
    full_candidates = [
        item for item in overlap.get("full_only") or []
        if item.get("confidence_score") is not None
        and float(item["confidence_score"]) >= threshold
        and item["mutation_instance_key"] in full_evidence["eligible_by_instance"]
    ]
    full_candidates.sort(key=lambda item: (-float(item["confidence_score"]), item["mutation_instance_key"]))
    ablation_pool = sorted(overlap.get("ablation_only") or [], key=lambda item: item["mutation_instance_key"])
    matched_size = min(len(full_candidates), len(ablation_pool))
    full_selected = full_candidates[:matched_size]
    ablation_selected = random.Random(sample_seed).sample(ablation_pool, matched_size)
    ablation_evidence = _load_ablation_evidence(ablation_progress_path)

    def full_entry(record: dict[str, Any]) -> dict[str, Any]:
        evidence = full_evidence["eligible_by_instance"][record["mutation_instance_key"]]
        return {"record": record, "evidence": evidence}

    overlap_entries = []
    for item in strict_overlap:
        ab_id = str(item["ablation"]["hypothesis_id"])
        ab_evidence = ablation_evidence.get(("overlap_high_confidence", ab_id))
        if not ab_evidence or not ab_evidence["valid"]:
            raise ValueError(f"missing valid Ablation overlap evidence: {ab_id}")
        overlap_entries.append(
            {
                "full": full_entry(item["full"]),
                "ablation": {"record": item["ablation"], "evidence": ab_evidence},
            }
        )

    ablation_entries = []
    for record in ablation_selected:
        key = ("ablation_only_random", str(record["hypothesis_id"]))
        evidence = ablation_evidence.get(key)
        if not evidence or not evidence["valid"]:
            raise ValueError(f"missing valid Ablation-only evidence: {record['hypothesis_id']}")
        ablation_entries.append({"record": record, "evidence": evidence})

    selected_ids = {str(item["record"]["hypothesis_id"]) for item in ablation_entries}
    all_ablation_ids = {str(item["hypothesis_id"]) for item in ablation_pool}
    result = {
        "schema_version": "sock-shop-r5-evidence-selection-v1",
        "selection_basis": {
            "runtime_outcomes_used_for_selection": False,
            "full_requires_two_strict_instance_completed_reports": True,
            "confidence_threshold": threshold,
            "sample_seed": sample_seed,
            "matched_sample_size": matched_size,
            "full_high_confidence_with_existing_evidence": len(full_candidates),
            "ablation_only_pool": len(ablation_pool),
        },
        "groups": {
            "strict_overlap_high_confidence": overlap_entries,
            "full_only_high_confidence": [full_entry(record) for record in full_selected],
            "ablation_only_random": ablation_entries,
        },
        "excluded": {
            "ablation_runtime_extra_not_in_main_denominator": sorted(all_ablation_ids - selected_ids),
            "full_high_confidence_without_existing_strict_runtime": sum(
                item.get("confidence_score") is not None
                and float(item["confidence_score"]) >= threshold
                and item["mutation_instance_key"] not in full_evidence["eligible_by_instance"]
                for item in overlap.get("full_only") or []
            ),
        },
        "verification": {
            "full_reports_scanned": full_evidence["reports_scanned"],
            "full_invalid_reports": len(full_evidence["invalid_reports"]),
            "full_incomplete_mutations": len(full_evidence["incomplete_mutations"]),
        },
        "human_review": "pending",
        "knowledge_base_updated": False,
    }
    output_path = output_dir / "evidence-selection.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    file_sha = _sha(output_path)
    (output_dir / "evidence-selection.sha256").write_text(
        file_sha + "  evidence-selection.json\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-dir", type=Path, required=True)
    parser.add_argument("--full-discovery", type=Path, required=True)
    parser.add_argument("--full-reports", type=Path, required=True)
    parser.add_argument("--ablation-progress", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_evidence_selection(
        args.audit_dir,
        args.full_discovery,
        args.full_reports,
        args.ablation_progress,
        args.output,
    )
    print(json.dumps({"selection_basis": result["selection_basis"], "excluded": result["excluded"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
