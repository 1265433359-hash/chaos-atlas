from __future__ import annotations

import json
import shutil
from pathlib import Path

from tools.run_native_full_discovery import ROOT, build_messages, parse_model_output, run_matrix


def test_native_discovery_messages_include_native_method_and_knowledge_view() -> None:
    bundle = {
        "project_id": "demo",
        "seed": 1001,
        "method_id": "ChaosAtlas-native-full",
        "common_input": {
            "topology": {"nodes": [{"id": "workload/api", "role": "workload"}], "edges": []}
        },
        "knowledge_view": {"cards": [{"id": "KB-1"}], "projection_used": False},
    }

    system, user = build_messages(bundle)

    assert "native project knowledge" in system
    assert "at most 500" in system
    payload = json.loads(user)
    assert payload["method_id"] == "ChaosAtlas-native-full"
    assert payload["knowledge_view"]["projection_used"] is False
    assert payload["parameter_contract"]["network_delay"] == {
        "latency_ms": "integer 1..500",
        "duration_s": "integer 1..60",
    }
    assert payload["parameter_contract"]["pod_kill"] == {"mode": "one"}


def test_parse_model_output_rejects_runtime_feedback_fields() -> None:
    try:
        parse_model_output(json.dumps({"hypotheses": [], "runtime_observation": "bad"}))
    except ValueError as exc:
        assert "forbidden" in str(exc)
    else:
        raise AssertionError("runtime feedback must be rejected")


def test_native_discovery_preflight_accepts_relative_input_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(ROOT)
    input_root = Path(".pytest-tmp-native-discovery-relative")
    if input_root.exists():
        shutil.rmtree(input_root)
    bundle_dir = input_root / "input_bundles" / "demo" / "seed-1001"
    bundle_dir.mkdir(parents=True)
    bundle = {
        "project_id": "demo",
        "seed": 1001,
        "method_id": "ChaosAtlas-native-full",
        "common_input": {"topology": {"nodes": [], "edges": []}},
        "knowledge_view": {"projection_used": False},
        "projection_used": False,
        "pollution_intentionally_not_excluded": True,
    }
    (bundle_dir / "chaosatlas-native-full.json").write_text(json.dumps(bundle), encoding="utf-8")
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"runtime_ready": True}), encoding="utf-8")
    try:
        result = run_matrix(
            input_root=input_root,
            profile_path=profile,
            output=tmp_path / "discovery",
            key_path=tmp_path / "unused-key",
            project_id="demo",
            seeds=(1001,),
            execute=False,
        )
        assert result["status"] == "preflight_passed"
    finally:
        shutil.rmtree(input_root)
