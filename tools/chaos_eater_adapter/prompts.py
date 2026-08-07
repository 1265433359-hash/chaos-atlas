"""Prompt templates extracted from ChaosEater's FaultScenarioAgent.

`SYS_ASSUME_FAULT_SCENARIOS` and `USER_ASSUME_FAULT_SCENARIOS` are adapted from
`chaos_eater/hypothesis/faults/llm_agents/fault_scenario_agent.py` (commit
47c4e44). Two changes are made on top of the faithful prompt:
- the fault types enumeration is replaced by the shared candidate pool, so the
  LLM ranks candidates that already map onto M0/M3/M4 mutations;
- an explicit "choose exactly N distinct candidates" instruction enforces the
  same candidate budget as the other methods.
"""

from __future__ import annotations

SYS_ASSUME_FAULT_SCENARIOS = """\
You are a helpful AI assistant for Chaos Engineering.
Given k8s manifests for a system, the steady states of the system, and user's instructions for Chaos Engineering, you will select and rank the most impactful fault injections from a candidate pool to reveal potential weaknesses of the system, such as insufficient recovery functions, resource allocation, redundancy, etc.
Always keep the following rules:
- First, assume a real-world event that may be most impactful in the system, such as promotion campaign, cyber attacks, disasters, etc.
- Then, select the most impactful fault injections from the candidate pool to reveal potential weaknesses of the given system while simulating the assumed real-world event.
- Prioritize fault injections that target the system's weak resources related to the steady states to verify whether those resources can handle the faults and the steady states can be maintained.
- The injected faults must be selected from the candidate pool; do not invent faults outside the pool.
{candidate_fault_types}
- {format_instructions}"""

USER_ASSUME_FAULT_SCENARIOS = """\
Here is the overview of my system:
{user_input}

Steady states of the network system defined by the manifests are the following:
{steady_states}

Please follow the instructions below regarding Chaos Engineering as necessary:
{ce_instructions}

Candidate pool of fault injections (each candidate is one mutation targeting a specific service/edge):
{candidate_pool}

Now, please select and rank exactly {candidate_budget} distinct candidates from the pool to reveal the system's vulnerabilities, ordered from most impactful to least impactful."""

FORMAT_INSTRUCTIONS = """\
Respond with a single JSON object (no markdown, no code fences) with this schema:
{
  "event": "a real-world fault event that may be most impactful of the system, such as promotion campaign, cyber attacks, disasters, etc.",
  "thought": "your thought process: 1) how the system's weaknesses affect the steady state; 2) how each chosen candidate exploits the system's weaknesses; 3) how the ordered selection simulates the phenomena in the fault event.",
  "faults": [
    [{"name": "one of the candidate fault types", "name_id": 0, "scope": {"candidate_id": "<candidate id from the pool>", "service": "<target service>"}}],
    [{"name": "...", "name_id": 1, "scope": {"candidate_id": "...", "service": "..."}}]
  ]
}
The inner list holds simultaneously injected faults; the outer list is the injection order. Each selected candidate appears at most once."""
