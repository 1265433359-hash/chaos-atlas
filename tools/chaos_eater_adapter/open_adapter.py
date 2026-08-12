"""Supplementary open-discovery adapter for the extracted ChaosEater prompt.

This class intentionally has no candidate-pool argument. It is labeled
`ChaosEater-adapter-open` in outputs and cannot stand in for the official
ChaosEater runtime.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from chaos_eater_adapter.llm_backend import LLMBackend
from open_discovery_compiler import RuntimeContract, compile_output
from open_discovery_prompts import CHAOSEATER_OPEN_SYSTEM, CHAOSEATER_OPEN_USER, OPEN_OUTPUT_SCHEMA


def _extract_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", stripped, re.DOTALL | re.IGNORECASE)
    if fenced:
        stripped = fenced.group(1).strip()
    start, end = stripped.find("{"), stripped.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("completion does not contain a JSON object")
    value = json.loads(stripped[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("completion root must be an object")
    return value


@dataclass
class OpenAdapterResult:
    raw_output: dict[str, Any]
    compiled: dict[str, Any]
    backend_meta: dict[str, Any]


class ChaosEaterOpenAdapter:
    """Run the open prompt and compile hypotheses without a pool restriction."""

    method_id = "ChaosEater-adapter-open"

    def __init__(self, backend: LLMBackend, max_hypotheses: int = 8) -> None:
        self.backend = backend
        self.max_hypotheses = max_hypotheses

    def propose(self, project_evidence: str, runtime_contract_text: str, contract: RuntimeContract) -> OpenAdapterResult:
        user_prompt = CHAOSEATER_OPEN_USER.format(
            project_evidence=project_evidence,
            runtime_contract=runtime_contract_text,
            output_schema=OPEN_OUTPUT_SCHEMA,
            max_hypotheses=self.max_hypotheses,
        )
        system_prompt = CHAOSEATER_OPEN_SYSTEM
        raw, metadata = self.backend.complete(system_prompt, user_prompt, OPEN_OUTPUT_SCHEMA)
        output = _extract_object(raw)
        output.setdefault("method_id", self.method_id)
        compiled = compile_output(output, contract)
        compiled["method_id"] = self.method_id
        return OpenAdapterResult(raw_output=output, compiled=compiled, backend_meta=metadata)
