import json
import urllib.request

import pytest

from tools.run_sock_shop_ablation_discovery import (
    _deepseek_model_call,
    build_ablation_payload,
    load_yaml15_bundle,
    run_ablation_discovery,
)


def _method_input():
    return {
        "method": "chaosatlas-ablation",
        "knowledge_allowed": False,
        "yaml_category_summary": {"secret": "must-not-leak"},
        "sock_shop_profile": {
            "namespace": "chaosatlas-sock-shop",
            "services": ["front-end", "catalogue", "orders"],
            "business_oracle": {"name": "golden-journey"},
        },
        "knowledge_base_view": {"must_not": "appear"},
        "call_chain_projection": {"must_not": "appear"},
    }


def _write_yaml15_bundle(tmp_path):
    examples = []
    categories = {}
    category_names = [
        "Pod disruption",
        "Network degradation",
        "Resource pressure",
        "Protocol/HTTP fault",
        "Composite/scheduled fault",
    ]
    for category in category_names:
        categories[category] = []
        for index in range(3):
            examples.append({"category": category, "yaml": f"kind: Example\nspec:\n  index: {index}\n"})
            categories[category].append({"order": len(examples), "category": category})
    prompt = {
        "schema_version": "sock-shop-ablation-yaml15-prompt-v1",
        "labeled_yaml_examples": examples,
    }
    prompt_path = tmp_path / "yaml15-prompt.json"
    prompt_path.write_text(json.dumps(prompt), encoding="utf-8")
    import hashlib

    manifest = {
        "schema_version": "sock-shop-ablation-yaml15-manifest-v1",
        "total_examples": 15,
        "category_order": category_names,
        "selection_fingerprint_sha256": "a" * 64,
        "prompt_path": prompt_path.name,
        "prompt_sha256": hashlib.sha256(prompt_path.read_bytes()).hexdigest(),
        "categories": categories,
    }
    manifest_path = tmp_path / "yaml15-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def _all_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _all_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _all_keys(child)


def test_ablation_payload_has_no_classification_confidence_or_full_trace():
    payload = build_ablation_payload(_method_input(), [], seed=123)

    assert payload["method"] == "chaosatlas-ablation"
    assert payload["seed"] == 123
    assert "category" not in payload
    assert "yaml_category_summary" not in payload
    assert all("confidence" not in item for item in payload["seen_hypotheses"])
    assert "call_chain_projection" not in payload
    assert "knowledge_base_view" not in payload
    assert payload["sock_shop_profile"]["business_oracle"]


def test_yaml15_payload_contains_only_frozen_labeled_examples_and_public_profile(tmp_path):
    bundle = load_yaml15_bundle(_write_yaml15_bundle(tmp_path))

    payload = build_ablation_payload(_method_input(), [], seed=123, yaml15_bundle=bundle)

    assert payload["method"] == "chaosatlas-ablation-yaml15"
    assert len(payload["yaml15_primer"]["labeled_yaml_examples"]) == 15
    assert set(item["category"] for item in payload["yaml15_primer"]["labeled_yaml_examples"]) == {
        "Pod disruption",
        "Network degradation",
        "Resource pressure",
        "Protocol/HTTP fault",
        "Composite/scheduled fault",
    }
    serialized = json.dumps(payload)
    assert "yaml_category_summary" not in serialized
    assert "knowledge_base_view" not in serialized
    assert "call_chain_projection" not in serialized
    assert all("confidence" not in key.lower() for key in _all_keys(payload))


