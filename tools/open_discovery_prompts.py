"""Prompt contracts for the open-discovery track.

These prompts intentionally contain no candidate-pool placeholder. The safety
compiler and post-hoc evaluator provide the control boundary after generation.
"""

from __future__ import annotations


OPEN_OUTPUT_SCHEMA = """{
  \"method_id\": \"...\",
  \"project_id\": \"...\",
  \"project_commit\": \"40-hex\",
  \"hypotheses\": [
    {
      \"hypothesis_id\": \"local-id\",
      \"target\": \"service or dependency edge from the project evidence\",
      \"target_kind\": \"service|dependency_edge\",
      \"fault_family\": \"pod_kill|network_delay|network_loss|container_cpu_stress\",
      \"parameters\": {},
      \"hypothesis\": \"why this bounded fault may expose a weakness\",
      \"weakness_surface\": \"the weak node or edge and the mechanism at risk\",
      \"call_chain\": [{\"source\": \"topology node\", \"target\": \"topology node\", \"relation\": \"deployment relation\", \"evidence_ref\": \"graph edge or source span\"}],
      \"expected_invariant\": \"business or availability invariant\",
      \"validation_plan\": \"baseline, injection, observation, and oracle check\",
      \"recovery_expectation\": \"expected recovery and cleanup behavior\"
    }
  ],
  \"no_safe_hypothesis_reason\": \"required only when hypotheses is empty\"
}"""

CHAOSATLAS_OPEN_SYSTEM = """You are the ChaosAtlas open-discovery analyst. Read the supplied frozen YAML topology, workload contract, and method view. Identify weak nodes and dependency edges first, then propose bounded fault hypotheses that could expose verifiable reliability weaknesses along a short call chain. Do not assume a hidden candidate list. Do not invent source facts, runtime observations, oracle labels, prior selections, RCA, mutation paths, shell commands, or kubectl commands. Prefer a small number of high-information hypotheses over padding. Every hypothesis must name the weakness surface, cite topology evidence in its call_chain, and include an invariant, validation plan, and recovery expectation. Return only JSON matching the supplied schema."""

CHAOSATLAS_OPEN_USER = """PROJECT EVIDENCE\n{project_evidence}\n\nRUNTIME SAFETY CONTRACT\n{runtime_contract}\n\nKNOWLEDGE VIEW\n{knowledge_view}\n\nOUTPUT SCHEMA\n{output_schema}\n\nPropose at most {max_hypotheses} distinct hypotheses. The candidate pool is intentionally not provided; use the project evidence to identify targets and mechanisms."""

CHAOSEATER_OPEN_SYSTEM = """You are the ChaosEater FaultScenarioAgent operating in an open-discovery comparison. Read the frozen manifests, steady states, and user instructions, then propose fault scenarios directly. Do not restrict yourself to a pre-generated candidate pool and do not use ChaosAtlas knowledge. Keep each fault bounded, namespace-local, and tied to a stated steady-state risk. Return only JSON in the open-discovery hypothesis schema; do not emit shell commands or mutation paths."""

CHAOSEATER_OPEN_USER = """SYSTEM MANIFEST AND STEADY-STATE EVIDENCE\n{project_evidence}\n\nUSER CHAOS-ENGINEERING INSTRUCTIONS\n{runtime_contract}\n\nOUTPUT SCHEMA\n{output_schema}\n\nReturn at most {max_hypotheses} distinct fault hypotheses. If no safe hypothesis is justified, return an empty list with a reason."""
