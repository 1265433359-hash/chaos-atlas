from __future__ import annotations

import json

import pytest

from tools.deepseek_advisory import (
    DeepSeekAdvisoryProvider,
    build_advisory_messages,
    read_deepseek_api_key,
)


def _payload() -> dict:
    return {
        "project_id": "demo",
        "inventory": {
            "project_id": "demo",
            "project_commit": "a" * 40,
            "namespace": "demo-lab",
            "deployments": [{"name": "api", "desired_replicas": 1, "ready_replicas": 1}],
            "secrets": [{"password": "must-not-leave"}],
        },
        "server_deployment_detection": {"status": "verified", "capability_name": "server_deployment_detection"},
        "candidate_space": {"candidates": [{"candidate_id": "candidate-1", "target": "api", "fault_family": "pod_kill"}]},
        "knowledge_view": [{"id": "KB-1", "status": "local_reusable", "test_node": {"family": "pod_kill"}}],
    }


def test_read_deepseek_api_key_requires_explicit_source(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("CHAOS_EATER_API_KEY", raising=False)

    with pytest.raises(ValueError, match="API key"):
        read_deepseek_api_key(None)

    key_file = tmp_path / "deepseek.key"
    key_file.write_text("  test-key-123  \n", encoding="utf-8")
    assert read_deepseek_api_key(key_file) == "test-key-123"


def test_build_advisory_messages_allowlists_runtime_facts() -> None:
    system, user = build_advisory_messages(_payload())

    assert "must not decide" in system
    assert "at most 8" in system
    assert "compact" in system
    assert "must-not-leave" not in user
    assert "candidate-1" in user
    assert "output_schema" in user


def test_provider_returns_structured_advisory_metadata_without_key() -> None:
    class Backend:
        name = "openai-compatible:deepseek-v4-flash"

        def complete(self, system: str, user: str, format_instructions: str):
            assert "must-not-leave" not in user
            return json.dumps({
                "hypotheses": [{
                    "candidate_id": "candidate-1",
                    "mechanism": "single replica replacement may interrupt availability",
                    "expected_observations": ["business oracle may fail during replacement"],
                    "missing_evidence": ["recovery window"],
                    "next_actions": ["collect scoped events"],
                }],
                "global_missing_evidence": ["independent recovery evidence"],
            }), {"backend": "test", "model": "deepseek-v4-flash"}

    provider = DeepSeekAdvisoryProvider(Backend())
    result = provider(_payload())

    assert result["hypotheses"][0]["candidate_id"] == "candidate-1"
    assert result["advisory_metadata"]["model"] == "deepseek-v4-flash"
    assert "api_key" not in json.dumps(result, ensure_ascii=True).lower()


def test_provider_accepts_fenced_json_response() -> None:
    class Backend:
        def complete(self, system: str, user: str, format_instructions: str):
            return (
                "Here is the bounded advisory:\n```json\n"
                + json.dumps({
                    "hypotheses": [],
                    "global_missing_evidence": [],
                })
                + "\n```",
                {"backend": "test", "model": "deepseek-v4-flash"},
            )

    result = DeepSeekAdvisoryProvider(Backend())(_payload())

    assert result["hypotheses"] == []
    assert result["advisory_metadata"]["backend"] == "test"