def test_yaml15_bundle_rejects_prompt_hash_mismatch(tmp_path):
    manifest_path = _write_yaml15_bundle(tmp_path)
    (tmp_path / "yaml15-prompt.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="prompt SHA-256 mismatch"):
        load_yaml15_bundle(manifest_path)


def test_yaml15_discovery_records_primer_provenance_and_marks_chain_as_inference(tmp_path):
    bundle = load_yaml15_bundle(_write_yaml15_bundle(tmp_path))

    def model_call(_payload):
        return {
            "stop": True,
            "stop_reason": "self_stop",
            "hypothesis": {
                "id": "yaml15-h-1",
                "target_service": "catalogue",
                "action_or_target": "delay",
                "call_chain_position": "after front-end",
            },
            "_usage": {"total_tokens": 7},
        }

    result = run_ablation_discovery(
        _method_input(),
        model_call,
        time_cap_seconds=30,
        seed=123,
        yaml15_bundle=bundle,
    )

    assert result["method"] == "chaosatlas-ablation-yaml15"
    assert result["schema_version"] == "sock-shop-ablation-yaml15-discovery-v1"
    assert result["yaml15_provenance"]["prompt_sha256"] == bundle["prompt_sha256"]
    assert result["prompt_protocol"]["classification_examples_allowed"] is True
    assert result["prompt_protocol"]["confidence_allowed"] is False
    assert result["hypotheses"][0]["call_chain_position_source"] == "model_inference"


def test_yaml15_discovery_rejects_claimed_verified_call_chain(tmp_path):
    bundle = load_yaml15_bundle(_write_yaml15_bundle(tmp_path))

    def model_call(_payload):
        return {
            "stop": True,
            "hypothesis": {
                "id": "yaml15-h-1",
                "target_service": "catalogue",
                "action_or_target": "delay",
                "call_chain_position": "after front-end",
                "call_chain_position_source": "verified_project_topology",
            },
        }

    with pytest.raises(ValueError, match="call_chain_position_source"):
        run_ablation_discovery(
            _method_input(),
            model_call,
            time_cap_seconds=30,
            seed=123,
            yaml15_bundle=bundle,
        )


def test_deepseek_call_audit_records_request_and_response_without_api_key(tmp_path, monkeypatch):
    response_payload = {
        "choices": [{"message": {"content": json.dumps({"stop": True, "stop_reason": "self_stop"})}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
        "model": "deepseek-chat",
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(response_payload).encode("utf-8")

    class FakeOpener:
        def open(self, _request, timeout):
            assert timeout > 0
            return FakeResponse()

    monkeypatch.setattr(urllib.request, "build_opener", lambda *_args: FakeOpener())
    audit_dir = tmp_path / "model-audit"
    model_call = _deepseek_model_call("do-not-write-this-api-key", audit_dir=audit_dir)

    result = model_call({"method": "chaosatlas-ablation-yaml15", "seed": 0})

    assert result["stop"] is True
    request_audit = json.loads((audit_dir / "call-001.request.json").read_text(encoding="utf-8"))
    response_audit = json.loads((audit_dir / "call-001.response.json").read_text(encoding="utf-8"))
    assert request_audit["body"]["model"] == "deepseek-chat"
    assert response_audit["usage"]["total_tokens"] == 12
    serialized = "".join(path.read_text(encoding="utf-8") for path in audit_dir.iterdir())
    assert "do-not-write-this-api-key" not in serialized
    assert "Authorization" not in serialized


def test_ablation_stops_when_model_explicitly_self_stops():
    calls = []

    def model_call(payload):
        calls.append(payload)
        if len(calls) == 2:
            return {"stop": True, "stop_reason": "self_stop", "_usage": {"total_tokens": 7}}
        return {
            "hypothesis": {
                "id": f"h-{len(calls)}",
                "target_service": "catalogue",
                "action_or_target": "delay",
                "call_chain_position": "business-service",
            },
            "continue_generation": True,
            "_usage": {"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16},
        }

    result = run_ablation_discovery(_method_input(), model_call, time_cap_seconds=30, seed=123)

    assert result["status"] == "completed"
    assert result["self_stop"] is True
    assert result["time_cap_hit"] is False
    assert result["stop_reason"] == "self_stop"
    assert len(result["hypotheses"]) == 1
    assert result["timing"]["model_calls"] == 2
    assert result["timing"]["total_tokens"] == 23
    assert all("stop_snapshot" not in item for item in result["hypotheses"])


def test_ablation_time_cap_prevents_any_request():
    calls = []

    def model_call(_payload):
        calls.append(True)
        raise AssertionError("model must not be called after a zero time cap")

    result = run_ablation_discovery(_method_input(), model_call, time_cap_seconds=0, seed=123)

    assert result["status"] == "time_cap_hit"
    assert result["self_stop"] is False
    assert result["time_cap_hit"] is True
    assert result["timing"]["model_calls"] == 0
    assert not calls


def test_payload_preserves_submillisecond_deadline():
    payload = build_ablation_payload(
        _method_input(),
        [],
        seed=123,
        deadline_remaining_seconds=0.0004,
    )

    assert payload["deadline_remaining_seconds"] == 0.0004


def test_ablation_response_after_deadline_is_time_cap_not_self_stop(monkeypatch):
    clock = {"now": 0.0}
    monkeypatch.setattr("tools.run_sock_shop_ablation_discovery.time.monotonic", lambda: clock["now"])

    def model_call(_payload):
        clock["now"] = 2.0
        return {"stop": True, "stop_reason": "self_stop", "_usage": {"total_tokens": 1}}

    result = run_ablation_discovery(_method_input(), model_call, time_cap_seconds=1, seed=123)

    assert result["status"] == "time_cap_hit"
    assert result["self_stop"] is False
    assert result["time_cap_hit"] is True
    assert result["stop_reason"] == "time_cap_hit"


def test_deepseek_retries_do_not_run_past_request_deadline(monkeypatch):
    clock = {"now": 0.0}
    attempts = []

    class FakeOpener:
        def open(self, _request, timeout):
            attempts.append(timeout)
            clock["now"] = 2.0
            raise urllib.error.URLError("temporary")

    monkeypatch.setattr(urllib.request, "build_opener", lambda *_args: FakeOpener())
    monkeypatch.setattr("tools.run_sock_shop_ablation_discovery.time.monotonic", lambda: clock["now"])
    monkeypatch.setattr("tools.run_sock_shop_ablation_discovery.time.sleep", lambda _seconds: None)
    model_call = _deepseek_model_call("do-not-write-this-api-key")

    with pytest.raises(TimeoutError, match="deadline"):
        model_call({"method": "chaosatlas-ablation-yaml15", "seed": 0, "deadline_remaining_seconds": 1})

    assert len(attempts) == 1


def test_deepseek_zero_deadline_never_opens_request(monkeypatch):
    attempts = []

    class FakeOpener:
        def open(self, _request, timeout):
            attempts.append(timeout)
            raise AssertionError("expired request must not be opened")

    monkeypatch.setattr(urllib.request, "build_opener", lambda *_args: FakeOpener())
    model_call = _deepseek_model_call("do-not-write-this-api-key")

    with pytest.raises(TimeoutError, match="deadline"):
        model_call({"method": "chaosatlas-ablation-yaml15", "seed": 0, "deadline_remaining_seconds": 0})

    assert not attempts


def test_ablation_checkpoint_resumes_without_repeating_completed_calls(tmp_path):
    checkpoint = tmp_path / "ablation.checkpoint.json"
    calls = []

    def interrupted(payload):
        calls.append(payload)
        if len(calls) == 2:
            raise RuntimeError("network interruption")
        return {
            "hypothesis": {
                "id": "h-1",
                "target_service": "catalogue",
                "action_or_target": "delay",
                "call_chain_position": "business-service",
            },
            "continue_generation": True,
            "_usage": {"total_tokens": 9},
        }

    with pytest.raises(RuntimeError, match="network interruption"):
        run_ablation_discovery(
            _method_input(),
            interrupted,
            time_cap_seconds=30,
            seed=123,
            checkpoint_path=checkpoint,
        )

    saved = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert len(saved["hypotheses"]) == 1
    assert saved["timing"]["model_calls"] == 1
    assert saved["timing"]["total_tokens"] == 9

    def finish(payload):
        assert len(payload["seen_hypotheses"]) == 1
        return {"stop": True, "stop_reason": "self_stop", "_usage": {"total_tokens": 3}}

    resumed = run_ablation_discovery(
        _method_input(),
        finish,
        time_cap_seconds=30,
        seed=123,
        checkpoint_path=checkpoint,
        resume=True,
    )

    assert len(resumed["hypotheses"]) == 1
    assert resumed["timing"]["model_calls"] == 2
    assert resumed["timing"]["total_tokens"] == 12


def test_ablation_completed_checkpoint_resume_does_not_call_model(tmp_path):
    checkpoint = tmp_path / "completed.checkpoint.json"

    def stop(_payload):
        return {"stop": True, "stop_reason": "self_stop", "_usage": {"total_tokens": 7}}

    completed = run_ablation_discovery(
        _method_input(),
        stop,
        time_cap_seconds=30,
        seed=123,
        checkpoint_path=checkpoint,
    )

    def must_not_run(_payload):
        raise AssertionError("completed checkpoint must not issue another model request")

    resumed = run_ablation_discovery(
        _method_input(),
        must_not_run,
        time_cap_seconds=30,
        seed=123,
        checkpoint_path=checkpoint,
        resume=True,
    )

    assert resumed == completed
