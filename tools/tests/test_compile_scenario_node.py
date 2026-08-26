from __future__ import annotations

import json
from pathlib import Path

from tools.compile_scenario_node import compile_scenario
from tools.tests.test_deployment_capability import scenario


def test_compile_scenario_is_deterministic_and_namespace_local():
    value = scenario()
    result = compile_scenario(value)
    assert result["status"] == "verified"
    manifest = result["phases"][0]["manifests"][0]
    assert manifest["metadata"]["namespace"] == "ns"
    assert manifest["metadata"]["labels"]["chaosatlas.dev/phase"] == "kill"
    assert manifest["spec"]["selector"]["namespaces"] == ["ns"]
    assert manifest["spec"]["selector"]["labelSelectors"] == {"name": "front-end"}
    assert "namespaces" not in manifest["spec"]
    assert "labelSelectors" not in manifest["spec"]
    assert result["scenario_hash"] == compile_scenario(json.loads(json.dumps(value)))["scenario_hash"]


def test_compile_scenario_rejects_unknown_fault_without_side_effects():
    value = scenario()
    value["phases"][0]["faults"][0]["kind"] = "alien"
    result = compile_scenario(value)
    assert result["status"] == "method_invalid"
    assert result["manifests"] == []
