"""Aggregate Dify trials and promote only confirmed RCA experiences."""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any

from tools.compile_rca_regression import compile_regression_intents
from tools.dify_adaptive_coverage import ANOMALY_RESULTS, MIN_REPETITIONS, inspect_trial
from tools.rca_loop import _contains_sensitive_value, evaluate_knowledge_promotion
from tools.reproduction_policy import STABLE_REPRODUCTION_STOP_RULE


ATTESTATION_FIELDS = ("baseline", "injection", "observation", "recovery", "cleanup", "independent_oracle")


def _payload(root: Path, name: str) -> dict[str, Any]:
    path = Path(root) / name
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    value = value.get("payload", value) if isinstance(value, dict) else {}
    return value if isinstance(value, dict) else {}


def _fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for name in ("classify.json", "observe.json", "rca_report.json", "cleanup_report.json", "knowledge_draft.json"):
        path = Path(root) / name
        digest.update(name.encode("utf-8"))
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"missing")
    return digest.hexdigest()


def _valid_confirmed_run(row: dict[str, Any]) -> dict[str, Any] | None:
    inspected = inspect_trial(row)
    if not inspected["valid"] or inspected["classification"] not in ANOMALY_RESULTS:
        return None
    root = Path(inspected["output"])
    classification = _payload(root, "classify.json") or _payload(root, "finding_report.json")
    rca = _payload(root, "rca_report.json")
    draft = _payload(root, "knowledge_draft.json")
    observe = _payload(root, "observe.json")
    cleanup = _payload(root, "cleanup_report.json")
    attestation = classification.get("attestation") or {}
    if not all(attestation.get(field) is True for field in ATTESTATION_FIELDS):
        return None
    if rca.get("rca_status") != "confirmed":
        return None
    transition = rca.get("transition") or {}
    if transition and transition.get("next_status") not in {None, "confirmed"}:
        return None
    hypotheses = rca.get("hypotheses") or []
    if not hypotheses or any(
        not isinstance(item, dict)
        or item.get("status") != "confirmed"
        or item.get("unsupported_claims")
        or not item.get("evidence_for")
        for item in hypotheses
    ):
        return None
    if not isinstance(observe.get("observation"), dict) or not (observe.get("observation") or {}).get("samples"):
        return None
    if cleanup.get("status") != "verified" or cleanup.get("errors"):
        return None
    manifest = _payload(root, "run_manifest.json")
    test_node = rca.get("test_node") or {}
    return {
        "row": row,
        "root": str(root),
        "run_id": str(manifest.get("run_id") or root.name),
        "seed": manifest.get("seed"),
        "fingerprint": _fingerprint(root),
        "classification": inspected["classification"],
        "rca": rca,
        "draft": draft,
        "test_node": test_node,
    }


def _markdown(card: dict[str, Any]) -> str:
    node = card.get("test_node") or {}
    evidence = card.get("evidence_runs") or []
    return "\n".join([
        f"# {card['id']}",
        "",
        f"- Project: `{card.get('project')}`",
        f"- Target: `{card.get('target')}`",
        f"- Fault: `{node.get('family')}`",
        f"- Parameter level: `{node.get('parameter_level', 'baseline')}`",
        f"- RCA status: `{card.get('rca_status')}`",
        f"- Valid reproductions: `{card.get('valid_reproductions')}`",
        "",
        "## Mechanism",
        "",
        str(card.get("mechanism_claim") or ""),
        "",
        "## Evidence",
        "",
        *[f"- `{item.get('run_id')}`: `{item.get('root')}`" for item in evidence],
        "",
        "## Boundaries",
        "",
        *[f"- {item}" for item in card.get("exclusion_conditions") or []],
        "",
    ])


