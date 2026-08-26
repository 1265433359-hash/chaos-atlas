from __future__ import annotations

import json

import pytest

from tools.llm_rca_assistant import build_messages, parse_analysis_output


def _case() -> dict:
    return {
        "weakness_id": "WS-demo-api-pod-kill",
        "project_id": "demo",
        "round_id": "r1",
        "test_node": {"target": "deployment:api", "target_role": "api deployment"},
        "symptom": {"oracle": "GET /", "observed_change": "request failed"},
        "hypotheses": [{"hypothesis_id": "h-api", "claim": "API depends on a single pod", "scope": {"edge": "deployment:api"}}],
    }


def _evidence() -> list[dict]:
    return [{
        "evidence_id": "EV-1", "kind": "runtime_log", "polarity": "supports",
        "claim_scope": "deployment:api", "source_ref": "logs/api.log", "sha256": "a" * 64,
        "window": {"start": "2026-08-20T00:00:00Z", "end": "2026-08-20T00:01:00Z"},
        "interpretation": "API logged connection failure",
    }]


def test_build_messages_contains_redacted_case_and_forbids_verdict_authority():
    system, user = build_messages(_case(), _evidence())
    payload = json.loads(user)
    assert "must not decide RCA status" in system
    assert payload["evidence"][0]["sha256"] == "a" * 64
    assert payload["output_schema"]["hypotheses"][0]["missing_evidence"] == "list[str]"


def test_parse_analysis_accepts_structured_mechanism_without_verdict():
    raw = json.dumps({
        "hypotheses": [{
            "hypothesis_id": "h-api",
            "mechanism": "the API process loses its dependency connection",
            "supports": ["EV-1"],
            "contradicts": [],
            "missing_evidence": ["scoped request-to-log correlation"],
            "next_actions": ["collect scoped API logs"],
        }],
        "global_missing_evidence": ["recovery evidence"],
    })
    result = parse_analysis_output(raw, allowed_hypothesis_ids={"h-api"}, allowed_scopes={"deployment:api"}, allowed_evidence_ids={"EV-1"})
    assert result["hypotheses"][0]["supports"] == ["EV-1"]
    assert "rca_status" not in result


@pytest.mark.parametrize("field", ["rca_status", "knowledge_status", "runtime_verdict", "kubectl_command"])
def test_parse_analysis_rejects_authoritative_or_execution_fields(field: str):
    raw = json.dumps({"hypotheses": [], field: "confirmed"})
    with pytest.raises(ValueError, match="forbidden"):
        parse_analysis_output(raw, allowed_hypothesis_ids=set(), allowed_scopes=set())


def test_parse_analysis_rejects_unknown_hypothesis_or_evidence_reference():
    raw = json.dumps({"hypotheses": [{"hypothesis_id": "unknown", "mechanism": "x", "supports": ["EV-X"], "contradicts": [], "missing_evidence": [], "next_actions": []}]})
    with pytest.raises(ValueError):
        parse_analysis_output(raw, allowed_hypothesis_ids={"h-api"}, allowed_scopes={"deployment:api"}, allowed_evidence_ids={"EV-1"})
