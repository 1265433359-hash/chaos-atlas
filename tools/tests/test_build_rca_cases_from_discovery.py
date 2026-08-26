from __future__ import annotations

import json

import pytest

from tools.build_rca_cases_from_discovery import build_rca_cases
from tools.validate_rca_loop import validate_case, validate_hypothesis
from tools.rca_runtime_loop import advance_rca_loop
from tools.sock_shop_rca import actions_for_case


def _profile() -> dict:
    return {
        "schema_version": "chaosatlas-project-profile-v1",
        "project_id": "demo",
        "project_commit": "fixture-commit",
        "revision_kind": "fixture",
        "namespace_policy": {"allowed_namespaces": ["demo-lab"], "isolation_required": True},
        "source": {"manifest_roots": ["manifests"], "source_roots": ["src"]},
        "business_oracles": [{
            "id": "homepage",
            "kind": "http",
            "entrypoint": "GET /",
            "success_contract": "HTTP 200",
        }],
        "observability": {"logs": {}, "events": {}},
        "recovery": {"deadline_s": 60, "require_business_probe": True, "require_cleanup": True},
        "cleanup": {"owner": "chaosatlas", "must_be_empty": True},
        "sensitive_data_policy": {"redact_fields": []},
    }


def _hypothesis(hid: str = "h-api") -> dict:
    return {
        "hypothesis_id": hid,
        "canonical_signature": "a" * 64,
        "project_id": "demo",
        "target": "deployment:api",
        "target_kind": "deployment",
        "fault_family": "pod_kill",
        "parameters": {"mode": "one"},
        "hypothesis": "losing the API pod may violate availability",
        "expected_invariant": "availableReplicas >= 1",
        "expected_steady_state": "availableReplicas >= 1",
        "validation_plan": "baseline, inject, observe, recover, cleanup",
        "recovery_expectation": "replacement pod becomes Ready",
        "weakness_surface": "API availability",
    }


def test_build_rca_cases_writes_only_accepted_hypotheses(tmp_path):
    handoff = {
        "status": "handoff_ready",
        "selected_hypotheses": [_hypothesis()],
        "rejected_hypotheses": [{"hypothesis_id": "rejected"}],
    }
    result = build_rca_cases(
        handoff,
        profile=_profile(),
        round_id="discovery-r1",
        output_root=tmp_path / "rca",
    )
    assert result["status"] == "completed"
    assert result["case_count"] == 1
    # Discover the stable filename without coupling the test to hash formatting.
    case_paths = list((tmp_path / "rca" / "cases").glob("*.json"))
    assert len(case_paths) == 1
    case = json.loads(case_paths[0].read_text(encoding="utf-8"))
    assert validate_case(case, tmp_path / "rca") == []
    assert validate_hypothesis(case["hypotheses"][0], case) == []
    assert case["rca_status"] == "pending"
    assert case["weakness_status"] == "candidate"
    assert case["knowledge_status"] == "none"
    assert case["test_node"]["source_ref"] == "discovery/handoff.json"
    assert (tmp_path / "rca" / "discovery" / "handoff.json").is_file()
    assert json.loads((tmp_path / "rca" / "manifest.json").read_text(encoding="utf-8"))["knowledge_base_updated"] is False


def test_build_rca_cases_rejects_identity_and_empty_inputs(tmp_path):
    with pytest.raises(ValueError, match="accepted"):
        build_rca_cases({"status": "handoff_ready", "selected_hypotheses": []}, profile=_profile(), round_id="r1", output_root=tmp_path / "empty")

    bad = _hypothesis()
    bad["project_id"] = "other"
    with pytest.raises(ValueError, match="project_id"):
        build_rca_cases({"status": "handoff_ready", "selected_hypotheses": [bad]}, profile=_profile(), round_id="r1", output_root=tmp_path / "bad")


def test_build_rca_cases_rejects_duplicate_ids_and_nonempty_output(tmp_path):
    with pytest.raises(ValueError, match="duplicate"):
        build_rca_cases({"status": "handoff_ready", "selected_hypotheses": [_hypothesis(), _hypothesis()]}, profile=_profile(), round_id="r1", output_root=tmp_path / "dupe")

    output = tmp_path / "existing"
    output.mkdir()
    (output / "keep.txt").write_text("user artifact", encoding="utf-8")
    with pytest.raises(FileExistsError):
        build_rca_cases({"status": "handoff_ready", "selected_hypotheses": [_hypothesis()]}, profile=_profile(), round_id="r1", output_root=output)


def test_native_case_can_enter_dry_run_rca_runtime(tmp_path):
    source = tmp_path / "rca"
    build_rca_cases(
        {"status": "handoff_ready", "selected_hypotheses": [_hypothesis()]},
        profile=_profile(),
        round_id="r1",
        output_root=source,
    )
    result = advance_rca_loop(
        rca_root=source,
        output_root=tmp_path / "r2",
        available_preconditions={"frozen_manifest"},
        dry_run=True,
    )
    assert result["status"] == "completed"


def test_native_case_exposes_gated_fault_injection_action():
    case = build_case_from_hypothesis_for_test()
    actions = actions_for_case(case, case["hypotheses"])
    injection = next(item for item in actions if item["kind"] == "native_fault_injection")
    assert "native_executor_ready" in injection["preconditions"]
    assert "business_oracle_available" in injection["preconditions"]
    assert injection["cleanup"]


def test_discovery_adapter_can_attach_frozen_pilot_contract(tmp_path):
    profile = _profile()
    profile["project_id"] = "demo"
    profile["project_commit"] = "fixture-commit"
    pilot = {
        "schema_version": "pilot-v1",
        "project_id": "demo",
        "project_commit": "fixture-commit",
        "namespace": "demo-lab",
        "target": "deployment:api",
        "oracle": {"entrypoint": "GET /", "success_contract": "HTTP 200"},
        "cleanup": {"must_be_absent": True},
        "mutation_manifest": {"kind": "PodChaos", "metadata": {"namespace": "demo-lab", "name": "demo-podkill"}},
    }
    source = tmp_path / "rca"
    build_rca_cases(
        {"status": "handoff_ready", "selected_hypotheses": [_hypothesis()]},
        profile=profile,
        round_id="r1",
        output_root=source,
        pilot_contract=pilot,
    )
    case = json.loads(next((source / "cases").glob("*.json")).read_text(encoding="utf-8"))
    assert case["test_node"]["mutation_manifest"]["metadata"]["name"] == "demo-podkill"
    assert case["cleanup_contract"]["must_be_absent"] is True


def build_case_from_hypothesis_for_test() -> dict:
    return {
        "case_family": "native_deployment_pod_kill",
        "project_id": "demo",
        "project_commit": "fixture-commit",
        "weakness_id": "WS-demo-api-pod-kill",
        "namespace": "demo-lab",
        "test_node": {"target": "deployment:api", "target_role": "deployment:api"},
        "symptom": {"baseline_contract": "HTTP 200"},
        "hypotheses": [{"hypothesis_id": "h-api", "weakness_id": "WS-demo-api-pod-kill"}],
    }
