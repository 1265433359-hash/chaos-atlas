import json
import urllib.error

import tools.run_sock_shop_confidence_discovery as discovery
from tools.run_sock_shop_confidence_discovery import build_deepseek_body, parse_model_json, run_confidence_discovery


def _method_input(method: str, knowledge_allowed: bool) -> dict:
    return {
        "method": method,
        "knowledge_allowed": knowledge_allowed,
        "yaml_category_summary": {
            "categories": {
                "Network degradation": {
                    "min_hypotheses": 2,
                    "max_hypotheses": 2,
                    "tau": 0.05,
                    "coverage_target": 0.5,
                    "top_motifs": [{"motif": "action_or_target=delay"}],
                }
            }
        },
    }


def test_discovery_records_hypotheses_novelty_stop_trace_and_timing():
    calls = []

    def fake_model(payload: dict) -> dict:
        calls.append(payload)
        return {
            "hypothesis": {
                "target_service": "catalogue",
                "action_or_target": "delay",
                "call_chain_position": "business-service",
                "motifs": ["action_or_target=delay"],
            }
        }

    result = run_confidence_discovery(_method_input("native-full", True), fake_model)

    assert result["method"] == "native-full"
    assert result["status"] == "confidence_incomplete"
    assert result["knowledge_allowed"] is True
    assert len(result["hypotheses"]) == 2
    assert result["hypotheses"][0]["novel"] is True
    assert result["hypotheses"][1]["novel"] is False
    assert result["stopping"]["Network degradation"]["reason"] == "max_hypotheses"
    assert len(result["confidence_trace"]["Network degradation"]) == 2
    assert result["timing"]["generation_seconds"] >= 0
    assert calls[0]["knowledge_allowed"] is True


def test_ablation_model_payload_excludes_knowledge_projection():
    received = []

    def fake_model(payload: dict) -> dict:
        received.append(payload)
        return {
            "hypothesis": {
                "target_service": "front-end",
                "action_or_target": "delay",
                "call_chain_position": "entry",
                "motifs": [],
            }
        }

    method_input = _method_input("chaosatlas-ablation", False)
    method_input["knowledge_projection"] = {"must_not_reach_model": True}
    result = run_confidence_discovery(method_input, fake_model)

    assert result["knowledge_allowed"] is False
    assert "knowledge_projection" not in received[0]
    assert received[0]["knowledge_allowed"] is False


def test_parse_model_json_accepts_fenced_json():
    value = parse_model_json(
        """```json
{"hypothesis": {"target_service": "orders"}}
```"""
    )
    assert value["hypothesis"]["target_service"] == "orders"


def test_deepseek_body_requires_structured_hypothesis_object():
    body = build_deepseek_body(
        {
            "method": "native-full",
            "knowledge_allowed": True,
            "category": "Network degradation",
            "category_config": {"top_motifs": [{"motif": "action_or_target=delay"}]},
            "sock_shop_profile": {"services": ["front-end", "catalogue"]},
            "seen_hypotheses": [],
        },
        model="deepseek-chat",
    )
    system = body["messages"][0]["content"]
    assert "hypothesis must be a JSON object" in system
    assert "target_service" in system
    assert "front-end" in body["messages"][1]["content"]


def test_deepseek_body_exposes_uncovered_required_motifs():
    body = build_deepseek_body(
        {
            "method": "chaosatlas-ablation",
            "knowledge_allowed": False,
            "category": "Network degradation",
            "category_config": {
                "top_motifs": [
                    {"motif": "action_or_target=delay"},
                    {"motif": "action_or_target=loss"},
                ]
            },
            "sock_shop_profile": {"services": ["front-end"]},
            "seen_hypotheses": [{"motifs": ["action_or_target=delay"]}],
        },
        model="deepseek-chat",
    )
    content = body["messages"][1]["content"]
    assert "uncovered_required_motifs" in content
    assert "action_or_target=loss" in content


def test_deepseek_model_call_uses_direct_bounded_opener(monkeypatch):
    calls = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": '{"hypothesis": {}}'}}]}).encode()

    class Opener:
        def open(self, request, timeout):
            calls["url"] = request.full_url
            calls["timeout"] = timeout
            return Response()

    def build_opener(*handlers):
        calls["handlers"] = handlers
        return Opener()

    monkeypatch.setattr(discovery.urllib.request, "build_opener", build_opener)
    call = discovery._deepseek_model_call("test-key")
    call({"method": "native-full", "knowledge_allowed": True, "category": "Pod disruption", "category_config": {}, "seen_hypotheses": []})

    assert any(isinstance(handler, discovery.urllib.request.ProxyHandler) for handler in calls["handlers"])
    assert calls["timeout"] == 120
    assert calls["url"].endswith("/v1/chat/completions")


def test_deepseek_model_call_retries_transient_network_errors(monkeypatch):
    attempts = {"count": 0}
    sleeps = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": '{"hypothesis": {}}'}}]}).encode()

    class Opener:
        def open(self, _request, timeout):
            assert timeout == 120
            attempts["count"] += 1
            if attempts["count"] < 5:
                if attempts["count"] == 1:
                    raise TimeoutError("read timeout")
                raise urllib.error.URLError("transient")
            return Response()

    monkeypatch.setattr(discovery.urllib.request, "build_opener", lambda *_handlers: Opener())
    monkeypatch.setattr(discovery.time, "sleep", lambda value: sleeps.append(value))

    result = discovery._deepseek_model_call("test-key")(
        {"method": "native-full", "knowledge_allowed": True, "category": "Pod disruption", "category_config": {}, "seen_hypotheses": []}
    )

    assert result == {"hypothesis": {}}
    assert attempts["count"] == 5
    assert sleeps == [1, 2, 4, 8]


def test_discovery_writes_checkpoint_after_completion(tmp_path):
    checkpoint = tmp_path / "discovery.checkpoint.json"

    result = run_confidence_discovery(
        _method_input("native-full", True),
        lambda _payload: {
            "hypothesis": {
                "target_service": "catalogue",
                "action_or_target": "delay",
                "call_chain_position": "business-service",
                "motifs": ["action_or_target=delay"],
            }
        },
        checkpoint_path=checkpoint,
    )

    saved = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert result["status"] == "confidence_incomplete"
    assert saved["status"] == "completed"
    assert len(saved["hypotheses"]) == 2
    assert saved["category_states"]["Network degradation"]["duplicate_count"] == 1