def _build_card(runs: list[dict[str, Any]]) -> dict[str, Any]:
    first = runs[0]
    rca = first["rca"]
    draft = first["draft"]
    node = dict(first["test_node"])
    project = str(rca.get("project_id") or "dify-kubernetes")
    commit = str(rca.get("project_commit") or "runtime-unknown")
    target = str(node.get("target") or "")
    family = str(node.get("family") or "")
    parameters = node.get("parameters") or {}
    identity = json.dumps([project, commit, target, family, parameters], sort_keys=True, ensure_ascii=True)
    card_id = "KB-WEAK-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    promotion = evaluate_knowledge_promotion(
        current="provisional",
        weakness_status="confirmed",
        rca_status="confirmed",
        valid_reproductions=len(runs),
        valid_counterfactuals=0,
        lifecycle_complete=True,
        direct_evidence=all(item["rca"].get("evidence_refs") for item in runs),
        applicability_complete=True,
        regression_complete=True,
        contradiction=False,
    )
    if not promotion.get("allowed") or promotion.get("next_status") != "local_reusable":
        raise ValueError(f"knowledge promotion gate rejected evidence: {promotion}")
    card = {
        "schema_version": "chaosatlas-weakness-knowledge-v1",
        "id": card_id,
        "project": project,
        "project_commit": commit,
        "case_family": str(rca.get("case_family") or ""),
        "weakness_id": str(rca.get("weakness_id") or ""),
        "target": target,
        "target_kind": str(node.get("target_kind") or "deployment"),
        "classification": "availability_weakness",
        "weakness_status": "confirmed",
        "rca_status": "confirmed",
        "knowledge_status": "local_reusable",
        "mechanism_level": str((rca.get("hypotheses") or [{}])[0].get("mechanism_level") or "service_boundary"),
        "mechanism_claim": str((rca.get("hypotheses") or [{}])[0].get("claim") or "runtime degradation during the confirmed fault"),
        "test_node": node,
        "test_node_centered_graph": draft.get("test_node_centered_graph") or {"edge": target, "scope": {"target": target}},
        "four_layer_validation": draft.get("four_layer_validation") or {"availability": True, "contract": False, "business_path": True, "recovery": True},
        "applicability_conditions": sorted({condition for run in runs for condition in run["draft"].get("applicability_conditions") or []}) or ["same project and commit"],
        "exclusion_conditions": sorted({condition for run in runs for condition in run["draft"].get("exclusion_conditions") or []}),
        "evidence_runs": [
            {"run_id": run["run_id"], "seed": run["seed"], "run_fingerprint": run["fingerprint"], "root": run["root"], "evidence_refs": list(run["rca"].get("evidence_refs") or [])}
            for run in runs
        ],
        "valid_reproductions": len(runs),
        "counter_evidence": [],
        "promotion_audit": promotion,
        "next_evidence": sorted({item for run in runs for item in run["draft"].get("next_evidence") or []}) or ["repeat_business_oracle"],
        "stop_rule": STABLE_REPRODUCTION_STOP_RULE,
        "regression_recipe": {"oracle": (rca.get("symptom") or {}).get("oracle") or "Dify business oracle", "selected_next_action": None},
    }
    regression = compile_regression_intents([card], snapshot={"card": card, "run_ids": [run["run_id"] for run in runs]})
    card["regression_intents"] = regression["intents"]
    return card


def _refresh_knowledge_index(knowledge_root: Path) -> dict[str, Any]:
    """Write a deterministic index for the flat Dify weakness-card store."""

    entries: list[dict[str, Any]] = []
    for path in sorted(Path(knowledge_root).glob("KB-*.json")):
        try:
            card = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(card, dict) or not card.get("id"):
            continue
        node = card.get("test_node") if isinstance(card.get("test_node"), dict) else {}
        entries.append({
            "id": str(card["id"]),
            "path": path.name,
            "markdown_path": path.with_suffix(".md").name,
            "project": str(card.get("project") or ""),
            "target": str(card.get("target") or node.get("target") or ""),
            "fault_family": str(node.get("family") or ""),
            "parameter_level": str(node.get("parameter_level") or "baseline"),
            "knowledge_status": str(card.get("knowledge_status") or ""),
            "valid_reproductions": int(card.get("valid_reproductions") or 0),
        })
    index = {
        "schema_version": "chaosatlas-weakness-index-v1",
        "card_count": len(entries),
        "cards": entries,
    }
    Path(knowledge_root).mkdir(parents=True, exist_ok=True)
    (Path(knowledge_root) / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    return index


def promote_confirmed_experiences(
    *,
    rows: list[dict[str, Any]],
    output_root: Path,
    knowledge_root: Path,
    min_repetitions: int = MIN_REPETITIONS,
) -> dict[str, Any]:
    """Aggregate rows and install only confirmed weakness cards."""

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        candidate_id = str(row.get("candidate_id") or "")
        if candidate_id:
            grouped[candidate_id].append(row)
    promoted: list[str] = []
    rejected: list[dict[str, Any]] = []
    output_root = Path(output_root)
    knowledge_root = Path(knowledge_root)
    cards_root = output_root / "promotion_artifacts"
    for candidate_id, candidate_rows in sorted(grouped.items()):
        valid_runs = [run for run in (_valid_confirmed_run(row) for row in candidate_rows) if run is not None]
        fingerprints = {run["fingerprint"] for run in valid_runs}
        if len(valid_runs) < min_repetitions or len(fingerprints) < min_repetitions:
            rejected.append({"candidate_id": candidate_id, "reason": "confirmed_rca_3of3_required", "valid_confirmed_runs": len(valid_runs)})
            continue
        card = _build_card(valid_runs[:min_repetitions])
        text = json.dumps(card, indent=2, ensure_ascii=True) + "\n"
        if _contains_sensitive_value(text):
            raise ValueError(f"refusing to write sensitive card: {card['id']}")
        cards_root.mkdir(parents=True, exist_ok=True)
        knowledge_root.mkdir(parents=True, exist_ok=True)
        for root in (cards_root, knowledge_root):
            (root / f"{card['id']}.json").write_text(text, encoding="utf-8")
            (root / f"{card['id']}.md").write_text(_markdown(card), encoding="utf-8")
        promoted.append(card["id"])
    index = _refresh_knowledge_index(knowledge_root)
    report = {
        "schema_version": "chaosatlas-dify-experience-promotion-v1",
        "status": "completed",
        "min_repetitions": min_repetitions,
        "promoted_card_ids": promoted,
        "rejected_candidates": rejected,
        "knowledge_root": str(knowledge_root),
        "formal_knowledge_base_updated": bool(promoted),
        "knowledge_index": str(knowledge_root / "index.json"),
        "knowledge_index_card_count": index["card_count"],
    }
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "experience_promotion.json").write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return report
