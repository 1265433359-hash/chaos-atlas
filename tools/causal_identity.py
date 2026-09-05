"""Canonical identity helpers for experiment de-duplication."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _text(value: Any) -> str:
    return str(value or "").strip().lower()


def _oracle_id(value: Any) -> str:
    if isinstance(value, dict):
        return _text(value.get("id") or value.get("workflow") or value.get("name"))
    return _text(value)


def _contract_id(value: Any) -> str:
    if isinstance(value, dict):
        return _text(value.get("id") or value.get("name") or value.get("type"))
    return _text(value)


def _parameter_domain(candidate: dict[str, Any]) -> str:
    family = _text(candidate.get("fault_family"))
    parameters = candidate.get("parameters") or {}
    if family in {"network_delay", "network_loss"}:
        return "latency_ms" if family == "network_delay" else "loss_percent"
    if family == "stress_cpu":
        return "cpu_load"
    if family == "stress_memory":
        return "memory_size"
    if family == "network_bandwidth":
        return "bandwidth_rate"
    if family in {"network_duplicate", "network_corrupt"}:
        return "packet_mutation_percent"
    if family == "dns_delay":
        return "latency_ms"
    if family == "pod_kill":
        return "replica_disruption"
    keys = sorted(str(key) for key in parameters if str(key) not in {"duration_s", "duration"})
    return keys[0] if keys else "none"


def canonical_causal_identity(candidate: dict[str, Any]) -> dict[str, str]:
    return {
        "source": _text(candidate.get("source") or (candidate.get("causal_identity") or {}).get("source")),
        "target": _text(candidate.get("target") or (candidate.get("causal_identity") or {}).get("target")),
        "target_kind": _text(candidate.get("target_kind") or (candidate.get("causal_identity") or {}).get("target_kind")),
        "fault_family": _text(candidate.get("fault_family") or (candidate.get("causal_identity") or {}).get("fault_family")),
        "oracle": _oracle_id(candidate.get("business_oracle") or candidate.get("oracle") or (candidate.get("causal_identity") or {}).get("oracle")),
        "recovery_contract": _contract_id(candidate.get("recovery_contract") or (candidate.get("causal_identity") or {}).get("recovery_contract")),
        "parameter_domain": _parameter_domain(candidate),
    }


def causal_cluster_id(candidate: dict[str, Any]) -> str:
    identity = canonical_causal_identity(candidate)
    raw = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()
