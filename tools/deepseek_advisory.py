"""DeepSeek advisory provider for bounded hypothesis generation."""

from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from tools.rca_loop import _contains_sensitive_value


def read_deepseek_api_key(api_key_file: Path | None = None) -> str:
    """Read a key from an explicit file or environment without exposing it."""

    if api_key_file is not None:
        path = Path(api_key_file)
        if not path.is_file():
            raise ValueError(f"DeepSeek API key file not found: {path}")
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
        raise ValueError("DeepSeek API key file is empty")
    for name in ("DEEPSEEK_API_KEY", "CHAOS_EATER_API_KEY"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    raise ValueError("DeepSeek API key is required via --api-key-file or DEEPSEEK_API_KEY")


def _deployment_fact(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    spec = value.get("spec") if isinstance(value.get("spec"), dict) else {}
    selector = value.get("selector") or spec.get("selector") or {}
    if isinstance(selector, dict) and isinstance(selector.get("matchLabels"), dict):
        selector = selector["matchLabels"]
    return {
        "name": value.get("name") or (value.get("metadata") or {}).get("name"),
        "desired_replicas": value.get("desired_replicas") or spec.get("replicas"),
        "ready_replicas": value.get("ready_replicas"),
        "selector": selector if isinstance(selector, dict) else {},
    }


def build_advisory_messages(payload: dict[str, Any]) -> tuple[str, str]:
    """Build a secret-free, candidate-bounded prompt for DeepSeek."""

    inventory = payload.get("inventory") if isinstance(payload.get("inventory"), dict) else {}
    candidates = payload.get("candidate_space", {}).get("candidates", [])
    candidate_view = []
    for item in candidates if isinstance(candidates, list) else []:
        if not isinstance(item, dict):
            continue
        candidate_view.append({
            key: item.get(key)
            for key in ("candidate_id", "target", "target_kind", "fault_family", "operation", "parameters", "static_prior", "applicability_plan", "recovery_expectation")
            if key in item
        })
    knowledge = []
    cards = payload.get("knowledge_view") if isinstance(payload.get("knowledge_view"), list) else []
    for card in cards:
        if not isinstance(card, dict):
            continue
        node = card.get("test_node") if isinstance(card.get("test_node"), dict) else {}
        knowledge.append({
            "id": card.get("id"),
            "status": card.get("status") or card.get("knowledge_status"),
            "test_node": {key: node.get(key) for key in ("family", "operation", "target", "target_kind") if key in node},
            "applicability_conditions": card.get("applicability_conditions", []),
            "next_evidence": card.get("next_evidence", []),
        })
    safe_payload = {
        "project_id": payload.get("project_id") or inventory.get("project_id"),
        "project_commit": inventory.get("project_commit"),
        "namespace": inventory.get("namespace"),
        "deployments": [_deployment_fact(item) for item in inventory.get("deployments", []) if isinstance(item, dict)],
        "services": [
            {key: item.get(key) for key in ("name", "port", "target_port", "selector") if key in item}
            for item in inventory.get("services", [])
            if isinstance(item, dict)
        ],
        "server_deployment_detection": {
            "status": (payload.get("server_deployment_detection") or {}).get("status"),
            "capability_name": (payload.get("server_deployment_detection") or {}).get("capability_name"),
        },
        "candidate_space": {"candidates": candidate_view},
        "knowledge_view": knowledge,
    }
    serialized = json.dumps(safe_payload, ensure_ascii=True, sort_keys=True)
    if _contains_sensitive_value(serialized):
        raise ValueError("advisory input contains sensitive values")
    system = (
        "You are the ChaosAtlas advisory hypothesis assistant. Use only the supplied project facts, "
        "candidate IDs and bounded knowledge view. Propose mechanisms, expected observations, missing "
        "evidence and next actions. You must not decide RCA status, knowledge status, runtime verdict, "
        "defense classification, or execute commands. Return compact JSON only: at most 8 hypotheses, "
        "each mechanism under 240 characters and each evidence/action list at most 3 items."
    )
    user = json.dumps({
        "input": safe_payload,
        "output_schema": {
            "hypotheses": [{
                "candidate_id": "existing candidate ID",
                "mechanism": "bounded mechanism hypothesis",
                "expected_observations": ["observable effect"],
                "missing_evidence": ["evidence still needed"],
                "next_actions": ["bounded evidence action"],
            }],
            "global_missing_evidence": ["evidence needed across candidates"],
        },
    }, indent=2, ensure_ascii=True)
    return system, user


def _safe_metadata(metadata: Any) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    allowed = {
        "backend", "model", "endpoint", "generation_time_ms", "prompt_tokens",
        "completion_tokens", "total_tokens", "finish_reason", "reasoning_content_chars",
    }
    return {key: deepcopy(metadata[key]) for key in sorted(allowed & set(metadata))}


def _decode_json_object(raw: Any) -> dict[str, Any]:
    """Decode JSON responses with the light formatting models commonly add."""
    text = str(raw).strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        if start < 0:
            raise
        value, _ = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(value, dict):
        raise ValueError("DeepSeek advisory response must be a JSON object")
    return value


class DeepSeekAdvisoryProvider:
    """Callable adapter returning only parseable advisory JSON."""

    def __init__(self, backend: Any) -> None:
        self.backend = backend
        self.last_metadata: dict[str, Any] = {}

    def __call__(self, payload: dict[str, Any]) -> dict[str, Any]:
        system, user = build_advisory_messages(payload)
        raw, metadata = self.backend.complete(
            system,
            user,
            "The response must be a JSON object matching output_schema and must use existing candidate IDs.",
        )
        value = _decode_json_object(raw)
        safe_metadata = _safe_metadata(metadata)
        value["advisory_metadata"] = safe_metadata
        self.last_metadata = safe_metadata
        return value


def create_deepseek_policy_provider(
    *,
    api_key_file: Path | None = None,
    base_url: str = "https://api.deepseek.com/v1",
    model: str = "deepseek-v4-flash",
    timeout: int = 180,
) -> Any:
    """Create the project-agnostic policy provider over DeepSeek."""

    api_key = read_deepseek_api_key(api_key_file)
    try:
        from tools.chaos_eater_adapter.llm_backend import OpenAICompatBackend
        from tools.llm_policy import OpenAICompatPolicyProvider
    except ModuleNotFoundError:
        from chaos_eater_adapter.llm_backend import OpenAICompatBackend
        from llm_policy import OpenAICompatPolicyProvider
    backend = OpenAICompatBackend(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout=timeout,
        json_mode=True,
        temperature=0.0,
        max_output_tokens=2200,
        disable_thinking=True,
    )
    return OpenAICompatPolicyProvider(backend)


def create_deepseek_advisory_provider(
    *,
    api_key_file: Path | None = None,
    base_url: str = "https://api.deepseek.com/v1",
    model: str = "deepseek-v4-flash",
    timeout: int = 180,
) -> DeepSeekAdvisoryProvider:
    """Create the explicit DeepSeek provider without persisting the key."""

    api_key = read_deepseek_api_key(api_key_file)
    try:
        from tools.chaos_eater_adapter.llm_backend import OpenAICompatBackend
    except ModuleNotFoundError:
        from chaos_eater_adapter.llm_backend import OpenAICompatBackend
    backend = OpenAICompatBackend(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout=timeout,
        json_mode=True,
        temperature=0.0,
        max_output_tokens=2600,
        disable_thinking=True,
    )
    return DeepSeekAdvisoryProvider(backend)
