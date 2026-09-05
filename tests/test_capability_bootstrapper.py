import json

from chaosatlas.capabilities.bootstrap import CapabilityBootstrapper
from chaosatlas.capabilities.evidence import CapabilityEvidenceIndex


class _Adapter:
    kube_context = "test"

    def __init__(self):
        self.calls = []

    def inventory(self):
        return {
            "status": "verified",
            "checked_at": "volatile-inventory-time",
            "project_id": "fixture",
            "project_commit": "revision",
            "namespace": "lab",
            "dependencies": [],
            "warnings": [],
        }

    def build_capability_nodes(self, _inventory):
        return {
            "status": "verified",
            "deployment_nodes": [{
                "node_id": "node:web",
                "deployment": {"name": "web", "workload_kind": "Deployment", "containers": ["web"]},
                "service": {"name": "web"},
                "extensions": {"runtime": {"jvm_present": False}, "capabilities": {}, "resource_facts": {}},
            }],
            "errors": [],
        }

    def runner(self, args, timeout=30):
        self.calls.append(list(args))
        command = args[2:] if args[:2] == ["--context", "test"] else args
        if command[:2] == ["get", "crd"]:
            return 0, "ok", ""
        if command[:2] == ["get", "pods"]:
            return 0, json.dumps({"items": []}), ""
        raise AssertionError(f"non-read-only command: {command}")


def _profile():
    return {
        "project_id": "fixture",
        "project_commit": "revision",
        "business_oracles": [{"id": "health"}],
        "recovery": {"deadline_s": 60},
        "cleanup": {"owner": "chaosatlas"},
    }


def test_bootstrapper_outputs_complete_read_only_32_plus_9_matrix():
    adapter = _Adapter()
    result = CapabilityBootstrapper(profile=_profile(), adapter=adapter).run()

    assert result["status"] == "verified"
    assert result["catalog"] == {"core": 32, "extension": 9, "total": 41}
    assert len(result["project_capabilities"]) == 41
    assert len({item["fault_id"] for item in result["project_capabilities"]}) == 41
    assert result["read_only"] is True
    assert result["injection_performed"] is False
    assert all((call[2:] if call[:2] == ["--context", "test"] else call)[0] == "get" for call in adapter.calls)


def test_bootstrap_hashes_ignore_probe_and_inventory_timestamps():
    first = CapabilityBootstrapper(profile=_profile(), adapter=_Adapter()).run()
    second = CapabilityBootstrapper(profile=_profile(), adapter=_Adapter()).run()
    assert first["input_snapshot_sha256"] == second["input_snapshot_sha256"]
    assert first["output_sha256"] == second["output_sha256"]


def test_inventory_failure_is_reported_without_runtime_calls():
    adapter = _Adapter()
    adapter.inventory = lambda: {"status": "environment_blocked", "errors": ["cluster unavailable"], "warnings": []}
    result = CapabilityBootstrapper(profile=_profile(), adapter=adapter).run()
    assert result["status"] == "environment_blocked"
    assert result["injection_performed"] is False
    assert adapter.calls == []


def test_historical_evidence_does_not_override_a_current_runtime_block():
    evidence = CapabilityEvidenceIndex(entries=[{
        "project_id": "fixture",
        "project_revision": "revision",
        "target": "web",
        "fault_id": "pod_kill",
        "parameter_digest": "same",
        "run_id": "run-1",
        "evidence_ref": "run-1/summary.json",
    }])
    result = CapabilityBootstrapper(profile=_profile(), adapter=_Adapter(), evidence_index=evidence).run()
    pod_kill = next(item for item in result["target_capabilities"] if item["fault_id"] == "pod_kill")
    assert pod_kill["evidence_grade"] == "E2"
    assert pod_kill["capability_status"] == "blocked"
    assert pod_kill["candidate_eligible"] is False
