"""Deterministic identity and overlap auditing for Sock Shop hypotheses.

This module is intentionally offline. It does not inspect runtime outcomes when
selecting representatives and it never invokes kubectl or an LLM.
"""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

import yaml


KIND_ALIASES = {
    "podchaos": "PodChaos",
    "pod-chaos": "PodChaos",
    "networkchaos": "NetworkChaos",
    "network-chaos": "NetworkChaos",
    "stresschaos": "StressChaos",
    "stress-chaos": "StressChaos",
    "httpchaos": "HTTPChaos",
    "http-chaos": "HTTPChaos",
    "dnschaos": "DNSChaos",
    "dns-chaos": "DNSChaos",
    "schedule": "Schedule",
    "workflow": "Workflow",
}

ACTION_ALIASES = {
    "kill": "pod-kill",
    "podkill": "pod-kill",
    "pod-kill": "pod-kill",
    "failure": "pod-failure",
    "podfailure": "pod-failure",
    "pod-failure": "pod-failure",
    "network-delay": "delay",
    "net-delay": "delay",
    "http-delay": "http-delay",
    "network-loss": "loss",
    "net-loss": "loss",
    "network-partition": "partition",
    "net-partition": "partition",
    "cpu-stress": "cpu",
    "stress-cpu": "cpu",
    "memory-stress": "memory",
    "stress-memory": "memory",
}

CALL_CHAIN_ALIASES = {
    "business service": "business-service",
    "business_service": "business-service",
    "data dependency": "data-dependency",
    "data_dependency": "data-dependency",
    "supporting service": "supporting-service",
    "supporting_service": "supporting-service",
    "entry point": "entry",
    "entry-point": "entry",
}


def normalize_kind(value: Any) -> str:
    text = str(value or "").strip()
    return KIND_ALIASES.get(text.lower(), text)


def _normal_token(value: Any) -> str:
    return "-".join(str(value or "").strip().lower().replace("_", "-").split())


def normalize_action(kind: Any, action: Any, mutation: dict[str, Any] | None = None) -> str:
    normalized_kind = normalize_kind(kind)
    source = mutation or {}
    spec = source.get("spec") or {}
    if normalized_kind in {"Schedule", "Workflow"}:
        spec = spec.get("podChaos") or spec.get("workflow") or spec
    candidate = action or spec.get("action") or spec.get("target")
    if normalized_kind == "StressChaos":
        stressors = spec.get("stressors") or {}
        if "cpu" in stressors:
            candidate = "cpu"
        elif "memory" in stressors:
            candidate = "memory"
    if normalized_kind == "DNSChaos" and not candidate:
        candidate = "dns"
    token = _normal_token(candidate)
    return ACTION_ALIASES.get(token, token)


def normalize_target(hypothesis: dict[str, Any], mutation: dict[str, Any] | None = None) -> str:
    if mutation:
        spec = mutation.get("spec") or {}
        if normalize_kind(mutation.get("kind")) in {"Schedule", "Workflow"}:
            spec = spec.get("podChaos") or spec.get("workflow") or spec
        selector = spec.get("selector") or {}
        labels = selector.get("labelSelectors") or {}
        for key in ("name", "app", "app.kubernetes.io/name"):
            if labels.get(key):
                return _normal_token(labels[key]).removesuffix("-service")
    value = hypothesis.get("target_service") or hypothesis.get("target") or "unknown"
    return _normal_token(value).removesuffix("-service")


def normalize_call_chain_position(value: Any) -> str:
    token = _normal_token(value)
    return CALL_CHAIN_ALIASES.get(token, token or "unknown")


def _canonical_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value).strip()


def _flatten(value: Any, prefix: str, output: list[tuple[str, str]]) -> None:
    if isinstance(value, dict):
        for key in sorted(value):
            _flatten(value[key], f"{prefix}.{key}" if prefix else str(key), output)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _flatten(item, f"{prefix}[{index}]", output)
    else:
        output.append((prefix, _canonical_scalar(value)))


def normalized_parameters(mutation: dict[str, Any]) -> str:
    """Return stable semantic parameters, excluding generated metadata."""
    kind = normalize_kind(mutation.get("kind"))
    spec = deepcopy(mutation.get("spec") or {})
    if kind in {"Schedule", "Workflow"}:
        nested = spec.get("podChaos") or spec.get("workflow")
        if isinstance(nested, dict):
            spec = {key: value for key, value in spec.items() if key not in {"podChaos", "workflow"}}
            spec["nested"] = nested
    flattened: list[tuple[str, str]] = []
    _flatten(spec, "spec", flattened)
    return "|".join(f"{key}={value}" for key, value in flattened)


