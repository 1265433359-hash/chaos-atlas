"""Build a redacted, cross-project ChaosAtlas full-v2 knowledge projection."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


RUNTIME_STATES = {"runtime_observed", "verified", "runtime_verified"}
PROJECT_ALIASES = {
    "online-boutique": ("online-boutique", "microservices-demo", "googlecloudplatform/microservices-demo"),
    "opentelemetry-demo": ("opentelemetry-demo", "open-telemetry/opentelemetry-demo", "otel"),
    "sock-shop": ("sock-shop", "microservices-demo/sock-shop"),
}
FORBIDDEN_OUTPUT_TERMS = (
    "candidate_id",
    "candidate_pool",
    "mutation_path",
    "runtime_observation",
    "post_run_rca",
    "oracle_label",
    "raw_yaml",
    "mutation_yaml",
    "source_yaml",
)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _runtime_validated(card: dict[str, Any]) -> bool:
    state = str(card.get("evidence_state", "")).lower()
    status = str(card.get("status", "")).lower()
    return state in RUNTIME_STATES and ("validated_runtime" in status or status in {"verified", "runtime_verified"})


def _fault_family(test_node: dict[str, Any]) -> str:
    family = str(test_node.get("family", "")).lower()
    operation = str(test_node.get("operation", "")).lower()
    if "network" in family and "delay" in operation and "loss" in operation:
        return "network_delay_or_loss"
    if "network" in family and "delay" in operation:
        return "network_delay"
    if "network" in family and "loss" in operation:
        return "network_loss"
    if "pod" in family:
        return "pod_kill"
    if "stress" in family and "memory" in operation:
        return "container_memory_stress"
    if "stress" in family:
        return "container_cpu_stress"
    if "http" in family:
        return "http_response_fault"
    if "dns" in family:
        return "dns_fault"
    if "time" in family:
        return "time_offset"
    return "bounded_fault"


def _role_for_kind(kind: str) -> str:
    normalized = kind.lower()
    if normalized == "testnode":
        return "test_node"
    if normalized in {"entrypoint", "ingress", "gateway"}:
        return "entrypoint"
    if normalized in {"targetdeployment", "targetworkload", "workload"}:
        return "workload"
    if normalized in {"controllerpath", "controller"}:
        return "controller_path"
    if normalized in {"businessexecution", "serviceexecution"}:
        return "business_execution"
    if normalized in {"downstreamcall", "outboundcall"}:
        return "synchronous_downstream_call"
    if normalized in {"asyncqueue", "queue", "messagequeue", "messaging"}:
        return "async_queue"
    if normalized in {"statestore", "database", "datastore", "cache"}:
        return "state_store"
    if normalized in {"networkedge", "dependencyedge"}:
        return "dependency_edge"
    if normalized in {"businessoutcome", "response"}:
        return "business_outcome"
    if normalized == "observation":
        return "observation"
    if normalized == "recovery":
        return "recovery"
    return "component"


def _graph_roles(graph: dict[str, Any]) -> list[str]:
    nodes = {str(node.get("id")): _role_for_kind(str(node.get("kind", ""))) for node in graph.get("nodes", []) if isinstance(node, dict)}
    edges = [edge for edge in graph.get("edges", []) if isinstance(edge, dict)]
    adjacency: dict[str, list[str]] = {}
    for edge in edges:
        source = str(edge.get("from", ""))
        target = str(edge.get("to", ""))
        if source in nodes and target in nodes:
            adjacency.setdefault(source, []).append(target)
    for targets in adjacency.values():
        targets.sort()
    starts = sorted(node_id for node_id, role in nodes.items() if role == "test_node")
    if not starts:
        return []

    def paths(node_id: str, visited: set[str]) -> list[list[str]]:
        if node_id in visited:
            return [[nodes[node_id]]]
        next_nodes = [target for target in adjacency.get(node_id, []) if target not in visited]
        if not next_nodes:
            return [[nodes[node_id]]]
        candidates: list[list[str]] = []
        for target in next_nodes:
            for suffix in paths(target, visited | {node_id}):
                candidates.append([nodes[node_id], *suffix])
        return candidates

    candidates = paths(starts[0], set())
    candidates.sort(key=lambda path: (path[-1] != "business_outcome", -len(path), path))
    role_path = candidates[0]
    deduplicated: list[str] = []
    for role in role_path:
        if not deduplicated or deduplicated[-1] != role:
            deduplicated.append(role)
    return deduplicated


def _target_role(graph: dict[str, Any]) -> str:
    nodes = {str(node.get("id")): _role_for_kind(str(node.get("kind", ""))) for node in graph.get("nodes", []) if isinstance(node, dict)}
    for edge in graph.get("edges", []):
        if not isinstance(edge, dict):
            continue
        source_role = nodes.get(str(edge.get("from")))
        target_role = nodes.get(str(edge.get("to")))
        if source_role == "test_node" and target_role:
            return target_role
    return "unknown_target"


def _raw_classification(card: dict[str, Any]) -> str:
    runtime_result = card.get("runtime_result")
    if isinstance(runtime_result, dict) and runtime_result.get("classification"):
        return str(runtime_result["classification"])
    result = card.get("result_classification")
    if isinstance(result, dict):
        value = result.get("classification")
        if value:
            return str(value)
    return "observed_effect_unspecified"


def _normalized_outcomes(raw: str) -> list[str]:
    text = raw.lower()
    outcomes: set[str] = set()
    if any(term in text for term in ("platform", "blocked", "prerequisite", "injection_blocked")):
        outcomes.add("platform_blocked")
    if any(term in text for term in ("no_business_impact", "no business impact")):
        outcomes.add("no_business_impact_observed")
    if any(term in text for term in ("preserved", "succeeded", "success", "graceful")):
        outcomes.add("business_response_preserved")
    if any(term in text for term in ("latency", "delay", "propagation", "slow", "degraded")):
        outcomes.add("latency_degradation")
    if any(term in text for term in ("deadline", "timeout", "hang", "infinite_hang")):
        outcomes.add("client_timeout")
    if any(term in text for term in ("server_completion_after", "server completion", "server-side business log")):
        outcomes.add("server_completion_after_client_timeout")
    if any(term in text for term in ("grpc", "rpc_error")):
        outcomes.add("grpc_error")
    if any(term in text for term in ("connection", "transport", "restart_race")):
        outcomes.add("transport_failure")
    if any(term in text for term in ("cascade", "fatal", "failure")) and "platform" not in text:
        outcomes.add("cascade_failure")
    if not outcomes:
        outcomes.add("observation_incomplete")
    return sorted(outcomes)


def _duration_class(test_node: dict[str, Any]) -> str:
    duration = str(test_node.get("duration", "")).strip().lower()
    if not duration:
        return "unspecified_duration"
    if duration.endswith(("s", "m", "ms")):
        return "bounded_duration"
    return "custom_duration"


def _chain_properties(path: list[str], target_role: str) -> dict[str, Any]:
    sync_count = path.count("synchronous_downstream_call")
    return {
        "critical_path": "business_outcome" in path,
        "sync_boundary": sync_count > 0,
        "async_boundary": "async_queue" in path,
        "stateful_dependency": "state_store" in path,
        "fanout": "single_or_repeated" if sync_count <= 1 else "repeated_synchronous",
        "target_position": target_role,
    }


def _safe_card_projection(card: dict[str, Any]) -> dict[str, Any]:
    if not _runtime_validated(card):
        raise ValueError("only runtime-validated cards may enter full-v2 projection")
    test_node = card.get("test_node")
    graph = card.get("test_node_centered_graph")
    if not isinstance(test_node, dict) or not isinstance(graph, dict):
        raise ValueError("runtime-validated card requires test_node and test_node_centered_graph")
    return {
        "fault_family": _fault_family(test_node),
        "target_role": _target_role(graph),
        "operation": str(test_node.get("operation", "unspecified")),
        "direction": str(test_node.get("direction", "unspecified")),
        "mode": str(test_node.get("mode", "unspecified")),
        "duration_class": _duration_class(test_node),
        "observed_outcomes": _normalized_outcomes(_raw_classification(card)),
        "chain_roles": _graph_roles(graph),
    }


def _negative_evidence(card: dict[str, Any]) -> dict[str, Any]:
    state = str(card.get("evidence_state") or card.get("status") or "unverified").lower()
    status = str(card.get("status") or "unverified").lower()
    raw = f"{status} {state} {_raw_classification(card)}"
    return {
        "evidence_state": "pending_review" if "pending" in status else state,
        "outcome": _normalized_outcomes(raw)[0],
        "outcomes": _normalized_outcomes(raw),
        "usage": "boundary_only_not_positive_runtime_rule",
    }


def _historical_support(historical_catalog: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(historical_catalog, dict):
        return []
    support: list[dict[str, Any]] = []
    for node in historical_catalog.get("nodes", []):
        if not isinstance(node, dict):
            continue
        name = str(node.get("node", "")).lower()
        family = {
            "network_delay": "network_delay",
            "network_loss": "network_loss",
            "pod_pod-kill": "pod_kill",
            "stress_cpu": "container_cpu_stress",
            "stress_memory": "container_memory_stress",
            "http_replace_response": "http_response_fault",
            "time_offset": "time_offset",
            "dns": "dns_fault",
        }.get(name)
        if not family:
            continue
        kind_counts = node.get("kind_counts") if isinstance(node.get("kind_counts"), dict) else {}
        support.append(
            {
                "fault_family": family,
                "document_count": int(node.get("document_count") or 0),
                "chaos_kind_counts": {str(k): int(v) for k, v in sorted(kind_counts.items()) if isinstance(v, int)},
                "evidence": "static_corpus_pattern_only",
                "usage_boundary": "ranking_prior_only_not_runtime_proof",
            }
        )
    return sorted(support, key=lambda item: (-item["document_count"], item["fault_family"]))


def _source_hashes(cards: list[dict[str, Any]]) -> list[str]:
    return sorted(_sha256(card) for card in cards)


def build_projection(cards: Iterable[dict[str, Any]], *, historical_catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    card_list = list(cards)
    normalized = [_safe_card_projection(card) for card in card_list if _runtime_validated(card)]
    if not normalized:
        raise ValueError("at least one runtime-validated card is required")
    negative = [_negative_evidence(card) for card in card_list if not _runtime_validated(card)]

    node_patterns = sorted({
        (
            item["fault_family"],
            item["target_role"],
            item["direction"],
            item["mode"],
            item["duration_class"],
        )
        for item in normalized
    })
    test_node_rules = [
        {
            "when": {
                "target_role": target_role,
                "direction": direction,
                "mode": mode,
                "duration_class": duration_class,
            },
            "fault": fault_family,
            "evidence": "runtime_observed",
            "runtime_support_count": sum(
                1
                for item in normalized
                if (
                    item["fault_family"],
                    item["target_role"],
                    item["direction"],
                    item["mode"],
                    item["duration_class"],
                )
                == (fault_family, target_role, direction, mode, duration_class)
            ),
        }
        for fault_family, target_role, direction, mode, duration_class in node_patterns
    ]

    chain_groups: dict[tuple[tuple[str, ...], str, bool, bool, bool, str], dict[str, Any]] = {}
    for item in normalized:
        props = _chain_properties(item["chain_roles"], item["target_role"])
        key = (
            tuple(item["chain_roles"]),
            props["fanout"],
            props["sync_boundary"],
            props["async_boundary"],
            props["stateful_dependency"],
            props["target_position"],
        )
        group = chain_groups.setdefault(key, {"outcomes": set(), "support": 0})
        group["support"] += 1
        group["outcomes"].update(item["observed_outcomes"])
    call_chain_rules = []
    for (roles, fanout, sync_boundary, async_boundary, stateful_dependency, target_position), group in sorted(chain_groups.items()):
        call_chain_rules.append(
            {
                "path": list(roles),
                "properties": {
                    "critical_path": "business_outcome" in roles,
                    "sync_boundary": sync_boundary,
                    "async_boundary": async_boundary,
                    "stateful_dependency": stateful_dependency,
                    "fanout": fanout,
                    "target_position": target_position,
                },
                "observed_outcomes": sorted(group["outcomes"]),
                "evidence": "runtime_observed",
                "runtime_support_count": group["support"],
            }
        )

    applicability_groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in normalized:
        key = (item["fault_family"], item["target_role"], item["direction"])
        group = applicability_groups.setdefault(key, {"outcomes": set(), "support": 0})
        group["support"] += 1
        group["outcomes"].update(item["observed_outcomes"])
    fault_applicability_rules = [
        {
            "fault": fault_family,
            "applies_to": target_role,
            "conditions": {
                "direction": direction,
                "timeout_evidence": "unknown_or_absent_unless_card_proves_boundary",
                "retry_evidence": "unknown",
            },
            "expected_surfaces": sorted(group["outcomes"]),
            "validation": "validate_business_oracle_latency_boundary_cleanup_and_washout",
            "runtime_support_count": group["support"],
        }
        for (fault_family, target_role, direction), group in sorted(applicability_groups.items())
    ]

    outcome_counts: dict[str, int] = {}
    for item in normalized:
        for outcome in item["observed_outcomes"]:
            outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
    outcome_taxonomy = [
        {
            "outcome": outcome,
            "runtime_support_count": count,
            "meaning": {
                "business_response_preserved": "business contract remained successful while another surface may have changed",
                "latency_degradation": "latency increased relative to baseline or configured observation budget",
                "client_timeout": "client-side caller stopped waiting before normal completion",
                "server_completion_after_client_timeout": "server-side completion was observed after caller timeout",
                "grpc_error": "gRPC or RPC surface returned an error",
                "transport_failure": "transport connection failed or reset",
                "cascade_failure": "business failure propagated across the observed path",
                "no_business_impact_observed": "oracle stayed within the observed success boundary",
                "platform_blocked": "platform prerequisite prevented valid injection",
                "observation_incomplete": "evidence was insufficient for a more specific class",
            }.get(outcome, "generic normalized outcome"),
        }
        for outcome, count in sorted(outcome_counts.items())
    ]

    historical = _historical_support(historical_catalog)
    projection = {
        "schema_version": "chaosatlas-generic-knowledge-projection-v2",
        "human_review": "pending",
        "knowledge_base_updated": False,
        "source_scope": "cross_project_generic_only",
        "test_node_rules": test_node_rules,
        "call_chain_rules": call_chain_rules,
        "fault_applicability_rules": fault_applicability_rules,
        "outcome_taxonomy": outcome_taxonomy,
        "negative_evidence": negative,
        "historical_fault_pattern_support": historical,
        "evidence_boundaries": [
            "runtime_observed evidence supports the observed business or latency outcome only",
            "static call-chain position is not proof that a request executed on every path",
            "an observed outcome does not prove an internal timeout, retry, cache, discovery, or registration mechanism",
            "target-project history, pending review, and unverified candidates are excluded",
            "static corpus frequency is a ranking prior only and cannot create positive runtime rules",
        ],
        "provenance": {
            "source_card_count": len(card_list),
            "runtime_validated_card_count": len(normalized),
            "non_runtime_card_count": len(card_list) - len(normalized),
            "source_hashes": _source_hashes(card_list),
            "historical_catalog_file_count": int((historical_catalog or {}).get("source", {}).get("file_count") or 0)
            if isinstance(historical_catalog, dict)
            else 0,
            "projection_policy": "abstract roles and bounded applicability only; no project identifiers or executable artifacts",
        },
    }
    encoded = _canonical(projection)
    projection["projection_sha256"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    output = json.dumps(projection, ensure_ascii=True)
    if any(term in output.lower() for term in FORBIDDEN_OUTPUT_TERMS):
        raise ValueError("projection contains forbidden project/runtime fields")
    return projection


def _matches_project(card: dict[str, Any], project_id: str) -> bool:
    aliases = PROJECT_ALIASES.get(project_id, (project_id,))
    project = str(card.get("project", "")).lower()
    return any(alias.lower() in project for alias in aliases)


def build_leave_one_project_out_projection(
    cards: Iterable[dict[str, Any]],
    *,
    heldout_project_id: str,
    historical_catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a prompt-safe projection excluding cards from the held-out target project."""
    filtered = [card for card in cards if not _matches_project(card, heldout_project_id)]
    return build_projection(filtered, historical_catalog=historical_catalog)


