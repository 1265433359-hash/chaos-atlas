"""FaultScenario data structures extracted from ChaosEater.

Faithful to `chaos_eater/hypothesis/faults/llm_agents/fault_scenario_agent.py`
(commit 47c4e44) but implemented with plain dataclasses so the adapter has no
pydantic/langchain dependency. Field descriptions below mirror the original
LLMField descriptions so the extraction stays auditable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Enumeration from ChaosMesh.FACTORY_MAP in chaos_eater/ce_tools/chaosmesh/chaosmesh.py.
FAULT_TYPE_NAMES: list[str] = [
    "PodChaos",
    "NetworkChaos",
    "DNSChaos",
    "HTTPChaos",
    "StressChaos",
    "IOChaos",
    "TimeChaos",
]

FAULT_TYPE_DESCRIPTIONS: dict[str, str] = {
    "PodChaos": "simulates Pod failures, such as Pod node restart, Pod's persistent unavailability, and certain container failures in a specific Pod (subtypes: pod-kill, container-kill)",
    "NetworkChaos": "simulates network failures, such as network latency, packet loss, packet disorder, and network partitions",
    "DNSChaos": "simulates DNS failures, such as the parsing failure of DNS domain name and the wrong IP address returned",
    "HTTPChaos": "simulates HTTP communication failures, such as HTTP communication latency",
    "StressChaos": "simulates CPU race or memory race",
    "IOChaos": "simulates the I/O failure of an application file, such as I/O delays, read and write failures",
    "TimeChaos": "simulates the time jump exception",
}


@dataclass
class Fault:
    """A single fault injection, mirroring ChaosEater's Fault model."""

    name: str  # one of FAULT_TYPE_NAMES
    name_id: int  # identifier to prevent name conflicts, starting from 0
    scope: dict[str, str]  # injection scope, e.g. {"candidate_id": "OB-PAYMENT-DELAY-2000"}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Fault":
        return cls(
            name=str(value.get("name", "")),
            name_id=int(value.get("name_id", 0)),
            scope={str(key): str(item) for key, item in (value.get("scope") or {}).items()},
        )


@dataclass
class FaultScenario:
    """A sequence of fault injections, mirroring ChaosEater's FaultScenario model."""

    event: str  # assumed real-world fault event
    thought: str  # reasoning behind the injection sequence
    faults: list[list[Fault]] = field(default_factory=list)  # inner = simultaneous, outer = order

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "FaultScenario":
        faults: list[list[Fault]] = []
        for parallel in value.get("faults") or []:
            faults.append([Fault.from_dict(item) for item in parallel if isinstance(item, dict)])
        return cls(
            event=str(value.get("event", "")),
            thought=str(value.get("thought", "")),
            faults=faults,
        )