def fault_family_key(hypothesis: dict[str, Any], mutation: dict[str, Any]) -> str:
    kind = normalize_kind(mutation.get("kind"))
    action = normalize_action(kind, hypothesis.get("action_or_target"), mutation)
    target = normalize_target(hypothesis, mutation)
    position = normalize_call_chain_position(hypothesis.get("call_chain_position"))
    return "|".join(
        (
            f"kind={kind}",
            f"action={action}",
            f"target={target}",
            f"call_chain_position={position}",
        )
    )


def mutation_instance_key(hypothesis: dict[str, Any], mutation: dict[str, Any]) -> str:
    return f"{fault_family_key(hypothesis, mutation)}|parameters={normalized_parameters(mutation)}"


def _structurally_complete(record: dict[str, Any]) -> bool:
    hypothesis = record.get("hypothesis") or {}
    mutation = record.get("mutation") or {}
    return bool(
        hypothesis.get("target_service")
        and hypothesis.get("action_or_target")
        and hypothesis.get("call_chain_position")
        and normalize_kind(mutation.get("kind"))
        and isinstance(mutation.get("spec"), dict)
    )


def _confidence(record: dict[str, Any]) -> float:
    hypothesis = record.get("hypothesis") or {}
    for key in ("confidence", "confidence_score", "score"):
        value = hypothesis.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    stop_snapshot = hypothesis.get("stop_snapshot") or {}
    upper95 = stop_snapshot.get("upper95")
    if isinstance(upper95, (int, float)):
        return max(0.0, min(1.0, 1.0 - float(upper95)))
    return float("nan")


def _confidence_source(record: dict[str, Any]) -> str:
    hypothesis = record.get("hypothesis") or {}
    if any(isinstance(hypothesis.get(key), (int, float)) for key in ("confidence", "confidence_score", "score")):
        return "explicit_hypothesis_confidence"
    if isinstance((hypothesis.get("stop_snapshot") or {}).get("upper95"), (int, float)):
        return "stop_posterior_complement"
    return "unavailable"


def _representative_record(record: dict[str, Any], method: str, reason: str) -> dict[str, Any]:
    selected = deepcopy(record)
    selected["method"] = method
    selected["fault_family_key"] = fault_family_key(selected["hypothesis"], selected["mutation"])
    selected["mutation_instance_key"] = mutation_instance_key(selected["hypothesis"], selected["mutation"])
    selected["selection_reason"] = reason
    selected["structurally_complete"] = _structurally_complete(selected)
    selected["confidence_available"] = not math.isnan(_confidence(selected))
    selected["confidence_score"] = None if math.isnan(_confidence(selected)) else round(_confidence(selected), 6)
    selected["confidence_source"] = _confidence_source(selected)
    return selected


