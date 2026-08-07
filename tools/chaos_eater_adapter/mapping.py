"""Mapping between ChaosEater fault types and the shared candidate pool.

ChaosEater selects among its seven fault-type enumerations; our shared pool is
a fixed list of concrete candidates (one mutation each). This module maps each
candidate to its ChaosEater fault type and renders the pool in a prompt-ready
form, so the LLM's type-level reasoning can be resolved back to candidate ids.
"""

from __future__ import annotations

from typing import Any

from chaos_eater_adapter.schemas import FAULT_TYPE_NAMES

# ChaosEater fault type -> candidate fault families in the shared pool.
FAULT_FAMILY_BY_TYPE: dict[str, set[str]] = {
    "PodChaos": {"pod_kill", "container_kill"},
    "NetworkChaos": {"latency", "packet_loss", "partition", "unavailable"},
    "HTTPChaos": {"http_delay", "http_error"},
    "StressChaos": {"cpu_stress", "memory_stress"},
    "DNSChaos": {"dns"},
    "IOChaos": {"io"},
    "TimeChaos": {"time"},
}

# Inverse lookup for resolving a candidate's family back to a ChaosEater type.
FAMILY_TO_TYPE: dict[str, str] = {}
for _fault_type, _families in FAULT_FAMILY_BY_TYPE.items():
    for _family in _families:
        FAMILY_TO_TYPE[_family] = _fault_type


def fault_type_of(candidate: dict[str, Any]) -> str:
    """ChaosEater fault type for a candidate, defaulting to NetworkChaos."""
    family = str(candidate.get("fault_family", ""))
    return FAMILY_TO_TYPE.get(family, "NetworkChaos")


def fault_family_of(fault_type: str) -> str:
    """Canonical fault family for a ChaosEater fault type (first family)."""
    families = sorted(FAULT_FAMILY_BY_TYPE.get(fault_type, set()))
    return families[0] if families else "latency"


def build_candidate_pool(candidates: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Render the shared candidate pool for the prompt.

    Each entry keeps the candidate id, its ChaosEater fault type, the target
    service/edge, and intensity so the LLM can reason over the same information
    tier (I0) that M0 uses, without leaking our static graph scores.
    """
    pool: list[dict[str, str]] = []
    for candidate in candidates:
        pool.append(
            {
                "candidate_id": str(candidate["candidate_id"]),
                "fault_type": fault_type_of(candidate),
                "fault_family": str(candidate.get("fault_family", "")),
                "service": str(candidate.get("service", "")),
                "edge": str(candidate.get("edge", "")),
                "intensity": str(candidate.get("intensity", "")),
                "duration": str(candidate.get("duration", "")),
            }
        )
    return pool


def candidate_fault_type_list() -> str:
    """Fault-type enumeration block for the system prompt (I0 information)."""
    lines = [
        "- Candidate faults belong to the following Chaos Mesh fault types: "
        + ", ".join(FAULT_TYPE_NAMES)
        + "."
    ]
    return "\n".join(lines)


def find_candidate(pool: list[dict[str, str]], candidate_id: str) -> dict[str, str] | None:
    for entry in pool:
        if entry["candidate_id"] == candidate_id:
            return entry
    return None
