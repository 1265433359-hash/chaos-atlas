"""Append a synchronized disambiguation result to an immutable RCA round."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

from tools.compile_rca_regression import compile_regression_intents, project_knowledge_draft
from tools.evidence_collectors import collect_file_evidence
from tools.rca_loop import _contains_sensitive_value, sha256_json
from tools.validate_rca_loop import validate_artifact


ROUND_ID = "pilot-r3-disambiguation-r2"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, indent=2, ensure_ascii=True, sort_keys=True) + "\n"
    if _contains_sensitive_value(text):
        raise ValueError(f"sensitive value detected in {path}")
    path.write_text(text, encoding="utf-8")


def _copy_tree(parent_root: Path, output_root: Path) -> None:
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"output {output_root} is not empty")
    output_root.mkdir(parents=True, exist_ok=True)
    for source in parent_root.rglob("*"):
        if source.is_file() and source.name != "validation_report.json":
            destination = output_root / source.relative_to(parent_root)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)


def build_disambiguation_round(
    *,
    parent_root: Path,
    source_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    """Create a new RCA round and preserve the parent's deterministic statuses."""

    parent_root = Path(parent_root)
    source_root = Path(source_root)
    output_root = Path(output_root)
    parent_manifest = _load(parent_root / "manifest.json")
    source_result = _load(source_root / "result.json")
    summary = source_result.get("summary") or {}
    if summary.get("classification") != "observation_inconclusive":
        raise ValueError("disambiguation ingestion requires an inconclusive r2 result")
    if summary.get("deterministic") is not False:
        raise ValueError("disambiguation ingestion requires a non-deterministic r2 result")
    _copy_tree(parent_root, output_root)

    case_paths = sorted((output_root / "cases").glob("*.json"))
    if len(case_paths) != 1:
        raise ValueError("Sock Shop disambiguation round expects exactly one case")
    case_path = case_paths[0]
    case = _load(case_path)
    case["round_id"] = ROUND_ID
    case.setdefault("evidence_refs", [])
    evidence_root = output_root / "evidence" / "disambiguation-r2"
    source_files = {
        "result.json": "config",
        "timeline.jsonl": "config",
        "manifest.json": "kubernetes_event",
    }
    for name in source_files:
        source = source_root / name
        if not source.is_file():
            raise ValueError(f"missing disambiguation source: {source}")
        destination = evidence_root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    claim_scope = str(case.get("test_node", {}).get("target_role") or "front-end deployment")
    new_evidence = [
        collect_file_evidence(
            root=output_root,
            source_ref="evidence/disambiguation-r2/timeline.jsonl",
            evidence_id="EV-LIVE-R2-TIMELINE-001",
            kind="config",
            claim_scope=claim_scope,
            interpretation="synchronized injection-window timeline shows HTTP 200 before a Ready replacement endpoint and later transport failure",
            satisfies=["injection_window_timeline"],
            window=source_result.get("window"),
        ),
        collect_file_evidence(
            root=output_root,
            source_ref="evidence/disambiguation-r2/result.json",
            evidence_id="EV-LIVE-R2-HTTP-ARTIFACT-001",
            kind="business_path_replay",
            claim_scope=claim_scope,
            interpretation="three HTTP 200 samples occurred without a Ready replacement endpoint and are classified as observation-window artifacts, not defense evidence",
            polarity="neutral",
            window=source_result.get("window"),
        ),
        collect_file_evidence(
            root=output_root,
            source_ref="evidence/disambiguation-r2/manifest.json",
            evidence_id="EV-LIVE-R2-INJECTION-001",
            kind="kubernetes_event",
            claim_scope=claim_scope,
            interpretation="bounded r2 runtime manifest records confirmed PodChaos injection and complete cleanup",
            satisfies=["injection_confirmation", "cleanup_confirmation"],
            window=source_result.get("window"),
        ),
    ]
    case["evidence_refs"].extend(new_evidence)
    case["knowledge_status"] = "provisional"
    case["knowledge_promotion_audit"] = {
        "allowed": True,
        "next_status": "provisional",
        "reason": "observation_window_artifact_requires_defense_counterfactual",
    }
    for hypothesis in case.get("hypotheses", []):
        hypothesis.setdefault("evidence_against", []).append("EV-LIVE-R2-HTTP-ARTIFACT-001")
        hypothesis["evidence_against"] = sorted(set(hypothesis["evidence_against"]))
        hypothesis["next_action"] = "A-SS-SINGLETON-COUNTERFACTUAL-001"
    _write(case_path, case)
    for hypothesis in case.get("hypotheses", []):
        _write(output_root / "hypotheses" / f"{hypothesis['hypothesis_id']}.json", hypothesis)

    draft = project_knowledge_draft(case, case.get("hypotheses", []), case.get("next_actions", []))
    _write(output_root / "knowledge_drafts" / f"{draft['id']}.json", draft)
    _write(
        output_root / "knowledge_drafts" / "regression_intents.json",
        compile_regression_intents([draft], snapshot={"cards": [draft]}),
    )
    manifest = _load(output_root / "manifest.json")
    manifest.update(
        {
            "round_id": ROUND_ID,
            "parent_round_id": parent_manifest.get("round_id"),
            "parent_manifest_sha256": sha256_json(parent_manifest),
            "disambiguation_source_sha256": hashlib.sha256((source_root / "result.json").read_bytes()).hexdigest(),
            "knowledge_base_updated": False,
            "case_statuses": [
                {
                    "weakness_id": case.get("weakness_id"),
                    "weakness_status": case.get("weakness_status"),
                    "rca_status": case.get("rca_status"),
                    "knowledge_status": case.get("knowledge_status"),
                }
            ],
        }
    )
    _write(output_root / "manifest.json", manifest)
    report = validate_artifact(output_root)
    _write(output_root / "validation_report.json", report)
    if not report["valid"]:
        raise ValueError("generated disambiguation RCA round failed validation: " + "; ".join(report["errors"]))
    return {
        "status": summary["classification"],
        "knowledge_status": case["knowledge_status"],
        "round_id": ROUND_ID,
        "validation": report,
        "evidence_ids": [item["evidence_id"] for item in new_evidence],
    }