def load_cards(paths: Iterable[Path]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for path in paths:
        value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        if not isinstance(value, dict):
            raise ValueError(f"knowledge card must be an object: {path}")
        cards.append(value)
    return cards


def load_cards_from_dirs(paths: Iterable[Path]) -> list[dict[str, Any]]:
    card_paths: list[Path] = []
    for path in paths:
        card_paths.extend(sorted(Path(path).glob("KB-*.json")))
    return load_cards(card_paths)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--card", type=Path, action="append", default=[])
    parser.add_argument("--card-dir", type=Path, action="append", default=[])
    parser.add_argument("--historical-catalog", type=Path)
    parser.add_argument("--heldout-project-id")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cards = [*load_cards(args.card), *load_cards_from_dirs(args.card_dir)]
    if not cards:
        raise ValueError("at least one --card or --card-dir is required")
    historical_catalog = None
    if args.historical_catalog:
        historical_catalog = json.loads(args.historical_catalog.read_text(encoding="utf-8-sig"))
    if args.heldout_project_id:
        projection = build_leave_one_project_out_projection(
            cards,
            heldout_project_id=args.heldout_project_id,
            historical_catalog=historical_catalog,
        )
    else:
        projection = build_projection(cards, historical_catalog=historical_catalog)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(projection, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "passed", "projection_sha256": projection["projection_sha256"]}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
