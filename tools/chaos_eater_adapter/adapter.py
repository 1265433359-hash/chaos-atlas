"""ChaosEaterAdapter: extract the FaultScenarioAgent selection into a ranker.

The adapter mirrors the ChaosEater hypothesis stage (fault_scenario_agent)
without its surrounding infrastructure:

1. build the system prompt from the extracted templates plus the shared
   candidate pool (same 12 candidates M0/M3/M4 draw from);
2. ask the pluggable backend for a FaultScenario (event / thought / fault
   sequence), exactly as ChaosEater's FaultScenarioAgent does;
3. resolve the chosen fault scopes back to candidate ids, deduplicate, cap at
   the shared budget, and return the ranked candidates.

The backend metadata (model, tokens, backend identity) is surfaced verbatim in
the result so the provenance of every ranking stays auditable.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from chaos_eater_adapter.llm_backend import LLMBackend
from chaos_eater_adapter.mapping import build_candidate_pool
from chaos_eater_adapter.prompts import (
    FORMAT_INSTRUCTIONS,
    SYS_ASSUME_FAULT_SCENARIOS,
    USER_ASSUME_FAULT_SCENARIOS,
)
from chaos_eater_adapter.schemas import FaultScenario


def extract_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object out of a completion, tolerating markdown fences."""
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"no JSON object found in completion: {text[:200]!r}")
    value = json.loads(stripped[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("completion JSON root is not an object")
    return value


@dataclass
class AdapterResult:
    scenario: FaultScenario
    ranked_candidates: list[dict[str, Any]] = field(default_factory=list)
    backend_meta: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class ChaosEaterAdapter:
    def __init__(self, backend: LLMBackend, candidates: list[dict[str, Any]], budget: int = 10) -> None:
        self.backend = backend
        self.candidates = candidates
        self.budget = budget
        self.pool = build_candidate_pool(candidates)
        self._by_id = {entry["candidate_id"]: entry for entry in self.pool}

    def select(
        self,
        user_input: str,
        steady_states: str,
        ce_instructions: str,
        extra_context: str | None = None,
    ) -> AdapterResult:
        pool_lines = [
            "- " + json.dumps(entry, ensure_ascii=True, sort_keys=True) for entry in self.pool
        ]
        user_prompt = USER_ASSUME_FAULT_SCENARIOS.format(
            user_input=user_input,
            steady_states=steady_states,
            ce_instructions=ce_instructions,
            candidate_pool="\n".join(pool_lines),
            candidate_budget=self.budget,
        )
        if extra_context:
            user_prompt += f"\n\nAdditional analysis from our methodology:\n{extra_context}"
        system_prompt = SYS_ASSUME_FAULT_SCENARIOS.format(
            candidate_fault_types=self._fault_type_block(),
            format_instructions=FORMAT_INSTRUCTIONS,
        )
        started = time.perf_counter()
        raw_text, meta = self.backend.complete(system_prompt, user_prompt, FORMAT_INSTRUCTIONS)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        meta.setdefault("generation_time_ms", elapsed_ms)

        scenario = self._parse(raw_text)
        ranked: list[dict[str, Any]] = []
        warnings: list[str] = []
        seen: set[str] = set()
        for parallel in scenario.faults:
            for fault in parallel:
                candidate_id = str((fault.scope or {}).get("candidate_id", "")).strip()
                if not candidate_id:
                    continue
                if candidate_id not in self._by_id:
                    warnings.append(f"candidate not in pool, skipped: {candidate_id}")
                    continue
                if candidate_id in seen:
                    continue
                seen.add(candidate_id)
                ranked.append(self._candidate_record(candidate_id))
                if len(ranked) >= self.budget:
                    break
            if len(ranked) >= self.budget:
                break
        if len(ranked) < self.budget:
            warnings.append(
                f"only {len(ranked)}/{self.budget} distinct in-pool candidates selected; "
                "budget not padded (see protocol: no invented selections)"
            )
        return AdapterResult(
            scenario=scenario,
            ranked_candidates=ranked,
            backend_meta=meta,
            warnings=warnings,
        )

    def _parse(self, raw_text: str) -> FaultScenario:
        try:
            value = extract_json_object(raw_text)
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"could not parse FaultScenario from completion: {exc}") from exc
        return FaultScenario.from_dict(value)

    def _fault_type_block(self) -> str:
        types = sorted({entry["fault_type"] for entry in self.pool})
        return "- Candidate faults belong to the following fault types: " + ", ".join(types) + "."

    def _candidate_record(self, candidate_id: str) -> dict[str, Any]:
        entry = self._by_id[candidate_id]
        candidate = next(item for item in self.candidates if item["candidate_id"] == candidate_id)
        return {
            "candidate_id": candidate_id,
            "fault_type": entry["fault_type"],
            "service": entry["service"],
            "edge": entry["edge"],
            "intensity": entry["intensity"],
            "duration": entry["duration"],
            "invariant": candidate.get("invariant"),
            "root_cause": candidate.get("root_cause"),
            "mutation": candidate.get("mutation"),
        }
