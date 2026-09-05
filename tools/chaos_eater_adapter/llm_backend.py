"""Pluggable LLM backends for the ChaosEater adapter.

`LLMBackend` is the adapter's only interface to a language model. Two
implementations ship with the adapter:

- `OpenAICompatBackend`: talks to any OpenAI-compatible chat-completions
  endpoint (OpenAI, DeepSeek, or a local Ollama `http://host:11434/v1`), using
  only the standard library.
- `MockBackend`: a deterministic, seed-driven backend that emits a
  structurally valid FaultScenario JSON. It exists to verify the pipeline
  (prompt build -> parse -> map -> rank) without an LLM and to power tests. It
  deliberately does NOT use our static graph scores, so it is not a stand-in
  for real ChaosEater selection.
"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from typing import Any, Protocol

class LLMBackend(Protocol):
    name: str

    def complete(self, system: str, user: str, format_instructions: str) -> tuple[str, dict[str, Any]]:
        """Return (raw completion text, metadata) for the given messages.

        The metadata dict records observable facts such as the model name,
        token counts, and backend identity; it must never contain invented
        values.
        """
        ...


class OpenAICompatBackend:
    """Call an OpenAI-compatible /chat/completions endpoint with urllib."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: int = 180,
        json_mode: bool = True,
        temperature: float = 0.2,
        max_output_tokens: int | None = None,
        disable_thinking: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.json_mode = json_mode
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.disable_thinking = disable_thinking

    @property
    def name(self) -> str:
        return f"openai-compatible:{self.model}"

    def complete(self, system: str, user: str, format_instructions: str) -> tuple[str, dict[str, Any]]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"{user}\n\n{format_instructions}"},
            ],
            "temperature": self.temperature,
        }
        if self.max_output_tokens is not None:
            payload["max_tokens"] = self.max_output_tokens
        if self.json_mode:
            payload["response_format"] = {"type": "json_object"}
        if self.disable_thinking:
            payload["thinking"] = {"type": "disabled"}
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"LLM endpoint unreachable: {exc}") from exc
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        try:
            data = json.loads(raw)
            choice = data["choices"][0]
            message = choice["message"]
            content_value = message.get("content")
            content = str(content_value or "")
            usage = data.get("usage") or {}
            meta = {
                "backend": "openai-compatible",
                "model": self.model,
                "endpoint": self.base_url,
                "generation_time_ms": elapsed_ms,
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "finish_reason": choice.get("finish_reason"),
                "message_fields": sorted(message.keys()) if isinstance(message, dict) else [],
                "reasoning_content_chars": len(str(message.get("reasoning_content") or "")) if isinstance(message, dict) else 0,
            }
            return content, meta
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"unexpected LLM response shape: {exc}") from exc


class MockBackend:
    """Deterministic pipeline-verification backend.

    Selection rule (ChaosEater-flavored, not score-based): simulate the
    assumption step by drawing a fault event from a fixed template, then walk
    the candidate pool one fault type at a time (order seeded) so the selection
    favors type diversity, like ChaosEater's "most impactful across types"
    heuristic. Never reads our static graph scores.
    """

    _EVENTS = [
        "a promotional campaign drives a sudden traffic spike",
        "a regional network incident degrades inter-service connectivity",
        "an overloaded database replica causes cascading latency",
        "a rolling deployment partially fails and leaves replicas degraded",
        "a dependent third-party service becomes slow during a peak period",
    ]

    def __init__(self, seed: int, candidates: list[dict[str, Any]], budget: int = 10) -> None:
        self.seed = seed
        self.candidates = candidates
        self.budget = budget
        self._rng = random.Random(seed)

    @property
    def name(self) -> str:
        return f"mock:seed{self.seed}"

    def complete(self, system: str, user: str, format_instructions: str) -> tuple[str, dict[str, Any]]:
        # Keep the OpenAI-compatible backend usable when the optional
        # ChaosEater scenario modules are not installed.
        from chaos_eater_adapter.mapping import fault_type_of

        by_type: dict[str, list[dict[str, Any]]] = {}
        for candidate in self.candidates:
            fault_type = fault_type_of(candidate)
            by_type.setdefault(fault_type, []).append(candidate)
        type_order = list(by_type.keys())
        self._rng.shuffle(type_order)
        # Deterministic traversal across fault types; within a type, keep the
        # original pool order so the same seed always yields the same ranking.
        selected: list[dict[str, Any]] = []
        for fault_type in type_order:
            for candidate in by_type[fault_type]:
                if len(selected) >= self.budget:
                    break
                selected.append(candidate)
            if len(selected) >= self.budget:
                break
        if len(selected) < self.budget:
            for candidate in self.candidates:
                if len(selected) >= self.budget:
                    break
                if candidate not in selected:
                    selected.append(candidate)

        faults: list[dict[str, Any]] = []
        for index, candidate in enumerate(selected):
            faults.append(
                {
                    "name": fault_type_of(candidate),
                    "name_id": index,
                    "scope": {
                        "candidate_id": candidate["candidate_id"],
                        "service": candidate.get("service", ""),
                    },
                }
            )
        scenario = {
            "event": self._EVENTS[self._rng.randrange(len(self._EVENTS))],
            "thought": "mock backend: deterministic type-diverse selection for pipeline verification",
            "faults": [[fault] for fault in faults],
        }
        meta = {
            "backend": "mock",
            "model": f"mock-seed-{self.seed}",
            "generation_time_ms": 1,
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "note": "mock is a pipeline verifier, not a real ChaosEater selection",
        }
        return json.dumps(scenario, ensure_ascii=True), meta
