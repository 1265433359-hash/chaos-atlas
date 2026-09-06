import json

from scripts.run_kubernetes_api_disposable_canary import _runtime_profile, _summarize_run


def test_runtime_profile_binds_one_owned_disposable_namespace_and_fault():
    profile = _runtime_profile(
        namespace="ca-l2-medusa-abc123",
        context="ca-l3-parent-abc123",
        family="image_pull_failure",
        project_revision="a" * 64,
    )

    assert profile["project_id"] == "medusa"
    assert profile["namespace_policy"]["allowed_namespaces"] == ["ca-l2-medusa-abc123"]
    assert profile["namespace_policy"]["disposable"] is True
    assert profile["runtime_contract"]["supported_fault_families"] == ["image_pull_failure"]
    assert set(profile["fault_support"]) == {"image_pull_failure"}
    assert "value" not in json.dumps(profile["fault_defaults"])


def test_run_summary_requires_live_status_and_valid_mechanism_evidence(tmp_path):
    run_root = tmp_path / "run"
    item_root = tmp_path / "item"
    evidence_root = item_root / "runtime" / "business"
    evidence_root.mkdir(parents=True)
    run_root.mkdir()
    (run_root / "batch_summary.json").write_text(json.dumps({"results": [{"output": str(item_root)}]}), encoding="utf-8")
    (item_root / "summary.json").write_text(json.dumps({"status": "live_completed"}), encoding="utf-8")
    (evidence_root / "live.json").write_text(json.dumps({
        "attestation": {"valid": True},
        "injection": {"confirmation": {"confirmed": True, "mechanism": "pod_image_pull_waiting"}},
        "recovery": {"confirmed": True},
        "cleanup": {"confirmed": True},
    }), encoding="utf-8")

    result = _summarize_run(run_root)

    assert result["verified"] is True
    assert result["mechanism"] == "pod_image_pull_waiting"
