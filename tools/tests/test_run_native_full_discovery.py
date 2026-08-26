from __future__ import annotations

import json
import shutil
from pathlib import Path

from tools.run_native_full_discovery import ROOT, build_messages, parse_model_output, run_matrix
from tools.run_native_full_discovery import build_policy_decision


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
        "common_input": {"topology": {"nodes": [], "edges": []}, "business_oracle": {"workflow": "GET /", "success": "HTTP 200"}},
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


def test_native_discovery_rejects_runtime_feedback_in_static_bundle(tmp_path: Path):
    input_root = tmp_path / "input"
    bundle_dir = input_root / "input_bundles" / "demo" / "seed-1001"
    bundle_dir.mkdir(parents=True)
    bundle = {
        "project_id": "demo",
        "seed": 1001,
        "method_id": "ChaosAtlas-native-full",
        "common_input": {"topology": {"nodes": [], "edges": []}, "runtime_observation": {"availableReplicas": 0}},
        "knowledge_view": {"projection_used": False},
        "projection_used": False,
        "pollution_intentionally_not_excluded": True,
    }
    (bundle_dir / "chaosatlas-native-full.json").write_text(json.dumps(bundle), encoding="utf-8")
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"runtime_ready": True}), encoding="utf-8")
    try:
        run_matrix(input_root=input_root, profile_path=profile, output=tmp_path / "discovery", key_path=tmp_path / "unused-key", project_id="demo", seeds=(1001,), execute=False)
    except ValueError as exc:
        assert "runtime" in str(exc)
    else:
        raise AssertionError("runtime feedback must be rejected from native static input")


def test_native_discovery_can_inject_one_static_deployment_pool_for_all_seeds(tmp_path: Path):
    input_root = tmp_path / "input"
    bundle_dir = input_root / "input_bundles" / "demo" / "seed-1001"
    bundle_dir.mkdir(parents=True)
    bundle = {
        "project_id": "demo", "seed": 1001, "method_id": "ChaosAtlas-native-full",
        "common_input": {"topology": {"nodes": [], "edges": []}, "business_oracle": {"workflow": "GET /", "success": "HTTP 200"}},
        "knowledge_view": {"projection_used": False}, "projection_used": False,
        "pollution_intentionally_not_excluded": True,
    }
    (bundle_dir / "chaosatlas-native-full.json").write_text(json.dumps(bundle), encoding="utf-8")
    pool = {
        "project_id": "demo", "project_commit": "a" * 40, "namespace": "chaosatlas-demo", "status": "verified",
        "deployment_nodes": [{"node_id": "deployment:api", "deployment": {"selector": {"matchLabels": {"app": "api"}}, "desired_replicas": 1}, "availability_profile": {"manifest_facts_status": "verified", "recovery_contract": {"ready_required": True}}}],
        "candidates": [{"target": "deployment:api", "target_kind": "deployment", "compile_eligible": True, "fault_families": ["pod_kill"]}],
    }
    pool_path = tmp_path / "pool.json"
    pool_path.write_text(json.dumps(pool), encoding="utf-8")
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"runtime_ready": True}), encoding="utf-8")
    result = run_matrix(input_root=input_root, profile_path=profile, output=tmp_path / "discovery", key_path=tmp_path / "unused-key", project_id="demo", seeds=(1001,), execute=False, deployment_pool_path=pool_path)
    assert result["status"] == "preflight_passed"
    preflight = json.loads((tmp_path / "discovery" / "preflight.json").read_text(encoding="utf-8"))
    assert preflight["records"][0]["eligible_count"] == 2


def test_policy_decision_has_auditable_schema_and_selected_ids():
    state = {
        "schema_version": "chaosatlas-experiment-policy-state-v1",
        "policy_version": "ig-stop-v1",
        "project_id": "demo",
        "project_commit": "a" * 40,
        "seed": 1001,
        "input_sha256": "b" * 64,
    }
    selection = {
        "policy_mode": "shadow",
        "policy_selected_hypothesis_ids": ["h-1"],
        "policy_selected_candidate_ids": ["candidate-a"],
        "stop_reason": None,
        "scores": [{"candidate_id": "candidate-a", "value_per_cost": 2.0}],
    }
    result = build_policy_decision(state, selection, legacy_hypothesis_ids=["h-1", "h-2"])
    assert result["schema_version"] == "chaosatlas-experiment-policy-decision-v1"
    assert result["input_sha256"] == "b" * 64
    assert result["legacy_hypothesis_ids"] == ["h-1", "h-2"]
    assert result["policy_selected_hypothesis_ids"] == ["h-1"]
