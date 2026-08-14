from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.run_online_boutique_two_arm_discovery import (
    build_messages,
    parse_model_output,
    prepare_output_dir,
)


def bundle(method: str = "ChaosAtlas-full") -> dict:
    return {
        "project_id": "online-boutique",
        "seed": 1001,
        "method_id": method,
        "common_input": {
            "project_id": "online-boutique",
            "project_commit": "a" * 40,
            "namespace": "chaosatlas-online-boutique",
            "topology": {"nodes": [], "edges": []},
            "business_oracle": {"workflow": "PlaceOrder"},
        },
        "knowledge_view": None if method.endswith("ablation") else {"facts": []},
    }


def test_messages_include_schema_and_method_view_without_cross_arm_output() -> None:
    system, user = build_messages(bundle())
    assert "Return only JSON" in system
    assert '"hypotheses"' in user
    assert "ChaosAtlas-full" in user
    assert "other_method_output" not in user


def test_messages_state_exact_runtime_parameter_contract() -> None:
    _, user = build_messages(bundle())
    value = json.loads(user)
    assert value["parameter_contract"]["network_delay"]["latency_ms"]
    assert value["parameter_contract"]["network_delay"]["duration_s"]
    assert value["parameter_contract"]["pod_kill"]["mode"] == "one"
    assert value["target_rule"].startswith("Use exact IDs from common_input.topology")


def test_parse_model_output_accepts_fenced_json() -> None:
    value = parse_model_output(
        "```json\n"
        + json.dumps(
            {
                "method_id": "ChaosAtlas-full",
                "project_id": "online-boutique",
                "project_commit": "a" * 40,
                "hypotheses": [],
                "no_safe_hypothesis_reason": "none",
            }
        )
        + "\n```"
    )
    assert value["project_id"] == "online-boutique"


def test_parse_model_output_rejects_executable_fields() -> None:
    with pytest.raises(ValueError, match="forbidden"):
        parse_model_output(json.dumps({"hypotheses": [], "kubectl_command": "apply"}))


def test_prepare_output_dir_refuses_nonempty_directory(tmp_path: Path) -> None:
    target = tmp_path / "formal"
    target.mkdir()
    (target / "old.json").write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError):
        prepare_output_dir(target)
