from __future__ import annotations

import json
from pathlib import Path

import pytest

from chaosatlas.oracles import DEFAULT_ORACLE_REGISTRY
from chaosatlas.isolation.blueprint import compile_blueprint
from chaosatlas.orchestration.engine import RunEngine, RunRequest
from chaosatlas.orchestration.isolated_run import resolve_isolation_profile
from tools.chaosatlas_adapters import OfflineProjectAdapter
from tools.project_onboarding import validate_project_profile


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "projects" / "chaosatlas-apps"
FACT_ROOT = ROOT / "tests" / "fixtures" / "chaosatlas_offline"
APPS = ("immich", "medusa", "rocketchat", "erpnext")
EXPECTED_TARGET_COUNTS = {
    "immich": 2,
    "medusa": 3,
    "rocketchat": 2,
    "erpnext": 9,
}
EXPECTED_ORACLE_TARGETS = {
    "immich": "immich-server",
    "medusa": "medusa-backend",
    "rocketchat": "rocketchat-rocketchat",
    "erpnext": "erpnext-nginx",
}


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


@pytest.mark.parametrize("app", APPS)
def test_four_app_profile_and_frozen_facts_share_one_contract(app: str) -> None:
    profile_path = APP_ROOT / app / "profile.json"
    facts_path = FACT_ROOT / app / "project_facts.json"
    profile = _load(profile_path)
    facts = _load(facts_path)

    validation = validate_project_profile(profile)
    assert validation["valid"], validation["errors"]
    assert profile["project_id"] == facts["project_id"] == app
    assert profile["project_commit"] == facts["project_commit"]
    assert profile["namespace_policy"]["allowed_namespaces"] == [facts["namespace"]]
    assert profile["runtime_contract"]["kube_context"] == "chaosatlas-apps"
    assert profile["fault_support"]["pod_kill"]["status"] == "supported"

    oracle = profile["business_oracles"][0]
    assert DEFAULT_ORACLE_REGISTRY.supports(oracle["kind"])
    assert oracle["service"] in facts["services"]
    assert oracle["expected_status"] == 200
    assert oracle["expected_body"]

    adapter = OfflineProjectAdapter(facts_path, workspace_root=ROOT)
    assert adapter.onboard(profile_path)["status"] == "ready_for_static_analysis"
    inventory = adapter.inventory(profile)
    detection = adapter.detect_server_deployment(inventory)
    candidates = adapter.map_test_nodes(detection)

    assert inventory["claim_scope"] == "static"
    assert detection["status"] == "verified"
    assert len(detection["candidates"]) == EXPECTED_TARGET_COUNTS[app]
    assert candidates["candidate_count"] == EXPECTED_TARGET_COUNTS[app]
    assert {item["fault_family"] for item in candidates["candidates"]} == {"pod_kill"}


@pytest.mark.parametrize("app", APPS)
def test_four_app_dry_run_selects_the_business_oracle_owner(app: str, tmp_path: Path) -> None:
    result = RunEngine().run(
        RunRequest(
            profile_path=APP_ROOT / app / "profile.json",
            output_root=tmp_path / app,
            mode="dry-run",
        )
    )

    assert result["status"] == "dry_run_ready"
    assert result["claim_scope"] == "planned"
    assert result["runtime_claims"] == []
    assert result["selected_candidate_ids"] == [
        f"server:deployment:{app}:{EXPECTED_ORACLE_TARGETS[app]}:pod_kill"
    ]


@pytest.mark.parametrize("app", ["medusa", "rocketchat"])
def test_disposable_l2_profiles_compile_and_route_kubernetes_api_faults(app: str) -> None:
    profile_path = APP_ROOT / app / "profile.json"
    expected_faults = {"secret_rotation", "image_pull_failure", "pod_unschedulable"}

    for fault_id in expected_faults:
        profile, route = resolve_isolation_profile(profile_path, fault_id)
        assert route["level"] == "L2"
        assert route["backend"] == "kubernetes_api"
        compiled = compile_blueprint(
            profile["isolation"]["l2"]["blueprint"],
            namespace=f"ca-l2-{app}-fixture",
            owner_labels={"chaosatlas.dev/managed": "true"},
        )
        assert compiled
        assert all(item["metadata"]["namespace"] == f"ca-l2-{app}-fixture" for item in compiled)
