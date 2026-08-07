"""ChaosEater adapter: candidate selection extracted from the ChaosEater workflow.

The adapter keeps ChaosEater's core selection logic — the FaultScenarioAgent
prompt, the fault-type enumeration, and the FaultScenario output structure —
without its docker-compose / langchain / full agent-loop infrastructure. The
LLM backend is pluggable (OpenAI-compatible chat completion, or a deterministic
mock for pipeline verification), and its output is mapped onto the shared
candidate pool used by M0/M3/M4 so results stay comparable.
"""

from chaos_eater_adapter.adapter import ChaosEaterAdapter
from chaos_eater_adapter.llm_backend import LLMBackend, MockBackend, OpenAICompatBackend
from chaos_eater_adapter.mapping import build_candidate_pool, fault_family_of
from chaos_eater_adapter.prompts import SYS_ASSUME_FAULT_SCENARIOS, USER_ASSUME_FAULT_SCENARIOS
from chaos_eater_adapter.schemas import FAULT_TYPE_NAMES, Fault, FaultScenario

__all__ = [
    "ChaosEaterAdapter",
    "LLMBackend",
    "MockBackend",
    "OpenAICompatBackend",
    "build_candidate_pool",
    "fault_family_of",
    "SYS_ASSUME_FAULT_SCENARIOS",
    "USER_ASSUME_FAULT_SCENARIOS",
    "FAULT_TYPE_NAMES",
    "Fault",
    "FaultScenario",
]