def select_method_representatives(records: Iterable[dict[str, Any]], *, method: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        family = fault_family_key(record["hypothesis"], record["mutation"])
        grouped.setdefault(family, []).append(record)

    result: list[dict[str, Any]] = []
    for family in sorted(grouped):
        members = grouped[family]
        if method == "native-full":
            def full_sort_key(item: dict[str, Any]) -> tuple[int, float, int, int]:
                score = _confidence(item)
                has_score = not math.isnan(score)
                return (
                    0 if has_score else 1,
                    -score if has_score else 0.0,
                    -int(item.get("evidence_completeness") or (item.get("hypothesis") or {}).get("evidence_completeness") or 0),
                    int(item.get("source_order", 0)),
                )

            selected = sorted(members, key=full_sort_key)[0]
            reasons = "highest_confidence_then_evidence_then_first_order"
        else:
            complete = [item for item in members if _structurally_complete(item)]
            selected = min(complete or members, key=lambda item: int(item.get("source_order", 0)))
            reasons = "first_structurally_complete_generation"
        representative = _representative_record(selected, method, reasons)
        representative["family_size"] = len(members)
        representative["family_members"] = [
            {
                "hypothesis_id": (member.get("hypothesis") or {}).get("id"),
                "source_order": member.get("source_order"),
                "mutation_instance_key": mutation_instance_key(member["hypothesis"], member["mutation"]),
            }
            for member in sorted(members, key=lambda item: int(item.get("source_order", 0)))
        ]
        result.append(representative)
    return result


def partition_method_sets(
    full_records: Iterable[dict[str, Any]],
    ablation_records: Iterable[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    def ensure_identity(record: dict[str, Any]) -> dict[str, Any]:
        if record.get("fault_family_key") and record.get("mutation_instance_key"):
            return record
        return _representative_record(
            record,
            str(record.get("method") or "unknown"),
            "identity_attached_during_partition",
        )

    full_records = [ensure_identity(record) for record in full_records]
    ablation_records = [ensure_identity(record) for record in ablation_records]
    full = {_record_key(record): record for record in full_records}
    ablation = {_record_key(record): record for record in ablation_records}
    full_families = {record["fault_family_key"]: record for record in full.values()}
    ablation_families = {record["fault_family_key"]: record for record in ablation.values()}
    full_instances = {record["mutation_instance_key"]: record for record in full.values()}
    ablation_instances = {record["mutation_instance_key"]: record for record in ablation.values()}

    family_overlap = []
    for key in sorted(full_families.keys() & ablation_families.keys()):
        family_overlap.append({"fault_family_key": key, "full": full_families[key], "ablation": ablation_families[key]})
    strict_overlap = []
    for key in sorted(full_instances.keys() & ablation_instances.keys()):
        strict_overlap.append({"mutation_instance_key": key, "full": full_instances[key], "ablation": ablation_instances[key]})

    return {
        "family_overlap": family_overlap,
        "strict_overlap": strict_overlap,
        "full_only": [full_families[key] for key in sorted(full_families.keys() - ablation_families.keys())],
        "ablation_only": [ablation_families[key] for key in sorted(ablation_families.keys() - full_families.keys())],
    }


def _record_key(record: dict[str, Any]) -> str:
    return str(record.get("fault_family_key") or fault_family_key(record["hypothesis"], record["mutation"]))


def _resolve_candidate_path(plan_path: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_file():
        return candidate
    from_cwd = Path.cwd() / candidate
    if from_cwd.is_file():
        return from_cwd
    from_plan = plan_path.parent / candidate
    if from_plan.is_file():
        return from_plan
    raise FileNotFoundError(f"runtime mutation path does not exist: {raw_path}")


def load_runtime_candidates(plan_path: Path, *, method: str) -> dict[str, Any]:
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    method_data = (payload.get("methods") or {}).get(method) or {}
    candidates = []
    blocked_candidates = []
    referenced: set[Path] = set()
    for order, candidate in enumerate(method_data.get("candidates") or []):
        if not candidate.get("path"):
            blocked_candidates.append({"source_order": order, "runtime_candidate": candidate})
            continue
        path = _resolve_candidate_path(plan_path, str(candidate["path"]))
        referenced.add(path.resolve())
        content = path.read_bytes()
        actual_sha = hashlib.sha256(content).hexdigest()
        expected_sha = candidate.get("sha256")
        if expected_sha and expected_sha != actual_sha:
            raise ValueError(f"mutation SHA-256 mismatch: {path}")
        mutation = yaml.safe_load(content.decode("utf-8"))
        if not isinstance(mutation, dict):
            raise ValueError(f"mutation is not a YAML mapping: {path}")
        hypothesis = candidate.get("hypothesis") or {
            "id": candidate.get("hypothesis_id"),
            "target_service": candidate.get("target_service"),
            "action_or_target": candidate.get("action_or_target"),
            "call_chain_position": candidate.get("call_chain_position"),
            "category": candidate.get("category"),
        }
        candidates.append(
            {
                "method": method,
                "hypothesis": hypothesis,
                "mutation": mutation,
                "source_order": order,
                "source_path": str(path),
                "mutation_sha256": actual_sha,
                "runtime_candidate": candidate,
            }
        )
    mutation_root = plan_path.parent / "methods" / method / "mutations"
    if not mutation_root.is_dir():
        mutation_root = Path(candidates[0]["source_path"]).parent if candidates else plan_path.parent
    all_mutations = {path.resolve() for path in mutation_root.rglob("*.yaml")}
    ignored = sorted(str(path) for path in all_mutations - referenced)
    return {
        "method": method,
        "candidates": candidates,
        "blocked_candidates": blocked_candidates,
        "ignored_mutation_files": len(ignored),
        "ignored_paths": ignored,
    }


def load_method_records(discovery_path: Path, runtime_plan_path: Path, *, method: str) -> dict[str, Any]:
    discovery = json.loads(discovery_path.read_text(encoding="utf-8"))
    hypotheses = {str(item.get("id")): item for item in discovery.get("hypotheses") or []}
    runtime = load_runtime_candidates(runtime_plan_path, method=method)
    records = []
    for candidate in runtime["candidates"]:
        hypothesis = candidate["hypothesis"]
        if hypothesis.get("id") in hypotheses:
            hypothesis = hypotheses[hypothesis["id"]]
        records.append({**candidate, "hypothesis": hypothesis})
    runtime["records"] = records
    runtime["discovery_status"] = discovery.get("status")
    runtime["discovery_path"] = str(discovery_path)
    return runtime
