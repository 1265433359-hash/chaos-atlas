from chaosatlas.capabilities.core_assessment import assess_core_capabilities


def _profile(**updates):
    value = {
        "project_id": "fixture",
        "project_commit": "revision",
        "business_oracles": [{"id": "health"}],
        "recovery": {"deadline_s": 60},
        "cleanup": {"owner": "chaosatlas"},
    }
    value.update(updates)
    return value


def _node(*, service=True, disposable=False, capabilities=None, workload_kind="Deployment"):
    return {
        "node_id": "node:web",
        "deployment": {"name": "web", "workload_kind": workload_kind, "containers": ["web"]},
        "service": {"name": "web"} if service else None,
        "extensions": {
            "capabilities": capabilities or {},
            "resource_facts": {
                "disposable_target": disposable,
                "secret_count": 1,
            },
        },
    }


def _runtime():
    backends = ("PodChaos", "StressChaos", "NetworkChaos", "DNSChaos", "HTTPChaos")
    return {
        "chaos_mesh": {"ready": True},
        "crds": {name: {"available": True} for name in backends},
        "httpchaos_runtime_verified": False,
    }


def test_core_assessment_covers_all_32_without_treating_implemented_as_verified():
    records = assess_core_capabilities(_profile(), [_node()], _runtime())
    assert len(records) == 32
    assert {item["fault_id"] for item in records}.__len__() == 32
    assert not any(item["capability_status"] == "supported" for item in records)
    assert next(item for item in records if item["fault_id"] == "pod_kill")["evidence_grade"] == "E1"


def test_core_assessment_keeps_http_and_native_mutations_fail_closed():
    records = assess_core_capabilities(_profile(), [_node(service=False)], _runtime())
    assert next(item for item in records if item["fault_id"] == "http_delay")["capability_status"] == "inapplicable"
    disk = next(item for item in records if item["fault_id"] == "disk_pressure")
    assert disk["capability_status"] == "blocked"
    assert {"disposable_target", "native_resource_capability"}.issubset(disk["prerequisites"])
    api = next(item for item in records if item["fault_id"] == "api_server_delay")
    assert api["required_isolation"] == "L3"
    assert api["capability_status"] == "blocked"


def test_core_assessment_preserves_profile_boundary_and_allows_declared_safe_native_target():
    profile = _profile(fault_support={"network_delay": {"status": "not_reachable", "reason": "policy"}})
    node = _node(disposable=True, capabilities={"native_resource": True})
    records = assess_core_capabilities(profile, [node], _runtime())
    boundary = next(item for item in records if item["fault_id"] == "network_delay")
    assert boundary["capability_status"] == "blocked"
    assert boundary["original_status"] == "not_reachable"
    native = next(item for item in records if item["fault_id"] == "disk_pressure")
    assert native["capability_status"] == "canary_required"


def test_api_server_delay_uses_verified_platform_evidence_as_canary_boundary():
    runtime = {**_runtime(), "api_server_delay_runtime_verified": True}
    api = next(item for item in assess_core_capabilities(_profile(), [_node()], runtime) if item["fault_id"] == "api_server_delay")
    assert api["capability_status"] == "canary_required"
    assert api["evidence_grade"] == "E1"
