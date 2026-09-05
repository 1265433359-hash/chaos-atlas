from datetime import datetime, timedelta, timezone

import pytest

from chaosatlas.isolation.contracts import transition_lease, validate_lease, validate_plan, with_hash
from chaosatlas.isolation.lease_store import LeaseStore
from chaosatlas.isolation.planner import IsolationPlanner
from chaosatlas.capabilities.core_assessment import isolation_for_core_fault
from chaosatlas.capabilities.extension_assessment import isolation_for_extension
from tools.extension_fault_catalog import extension_catalog
from tools.fault_catalog import fault_catalog


def _profile(level="l1", config=None):
    return {
        "project_id": "fixture",
        "project_commit": "revision",
        "namespace_policy": {"allowed_namespaces": ["fixture-lab"]},
        "runtime_contract": {"kube_context": "test"},
        "isolation": {level: config or {"mode": "adopted-test-replica", "dedicated_test_replica": True}, "synthetic_data_only": True},
    }


def _capability(level="L1", fault="pod_kill", status="canary_required"):
    return {"fault_id": fault, "target_id": "node:web", "required_isolation": level, "capability_status": status}


def test_planner_never_lowers_isolation_and_forces_control_plane_to_l3():
    planner = IsolationPlanner()
    plan = planner.plan(profile=_profile("l3", {"mode": "ephemeral-cluster"}), capability=_capability("L3", "api_server_delay"), proposed_isolation="L1")
    assert plan["effective_isolation"] == "L3"
    assert plan["provider"] == "minikube-l3"
    assert plan["status"] == "ready"
    assert validate_plan(plan) == []


def test_planner_blocks_missing_l2_target_facts_and_inapplicable_capability():
    plan = IsolationPlanner().plan(profile=_profile("l2", {"mode": "ephemeral-target"}), capability=_capability("L2", status="inapplicable"), target={})
    assert plan["status"] == "blocked"
    assert "capability_inapplicable" in plan["blockers"]
    assert "sandbox_blueprint_or_container_facts_required" in plan["blockers"]


def test_lease_state_machine_and_atomic_store(tmp_path):
    now = datetime.now(timezone.utc)
    lease = with_hash({
        "schema_version": "chaosatlas-environment-lease-v1",
        "lease_id": "lease-abc",
        "plan_id": "plan-abc",
        "project_id": "fixture",
        "provider": "kubernetes-l1",
        "isolation_level": "L1",
        "state": "planned",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(),
        "owner_labels": {"chaosatlas.dev/managed": "true"},
        "resources": [],
        "external_profiles": [],
        "cleanup_attempts": 0,
        "last_error": None,
    }, "lease_sha256")
    assert validate_lease(lease) == []
    preparing = transition_lease(lease, "preparing")
    with pytest.raises(ValueError, match="invalid lease transition"):
        transition_lease(preparing, "released")
    store = LeaseStore(tmp_path)
    store.save(preparing, require_new=True)
    assert store.load("lease-abc") == preparing
    assert store.active(project_id="fixture") == [preparing]


def test_store_refuses_tampered_lease(tmp_path):
    store = LeaseStore(tmp_path)
    store.leases.mkdir(parents=True)
    (store.leases / "lease-bad.json").write_text('{"lease_id":"lease-bad"}', encoding="utf-8")
    with pytest.raises(ValueError, match="integrity"):
        store.load("lease-bad")


def test_store_creation_lock_fails_closed_on_concurrent_creator(tmp_path):
    store = LeaseStore(tmp_path)
    with store.creation_lock():
        with pytest.raises(RuntimeError, match="already in progress"):
            with store.creation_lock():
                pass


def test_planner_blocks_sensitive_material_without_copying_its_value_to_reason():
    profile = _profile("l2", {"mode": "ephemeral-target", "blueprint": {"resources": [{"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "bad"}, "data": {"api_token": "do-not-copy-this"}}]}})
    plan = IsolationPlanner().plan(profile=profile, capability=_capability("L2"), target={})
    assert plan["status"] == "blocked"
    assert any(item.startswith("sensitive_material_detected:") for item in plan["blockers"])
    assert all("do-not-copy-this" not in item for item in plan["blockers"])


def test_planner_covers_all_32_plus_9_catalog_defaults():
    safe_workload = {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "sandbox"}, "spec": {"selector": {"matchLabels": {"app": "sandbox"}}, "template": {"metadata": {"labels": {"app": "sandbox"}}, "spec": {"containers": [{"name": "sandbox", "image": "registry.k8s.io/pause:3.9"}]}}}}
    profile = {
        "project_id": "fixture",
        "project_commit": "revision",
        "namespace_policy": {"allowed_namespaces": ["fixture-lab"]},
        "isolation": {
            "synthetic_data_only": True,
            "l1": {"mode": "adopted-test-replica", "dedicated_test_replica": True},
            "l2": {"mode": "ephemeral-target", "blueprint": {"resources": [safe_workload]}},
            "l3": {"mode": "ephemeral-cluster"},
        },
    }
    mappings = {fault_id: isolation_for_core_fault(fault_id) for fault_id in fault_catalog()}
    mappings.update({fault_id: isolation_for_extension(fault_id) for fault_id in extension_catalog()})
    assert len(mappings) == 41
    target = {"deployment": {"resources": {"limits": {"memory": "256Mi"}}}}
    plans = [IsolationPlanner().plan(profile=profile, capability=_capability(level, fault_id), target=target) for fault_id, level in mappings.items()]
    assert all(plan["status"] == "ready" for plan in plans)
    assert {plan["capability_id"] for plan in plans} == set(mappings)
    assert all(plan["effective_isolation"] == mappings[plan["capability_id"]] for plan in plans)
