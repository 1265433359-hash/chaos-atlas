"""Select auditable Train Ticket chaos candidates without applying mutations."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("PyYAML is required") from exc


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"JSON root is not an object: {path}")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix().replace("\\", "/")


def load_cards(root: Path) -> list[dict[str, Any]]:
    index = load_json(root / "index.json")
    cards: list[dict[str, Any]] = []
    for entry in index.get("cards", []):
        if not isinstance(entry, dict):
            continue
        path = root / str(entry.get("path", ""))
        if path.exists():
            try:
                card = load_json(path)
            except (OSError, json.JSONDecodeError, ValueError):
                continue
            card["_index_entry"] = entry
            cards.append(card)
    return cards


def load_runtime_index(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"records": []}
    return load_json(path)


def card_matches(card: dict[str, Any], kind: str, service: str | None) -> bool:
    node = card.get("test_node") or {}
    if node.get("family") != kind:
        return False
    label = ((node.get("selector") or {}).get("label") or {}).get("app")
    return service is None or label == service


def card_summary(card: dict[str, Any]) -> dict[str, Any]:
    node = card.get("test_node") or {}
    entry = card.get("_index_entry") or {}
    return {
        "id": card.get("id"),
        "version": card.get("version"),
        "status": card.get("status"),
        "evidence_state": card.get("evidence_state"),
        "runtime_status": entry.get("runtime_status"),
        "business_path_status": entry.get("business_path_status"),
        "injection_recommendation": entry.get("injection_recommendation"),
        "selector_app": ((node.get("selector") or {}).get("label") or {}).get("app"),
        "next_evidence": card.get("next_evidence", []),
    }


def runtime_matches(records: list[dict[str, Any]], service: str, node: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for record in records:
        record_node = record.get("test_node")
        if record_node and record_node != node:
            continue
        target_service = record.get("target_service")
        if target_service is not None:
            # Current records are exact service evidence. The branch below is
            # deliberately reserved for legacy records that predate the
            # target_service field; it must never fuzzy-match an explicit
            # service mismatch.
            if target_service == service:
                matches.append(record)
            continue
        record_id = str(record.get("id", ""))
        service_token = service.replace("ts-", "").replace("-service", "").upper()
        if service.lower() in record_id.lower() or service_token in record_id.upper():
            matches.append(record)
        elif node == "network_delay" and "NETWORK" in record_id.upper() and "BASIC" in service_token:
            matches.append(record)
        elif node == "stress_cpu" and "STRESS" in record_id.upper() and "ORDER" in service_token:
            matches.append(record)
    return matches


def mutation_constraints(kind: str, node: str, service: str) -> dict[str, Any]:
    constraints: dict[str, Any] = {
        "namespace": "train-ticket-lab",
        "mode": "one",
        "selector": {"labelSelectors": {"app": service}},
        "duration": "bounded_and_explicit",
        "require_runner": "tools/run_chaos_experiment.py",
        "require_injection_status": "status.experiment.containerRecords[].injectedCount >= 1",
        "require_recovery_status": "recoveredCount >= injectedCount",
    }
    if kind == "NetworkChaos" and node == "network_delay":
        constraints.update(
            {
                "action": "delay",
                "direction": "to",
                "first_profile": "100ms-500ms",
                "boundary_profile": "only after baseline and timeout budget are known",
            }
        )
    elif kind == "StressChaos" and node == "stress_cpu":
        constraints.update(
            {
                "stressor": "cpu",
                "first_profile": {"workers": 1, "load_percent": 80, "duration": "45s"},
                "strong_profile": {"workers": 4, "load_percent": 100, "duration": "60s"},
                "observation": "cgroup-v2 cpu.stat plus read-only request and readiness",
            }
        )
    elif kind == "HTTPChaos":
        constraints.update(
            {
                "platform_gate": "HTTP tproxy/ebtables must pass before apply",
                "first_profile": "single read-only endpoint, response status or delay only",
            }
        )
    return constraints


def primary_test_node(nodes: set[str] | list[str]) -> str:
    """Return a stable representative node for a slice.

    The generic 'selector' node is skipped when a business-specific node is
    present (e.g. 'stress_cpu', 'network_delay'), so runtime-evidence matching
    and candidate output are not misdirected to the generic node. Ordering is
    deterministic regardless of set iteration order.
    """
    ordered = sorted(nodes)
    if len(ordered) > 1 and "selector" in ordered:
        ordered = [value for value in ordered if value != "selector"]
    return ordered[0] if ordered else ""


def score_candidate(
    slice_item: dict[str, Any],
    cards: list[dict[str, Any]],
    runtime_records: list[dict[str, Any]],
) -> tuple[int, str, list[str], list[dict[str, Any]]]:
    kind = str(slice_item.get("kind", ""))
    nodes = sorted(set(slice_item.get("test_nodes") or []))
    service = ((slice_item.get("selector") or {}).get("labels") or {}).get("app", "")
    matching_cards = [card for card in cards if card_matches(card, kind, service)]
    # Use a stable representative when a slice has multiple abstract nodes;
    # set iteration must not affect candidate ranking.
    primary_node = primary_test_node(nodes)
    matching_runtime = runtime_matches(runtime_records, service, primary_node)
    score = 0
    reasons: list[str] = []
    decision = "needs_runtime_gate"
    if slice_item.get("target_matches"):
        score += 25
        reasons.append("selector matches a project Deployment")
    if slice_item.get("service_matches"):
        score += 15
        reasons.append("selector matches a project Service")
    if slice_item.get("function_candidates"):
        score += 15
        reasons.append("static function candidates exist")
    if slice_item.get("blast_radius_flag"):
        score -= 10
        reasons.append("raw sample carries blast-radius warning; use bounded mutation")
    for card in matching_cards:
        status = str(card.get("status", ""))
        evidence = str(card.get("evidence_state", ""))
        recommendation = str((card.get("_index_entry") or {}).get("injection_recommendation", ""))
        if evidence == "runtime_observed":
            score += 30
            reasons.append(f"runtime knowledge card {card.get('id')} exists")
            if "timeout_boundary_confirmed" in status or recommendation.startswith("stop_"):
                decision = "closed_runtime_boundary_no_reinjection"
                reasons.append("runtime knowledge closes this boundary; retain for retrieval but do not reinject")
            else:
                decision = "ready_candidate_with_runner"
        elif "static_only" in evidence or "not_reachable" in json.dumps(card, ensure_ascii=True):
            score -= 45
            reasons.append(f"knowledge card {card.get('id')} defers the current business path")
            decision = "defer_unreachable_or_unproven_path"
        elif "blocked" in status:
            score -= 50
            reasons.append(f"knowledge card {card.get('id')} is platform-blocked")
            decision = "blocked_by_platform_prerequisite"
    if matching_runtime:
        reasons.append("runtime classification evidence exists for this service family")
    if not matching_cards and service:
        reasons.append("no service-specific runtime card; baseline and applicability gate are required")
    if not service:
        decision = "defer_missing_selector"
        score -= 60
        reasons.append("selector does not identify an app label")
    return score, decision, reasons, [card_summary(card) for card in matching_cards]


def select_candidates(
    slices: list[dict[str, Any]],
    node: str | None,
    kind: str | None,
    service: str | None,
    limit: int,
    cards: list[dict[str, Any]],
    runtime_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for slice_item in slices:
        nodes = set(slice_item.get("test_nodes") or [])
        if node and node not in nodes:
            continue
        if kind and slice_item.get("kind") != kind:
            continue
        app = ((slice_item.get("selector") or {}).get("labels") or {}).get("app")
        if service and app != service:
            continue
        # Stable representative for the slice's own test nodes; set iteration
        # order must not leak into candidate output.
        primary_node = primary_test_node(nodes)
        score, decision, reasons, card_summaries = score_candidate(slice_item, cards, runtime_records)
        source_path = ROOT / str(slice_item.get("source", "")).replace("\\", "/")
        raw: dict[str, Any] = {}
        if source_path.exists():
            try:
                loaded = yaml.safe_load(source_path.read_text(encoding="utf-8"))
                raw = loaded if isinstance(loaded, dict) else {}
            except yaml.YAMLError:
                raw = {}
        selected.append(
            {
                "rank_score": score,
                "decision": decision,
                "reasons": reasons,
                "test_id": slice_item.get("test_id"),
                "test_nodes": slice_item.get("test_nodes", []),
                "kind": slice_item.get("kind"),
                "source_yaml": rel(source_path),
                "source_sha256": sha256(source_path) if source_path.exists() else None,
                "raw_name": ((raw.get("metadata") or {}).get("name")),
                "raw_namespace": ((raw.get("metadata") or {}).get("namespace")),
                "target_app": app,
                "static_slice": {
                    "target_matches": len(slice_item.get("target_matches") or []),
                    "service_matches": len(slice_item.get("service_matches") or []),
                    "function_candidates": len(slice_item.get("function_candidates") or []),
                    "code_modules": slice_item.get("code_module_candidates", []),
                    "blast_radius_flag": bool(slice_item.get("blast_radius_flag")),
                },
                "knowledge_cards": card_summaries,
                "runtime_matches": runtime_matches(runtime_records, app or "", primary_node),
                "mutation_constraints": mutation_constraints(str(slice_item.get("kind")), primary_node, app or ""),
            }
        )
    selected.sort(key=lambda item: (-int(item["rank_score"]), str(item.get("test_id"))))
    for index, item in enumerate(selected[: max(0, limit)], start=1):
        item["rank"] = index
    return selected[: max(0, limit)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", help="normalized test node such as network_delay or stress_cpu")
    parser.add_argument("--kind", help="Chaos Mesh kind filter")
    parser.add_argument("--service", help="app label filter")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--slices", type=Path, default=ROOT / "artifacts/train-ticket/train_ticket_test_slices_graph.json")
    parser.add_argument("--catalog", type=Path, default=ROOT / "artifacts/train-ticket/test_node_catalog.json")
    parser.add_argument("--knowledge-root", type=Path, default=ROOT / "artifacts/train-ticket/knowledge_base")
    parser.add_argument("--runtime-index", type=Path, default=ROOT / "artifacts/train-ticket/runtime/classification_index.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    slices_doc = load_json(args.slices)
    catalog = load_json(args.catalog)
    cards = load_cards(args.knowledge_root)
    runtime_index = load_runtime_index(args.runtime_index)
    slices = slices_doc.get("slices") or []
    candidates = select_candidates(
        slices,
        args.node,
        args.kind,
        args.service,
        args.limit,
        cards,
        runtime_index.get("records") or [],
    )
    report = {
        "schema_version": 1,
        "tool": "select_chaos_candidates",
        "project": slices_doc.get("project"),
        "commit": slices_doc.get("commit"),
        "selection_policy": {
            "center": "test_node",
            "static_evidence": "selector -> target -> function candidates",
            "runtime_evidence": "knowledge card and classification index",
            "safety_rule": "This report proposes candidates only; use run_chaos_experiment.py for injection.",
            "decision_labels": [
                "ready_candidate_with_runner",
                "closed_runtime_boundary_no_reinjection",
                "needs_runtime_gate",
                "defer_unreachable_or_unproven_path",
                "blocked_by_platform_prerequisite",
                "defer_missing_selector",
            ],
        },
        "filters": {"node": args.node, "kind": args.kind, "service": args.service, "limit": args.limit},
        "catalog_context": {
            "source_file_count": (catalog.get("source") or {}).get("file_count"),
            "node_count": len(catalog.get("nodes") or []),
        },
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
