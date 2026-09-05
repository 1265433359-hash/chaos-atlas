from chaosatlas.capabilities.extension_assessment import assess_extension_capabilities


def _profile():
    return {
        "project_id": "fixture",
        "project_commit": "revision",
        "business_oracles": [{"id": "health"}],
        "recovery": {"deadline_s": 60},
    }


def _node():
    return {
        "node_id": "node:web",
        "deployment": {"name": "web", "workload_kind": "Deployment"},
        "extensions": {
            "runtime": {"jvm_present": False},
            "writable_paths": [],
            "capabilities": {},
        },
    }


def _runtime(network=True):
    return {
        "chaos_mesh": {"ready": network},
        "crds": {
            "IOChaos": {"available": True},
            "TimeChaos": {"available": True},
            "JVMChaos": {"available": True},
            "NetworkChaos": {"available": network},
        },
    }


def test_extension_assessment_has_seven_workload_and_two_placeholders_without_edges():
    records = assess_extension_capabilities(_profile(), [_node()], [], _runtime())
    assert len(records) == 9
    assert len({item["fault_id"] for item in records}) == 9
    dependency = [item for item in records if item["fault_id"].startswith("extension.dependency_")]
    assert all(item["target_id"] is None and item["capability_status"] == "inapplicable" for item in dependency)
    io_delay = next(item for item in records if item["fault_id"] == "extension.io_delay")
    assert io_delay["capability_status"] == "inapplicable"
    assert "IOChaos" not in io_delay["prerequisites"]


def test_dependency_extensions_are_scoped_per_declared_edge_and_require_runtime():
    edge = {
        "id": "web-cache",
        "source": "web",
        "target": "cache",
        "source_selector": {"app": "web"},
        "target_selector": {"app": "cache"},
        "oracle_id": "health",
    }
    records = assess_extension_capabilities(_profile(), [_node()], [edge], _runtime(network=False))
    dependency = [item for item in records if item["fault_id"].startswith("extension.dependency_")]
    assert len(dependency) == 2
    assert all(item["target_id"] == "dependency:web-cache" for item in dependency)
    assert all(item["capability_status"] == "blocked" for item in dependency)
