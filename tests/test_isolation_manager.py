from datetime import datetime, timedelta, timezone
import threading

import pytest

from chaosatlas.isolation.lease_store import LeaseStore
from chaosatlas.isolation.manager import IsolationManager
from chaosatlas.isolation.planner import IsolationPlanner
from chaosatlas.isolation.providers import ProviderRegistry


class FakeProvider:
    name = "kubernetes-l1"

    def __init__(self, *, fail_prepare=False, fail_cleanup=False, raise_cleanup=False):
        self.fail_prepare = fail_prepare
        self.fail_cleanup = fail_cleanup
        self.raise_cleanup = raise_cleanup
        self.cleanup_calls = 0

    def preflight(self, plan):
        return []

    def supports(self, plan):
        return plan.get("provider") == self.name

    def prepare(self, plan, lease, mutate):
        mutate("register_resource", {"kind": "Namespace", "namespace": None, "name": lease["target_name"], "actual_uid": "uid-1", "cleanup_policy": "delete"})
        if self.fail_prepare:
            raise RuntimeError("prepare boom")

    def verify_ready(self, plan, lease):
        return {"status": "verified", "checks": {"ready": True}, "errors": []}

    def cleanup(self, plan, lease):
        self.cleanup_calls += 1
        if self.raise_cleanup:
            raise RuntimeError("cleanup runner crashed")
        return {"status": "blocked", "reason": "cleanup boom"} if self.fail_cleanup else {"status": "released"}

    def verify_absent(self, plan, lease):
        return {"confirmed": True, "errors": []}


def _plan():
    profile = {"project_id": "fixture", "project_commit": "r", "namespace_policy": {"allowed_namespaces": ["fixture-lab"]}, "isolation": {"l1": {"mode": "adopted-test-replica", "dedicated_test_replica": True}, "synthetic_data_only": True}}
    capability = {"fault_id": "pod_kill", "target_id": "n1", "required_isolation": "L1", "capability_status": "canary_required"}
    return IsolationPlanner().plan(profile=profile, capability=capability, target={})


def test_manager_persists_before_prepare_and_releases_idempotently(tmp_path):
    provider = FakeProvider()
    manager = IsolationManager(store=LeaseStore(tmp_path), providers=ProviderRegistry([provider]))
    lease = manager.prepare(_plan())
    assert lease["state"] == "ready"
    released = manager.release(lease["lease_id"])
    assert released["state"] == "released"
    assert manager.release(lease["lease_id"])["state"] == "released"
    assert provider.cleanup_calls == 1


def test_partial_prepare_failure_runs_cleanup_and_keeps_error(tmp_path):
    provider = FakeProvider(fail_prepare=True)
    manager = IsolationManager(store=LeaseStore(tmp_path), providers=ProviderRegistry([provider]))
    lease = manager.prepare(_plan())
    assert lease["state"] == "released"
    assert "prepare boom" in lease["last_error"]
    assert provider.cleanup_calls == 1


def test_cleanup_failure_blocks_new_project_lease_until_recovery(tmp_path):
    provider = FakeProvider(fail_cleanup=True)
    manager = IsolationManager(store=LeaseStore(tmp_path), providers=ProviderRegistry([provider]))
    lease = manager.prepare(_plan())
    failed = manager.release(lease["lease_id"])
    assert failed["state"] == "cleanup_failed"
    with pytest.raises(RuntimeError, match="active isolation lease"):
        manager.prepare(_plan())


def test_reaper_releases_expired_lease(tmp_path):
    provider = FakeProvider()
    store = LeaseStore(tmp_path)
    manager = IsolationManager(store=store, providers=ProviderRegistry([provider]))
    lease = manager.prepare(_plan())
    lease["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    from chaosatlas.isolation.contracts import with_hash
    store.save(with_hash(lease, "lease_sha256"))
    assert manager.reap_expired()[0]["state"] == "released"


def test_cleanup_runner_exception_is_persisted_as_cleanup_failed(tmp_path):
    manager = IsolationManager(store=LeaseStore(tmp_path), providers=ProviderRegistry([FakeProvider(raise_cleanup=True)]))
    lease = manager.prepare(_plan())
    failed = manager.release(lease["lease_id"])
    assert failed["state"] == "cleanup_failed"
    assert "cleanup runner crashed" in failed["last_error"]


def test_damaged_lease_stops_reaper_without_guessing_cleanup(tmp_path):
    provider = FakeProvider()
    store = LeaseStore(tmp_path)
    store.leases.mkdir(parents=True)
    (store.leases / "lease-damaged.json").write_text('{"state":"ready"}', encoding="utf-8")
    manager = IsolationManager(store=store, providers=ProviderRegistry([provider]))
    with pytest.raises(ValueError, match="integrity"):
        manager.reap_expired()
    assert provider.cleanup_calls == 0


def test_reaper_skips_a_prepare_that_holds_the_operation_lock(tmp_path):
    entered = threading.Event()
    proceed = threading.Event()

    class BlockingProvider(FakeProvider):
        def prepare(self, plan, lease, mutate):
            entered.set()
            assert proceed.wait(5)
            super().prepare(plan, lease, mutate)

    store = LeaseStore(tmp_path, coordination_root=tmp_path / "coordination")
    manager = IsolationManager(store=store, providers=ProviderRegistry([BlockingProvider()]))
    result = []
    worker = threading.Thread(target=lambda: result.append(manager.prepare(_plan(), ttl_minutes=1)))
    worker.start()
    assert entered.wait(5)
    assert manager.reap_expired(now=datetime.now(timezone.utc) + timedelta(minutes=2)) == []
    proceed.set()
    worker.join(5)
    assert result and result[0]["state"] == "ready"
    assert manager.release(result[0]["lease_id"])["state"] == "released"


def test_whole_machine_l3_claim_applies_across_store_roots(tmp_path):
    coordination = tmp_path / "coordination"
    first = LeaseStore(tmp_path / "one", coordination_root=coordination)
    second = LeaseStore(tmp_path / "two", coordination_root=coordination)
    lease = {"lease_id": "lease-global-one", "provider": "minikube-l3", "created_at": datetime.now(timezone.utc).isoformat()}
    with first.creation_lock():
        first.assert_l3_available()
        first.claim_l3(lease)
    with second.creation_lock():
        with pytest.raises(RuntimeError, match="already active"):
            second.assert_l3_available()
    first.release_l3_claim("lease-global-one")
    with second.creation_lock():
        second.assert_l3_available()


def test_keyboard_interrupt_runs_owned_cleanup_before_propagating(tmp_path):
    class InterruptedProvider(FakeProvider):
        def prepare(self, plan, lease, mutate):
            super().prepare(plan, lease, mutate)
            raise KeyboardInterrupt()

    provider = InterruptedProvider()
    store = LeaseStore(tmp_path, coordination_root=tmp_path / "coordination")
    manager = IsolationManager(store=store, providers=ProviderRegistry([provider]))
    with pytest.raises(KeyboardInterrupt):
        manager.prepare(_plan())
    leases = store.list()
    assert len(leases) == 1 and leases[0]["state"] == "released"
    assert provider.cleanup_calls == 1
