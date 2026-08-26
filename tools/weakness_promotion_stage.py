"""Promote repeated runtime weakness evidence into a local reusable card.

This path is intentionally separate from defense promotion.  A weakness card
requires repeated, independently captured runtime degradation with a confirmed
RCA; a defensive result is rejected rather than being reinterpreted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.compile_rca_regression import compile_regression_intents
from tools.rca_loop import _contains_sensitive_value, evaluate_knowledge_promotion


REQUIRED_RUN_ARTIFACTS = (
    "run_manifest.json",
    "classify.json",
    "observe.json",
    "rca_report.json",
    "knowledge_draft.json",
    "cleanup_report.json",
)
_ATTESTATION_FIELDS = ("baseline", "injection", "observation", "recovery", "cleanup", "independent_oracle")


def _load_payload(root: Path, name: str) -> dict[str, Any]:
    path = Path(root) / name
    if path.is_symlink() or path.resolve().parent != Path(root).resolve():
        raise ValueError(f"{path} must be a regular file directly under its run root")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    payload = value.get("payload", value)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} payload must contain an object")
    return payload


def select_history_children(root: Path) -> dict[str, Any]:
    """Select only immediate, complete run directories below an explicit root."""

    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError(f"weakness history root must be a real directory: {root}")
    selected: list[Path] = []
    rejected: list[dict[str, str]] = []
    for child in sorted(root.iterdir(), key=lambda path: path.name):
        if child.is_symlink() or not child.is_dir():
            rejected.append({"path": child.name, "reason": "not_directory"})
            continue
        if not all(
            (child / name).is_file()
            and not (child / name).is_symlink()
            and (child / name).resolve().parent == child.resolve()
            for name in REQUIRED_RUN_ARTIFACTS
        ):
            rejected.append({"path": child.name, "reason": "missing_required_artifacts"})
            continue
        selected.append(child)
    return {"selected": selected, "rejected": rejected}


def _fingerprint(
    *, classification: dict[str, Any], rca: dict[str, Any], observation: dict[str, Any], cleanup: dict[str, Any], draft: dict[str, Any]
) -> str:
    semantic = {
        "classification": {"result": classification.get("result"), "attestation": classification.get("attestation")},
        "rca": {
            "project_id": rca.get("project_id"),
            "project_commit": rca.get("project_commit"),
            "case_family": rca.get("case_family"),
            "test_node": rca.get("test_node"),
            "evidence_refs": rca.get("evidence_refs"),
            "hypotheses": rca.get("hypotheses"),
        },
        "observation": observation,
        "cleanup": {"status": cleanup.get("status"), "errors": cleanup.get("errors")},
        "draft": {"next_evidence": draft.get("next_evidence"), "applicability_conditions": draft.get("applicability_conditions")},
    }
    return hashlib.sha256(json.dumps(semantic, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _causal_identity(rca: dict[str, Any]) -> tuple[str, ...]:
    node = rca.get("test_node") or {}
    parameters = json.dumps(node.get("parameters") or {}, sort_keys=True, ensure_ascii=True)
    return (
        str(rca.get("project_id") or ""),
        str(rca.get("project_commit") or ""),
        str(rca.get("case_family") or ""),
        str(node.get("target") or ""),
        str(node.get("target_kind") or ""),
        str(node.get("family") or ""),
        str(node.get("operation") or ""),
        parameters,
    )


def _evidence_source_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    for item in value or []:
        if isinstance(item, dict):
            item = item.get("source_ref")
        if item:
            refs.add(str(item))
    return refs


def _validate_run(root: Path) -> dict[str, Any]:
    root = Path(root)
    classification = _load_payload(root, "classify.json")
    if classification.get("result") != "availability_degraded":
        raise ValueError(f"{root}: runtime result is not availability_degraded")
    attestation = classification.get("attestation") or {}
    if not isinstance(attestation, dict) or not all(attestation.get(field) is True for field in _ATTESTATION_FIELDS):
        raise ValueError(f"{root}: lifecycle attestation is incomplete")

    rca = _load_payload(root, "rca_report.json")
    manifest = _load_payload(root, "run_manifest.json")
    draft = _load_payload(root, "knowledge_draft.json")
    run_id = str(manifest.get("run_id") or "")
    if not run_id:
        raise ValueError(f"{root}: run identity is missing")
    project_id = str(rca.get("project_id") or "")
    project_commit = str(rca.get("project_commit") or "")
    if not project_id or not project_commit:
        raise ValueError(f"{root}: project identity is missing")
    if rca.get("round_id") and str(rca.get("round_id")) != run_id:
        raise ValueError(f"{root}: RCA round_id does not match run manifest")
    if draft.get("round_id") and str(draft.get("round_id")) != run_id:
        raise ValueError(f"{root}: knowledge draft round_id does not match run manifest")
    if draft.get("project") and str(draft.get("project")) != project_id:
        raise ValueError(f"{root}: knowledge draft project does not match RCA")
    if draft.get("project_commit") and str(draft.get("project_commit")) != project_commit:
        raise ValueError(f"{root}: knowledge draft commit does not match RCA")
    inventory_path = Path(root) / "inventory.json"
    if inventory_path.is_symlink():
        raise ValueError(f"{root}: inventory artifact must not be a symlink")
    if inventory_path.is_file():
        inventory = _load_payload(root, "inventory.json")
        if inventory.get("project_id") and str(inventory.get("project_id")) != project_id:
            raise ValueError(f"{root}: inventory project does not match RCA")
        if inventory.get("project_commit") and str(inventory.get("project_commit")) != project_commit:
            raise ValueError(f"{root}: inventory commit does not match RCA")
    transition = rca.get("transition") or {}
    if rca.get("rca_status") != "confirmed" or transition.get("next_status") not in {None, "confirmed"}:
        raise ValueError(f"{root}: RCA is not confirmed")
    hypotheses = rca.get("hypotheses") or []
    if not isinstance(hypotheses, list) or not hypotheses:
        raise ValueError(f"{root}: confirmed RCA requires at least one hypothesis")
    for hypothesis in hypotheses:
        if not isinstance(hypothesis, dict):
            raise ValueError(f"{root}: RCA hypothesis must be an object")
        if str(hypothesis.get("status")) != "confirmed":
            raise ValueError(f"{root}: RCA hypothesis is not confirmed")
        if not str(hypothesis.get("hypothesis_id") or ""):
            raise ValueError(f"{root}: RCA hypothesis identity is missing")
        if not isinstance(hypothesis.get("required_evidence"), list) or not hypothesis.get("required_evidence"):
            raise ValueError(f"{root}: RCA hypothesis required evidence is missing")
        if not isinstance(hypothesis.get("evidence_for"), list) or not hypothesis.get("evidence_for"):
            raise ValueError(f"{root}: RCA hypothesis supporting evidence is missing")
        if hypothesis.get("unsupported_claims"):
            raise ValueError(f"{root}: RCA hypothesis contains unsupported claims")
    audits = rca.get("rca_audit") or []
    if not isinstance(audits, list) or not audits:
        raise ValueError(f"{root}: RCA audit is missing")
    for audit in audits:
        audit_transition = audit.get("transition") or {}
        if audit_transition.get("allowed") is not True or audit_transition.get("next_status") != "confirmed":
            raise ValueError(f"{root}: RCA audit did not confirm the case")
        for item in audit.get("hypotheses") or []:
            if item.get("required_evidence_complete") is not True:
                raise ValueError(f"{root}: RCA audit evidence is incomplete")
    contradiction = any(
        bool(item.get("high_severity_contradiction"))
        for audit in audits
        for item in (audit.get("hypotheses") or [])
        if isinstance(item, dict)
    )
    if contradiction:
        raise ValueError(f"{root}: runtime evidence contains a contradiction")

    observation = _load_payload(root, "observe.json").get("observation") or {}
    if not isinstance(observation, dict) or not observation.get("samples"):
        raise ValueError(f"{root}: business observation evidence is incomplete")
    rca_refs = _evidence_source_refs(rca.get("evidence_refs"))
    classify_refs = _evidence_source_refs(classification.get("evidence_refs"))
    observe_refs = _evidence_source_refs(_load_payload(root, "observe.json").get("evidence_refs"))
    if not rca_refs or (classify_refs and classify_refs != rca_refs) or (observe_refs and observe_refs != rca_refs):
        raise ValueError(f"{root}: runtime evidence references are not bound across stages")
    cleanup = _load_payload(root, "cleanup_report.json")
    if cleanup.get("status") != "verified" or cleanup.get("errors"):
        raise ValueError(f"{root}: cleanup is not verified")
    identity = _causal_identity({**rca, "project_id": project_id, "project_commit": project_commit})
    node = rca.get("test_node") or {}
    return {
        "root": str(root),
        "run_id": run_id,
        "seed": manifest.get("seed"),
        "project_id": project_id,
        "project_commit": project_commit,
        "case_family": str(rca.get("case_family") or ""),
        "weakness_id": str(rca.get("weakness_id") or ""),
        "rca_status": str(rca.get("rca_status")),
        "target": str(node.get("target") or ""),
        "target_kind": str(node.get("target_kind") or ""),
        "test_node": dict(node),
        "symptom": dict(rca.get("symptom") or {}),
        "hypotheses": list(hypotheses),
        "evidence_refs": list(rca.get("evidence_refs") or []),
        "applicability_conditions": list(draft.get("applicability_conditions") or []),
        "exclusion_conditions": list(draft.get("exclusion_conditions") or []),
        "next_evidence": list(draft.get("next_evidence") or []),
        "identity": identity,
        "run_fingerprint": _fingerprint(
            classification=classification,
            rca=rca,
            observation=observation,
            cleanup=cleanup,
            draft=draft,
        ),
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    text = json.dumps(value, indent=2, ensure_ascii=True) + "\n"
    if _contains_sensitive_value(text):
        raise ValueError(f"refusing to write sensitive weakness artifact: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _copy_knowledge_artifact_without_overwrite(source: Path, destination: Path) -> None:
    """Install a card only when the destination is absent or semantically equal."""

    destination = Path(destination)
    if destination.is_symlink():
        raise ValueError(f"knowledge artifact destination must not be a symlink: {destination.name}")
    if destination.exists():
        try:
            existing = json.loads(destination.read_text(encoding="utf-8"))
            incoming = json.loads(Path(source).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"existing knowledge artifact is not valid JSON: {destination.name}") from exc
        if existing != incoming:
            raise ValueError(f"knowledge artifact already exists with different content: {destination.name}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _stage_payload(*, status: str, selected: list[Path], rejected: list[dict[str, str]], **extra: Any) -> dict[str, Any]:
    return {
        "schema_version": "chaosatlas-weakness-promotion-stage-v1",
        "status": status,
        "selected_runs": [path.name for path in selected],
        "rejected_inputs": rejected,
        **extra,
    }


def record_promotion_conflict(
    *, old_card: Path | None, run_roots: list[Path], reason: str, output_root: Path
) -> dict[str, Any]:
    """Record invalid or contradictory evidence without modifying an old card."""

    old_card = Path(old_card) if old_card is not None else None
    snapshot = None
    if old_card is not None and old_card.is_file():
        snapshot = hashlib.sha256(old_card.read_bytes()).hexdigest()
    payload = {
        "schema_version": "chaosatlas-weakness-conflict-v1",
        "status": "contested",
        "reason": str(reason),
        "old_card": str(old_card) if old_card is not None else None,
        "old_snapshot_sha256": snapshot,
        "run_roots": [str(Path(root)) for root in run_roots],
        "reusable_card_preserved": bool(old_card is not None and old_card.is_file()),
        "regression_intents": [],
    }
    _write_json(Path(output_root) / "knowledge_conflict.json", payload)
    return payload


def promote_from_history(
    *, history_root: Path, output_root: Path, knowledge_write_root: Path | None = None
) -> dict[str, Any]:
    """Promote two independent, same-identity weakness runs to local reuse."""

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
        _write_json(output_root / "knowledge_promotion.json", payload)
        return payload

    old_card = Path(knowledge_write_root) / "weakness_card.json" if knowledge_write_root is not None else None
    try:
        runs = [_validate_run(root) for root in selected]
        if len({run["run_id"] for run in runs}) != len(runs):
            raise ValueError("weakness promotion requires distinct run ids")
        if len({run["run_fingerprint"] for run in runs}) != len(runs):
            raise ValueError("weakness promotion requires independent run artifacts")
        identities = {run["identity"] for run in runs}
        if len(identities) != 1:
            raise ValueError("weakness runs must share the same project revision and causal identity")
        identity = next(iter(identities))
        project_id, project_commit, case_family, target, target_kind, family, operation, _ = identity
        promotion = evaluate_knowledge_promotion(
            current="provisional",
            weakness_status="confirmed",
            rca_status="confirmed",
            valid_reproductions=len(runs),
            valid_counterfactuals=0,
            lifecycle_complete=True,
            direct_evidence=all(run["evidence_refs"] for run in runs),
            applicability_complete=all(run["applicability_conditions"] for run in runs),
            regression_complete=True,
            contradiction=False,
        )
        if not promotion.get("allowed") or promotion.get("next_status") != "local_reusable":
            raise ValueError(f"weakness promotion gate rejected evidence: {promotion}")

        card_id = "KB-WEAK-" + hashlib.sha256(":".join(identity).encode("utf-8")).hexdigest()[:16]
        first = runs[0]
        card = {
            "schema_version": "chaosatlas-weakness-knowledge-v1",
            "id": card_id,
            "project": project_id,
            "project_commit": project_commit,
            "case_family": case_family,
            "weakness_id": first["weakness_id"],
            "target": target,
            "target_kind": target_kind,
            "classification": "availability_weakness",
            "weakness_status": "confirmed",
            "rca_status": "confirmed",
            "knowledge_status": "local_reusable",
            "mechanism_level": "service_boundary",
            "mechanism_claim": (first["hypotheses"][0].get("claim") if first["hypotheses"] else "runtime availability degrades during the confirmed fault"),
            "test_node": first["test_node"],
            "applicability_conditions": sorted({item for run in runs for item in run["applicability_conditions"]}) or ["same project and commit"],
            "exclusion_conditions": sorted({item for run in runs for item in run["exclusion_conditions"]}),
            "evidence_runs": [
                {
                    "run_id": run["run_id"],
                    "seed": run["seed"],
                    "run_fingerprint": run["run_fingerprint"],
                    "root": run["root"],
                    "evidence_refs": run["evidence_refs"],
                }
                for run in runs
            ],
            "valid_reproductions": len(runs),
            "counter_evidence": [],
            "promotion_audit": promotion,
            "next_evidence": sorted({item for run in runs for item in run["next_evidence"]}) or ["repeat_business_oracle", "verify_recovery_after_fault_removal"],
            "stop_rule": "stop after two valid reproductions or one clean falsification",
            "regression_recipe": {"oracle": first["symptom"].get("oracle") or "project business oracle", "selected_next_action": None},
        }
        snapshot = {"card": card, "run_ids": [run["run_id"] for run in runs]}
        regression = compile_regression_intents([card], snapshot=snapshot)
        card["regression_intents"] = regression["intents"]
        artifact_root = output_root / "promotion_artifacts"
        _write_json(artifact_root / "weakness_card.json", card)
        _write_json(artifact_root / f"{card_id}.json", card)
        _write_json(artifact_root / "regression_intents.json", regression)
        for name in ("weakness_card.json", f"{card_id}.json", "regression_intents.json"):
            if knowledge_write_root is not None:
                destination = Path(knowledge_write_root)
                destination.mkdir(parents=True, exist_ok=True)
                _copy_knowledge_artifact_without_overwrite(artifact_root / name, destination / name)
        payload = _stage_payload(
            status="promoted",
            selected=selected,
            rejected=rejected,
            knowledge_status=card["knowledge_status"],
            classification=card["classification"],
            card_id=card_id,
            weakness_id=first["weakness_id"],
            valid_reproductions=len(runs),
            regression=regression,
        )
        _write_json(output_root / "knowledge_promotion.json", payload)
        return {"status": "promoted", **card, "regression": regression, "stage": payload}
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        conflict = record_promotion_conflict(
            old_card=old_card if old_card is not None and old_card.is_file() else None,
            run_roots=selected,
            reason=str(exc),
            output_root=output_root,
        )
        conflict_fields = {
            key: value for key, value in conflict.items() if key not in {"status", "reason"}
        }
        payload = _stage_payload(status="contested", selected=selected, rejected=rejected, reason=str(exc), **conflict_fields)
        _write_json(output_root / "knowledge_promotion.json", payload)
        return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--knowledge-write-root", type=Path)
    args = parser.parse_args(argv)
    result = promote_from_history(
        history_root=args.history_root,
        output_root=args.output,
        knowledge_write_root=args.knowledge_write_root,
    )
    print(json.dumps({"status": result.get("status"), "output": str(args.output)}, ensure_ascii=True))
    return 0 if result.get("status") == "promoted" else 2


if __name__ == "__main__":
    raise SystemExit(main())
