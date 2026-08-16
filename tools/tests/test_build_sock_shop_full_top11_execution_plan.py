import json
from pathlib import Path

import pytest

from tools.build_sock_shop_full_top11_execution_plan import build_execution_plan, classify_execution_entries


def _top(rank, hypothesis_id, instance_key):
    return {
        "rank": rank,
        "hypothesis_id": hypothesis_id,
        "mutation_instance_key": instance_key,
        "executable_mutation_key": instance_key.replace("|call_chain_position=entry", ""),
        "source_path": f"{hypothesis_id}.yaml",
        "mutation_sha256": f"sha-{hypothesis_id}",
    }


def test_execution_plan_keeps_blocked_and_only_reuses_two_valid_reports():
    top = [
        _top(1, "blocked", "kind=HTTPChaos|call_chain_position=entry|parameters=x"),
        _top(2, "reused", "kind=PodChaos|call_chain_position=entry|parameters=y"),
        _top(3, "fresh", "kind=StressChaos|call_chain_position=entry|parameters=z"),
    ]
    gate = {
        "blocked.yaml": {"decision": "blocked", "errors": ["target_port_missing:80"]},
        "reused.yaml": {"decision": "ready_for_injection", "errors": []},
        "fresh.yaml": {"decision": "ready_for_injection", "errors": []},
    }
    top[0]["source_path"] = "blocked.yaml"
    top[1]["source_path"] = "reused.yaml"
    top[2]["source_path"] = "fresh.yaml"
    evidence = {
        top[1]["executable_mutation_key"]: {
            "mutation_instance_key": top[1]["mutation_instance_key"],
            "reports": [
                {"replicate": 1, "valid": True, "mutation_sha256": top[1]["mutation_sha256"]},
                {"replicate": 2, "valid": True, "mutation_sha256": top[1]["mutation_sha256"]},
            ]
        },
        top[2]["executable_mutation_key"]: {"reports": [{"replicate": 1, "valid": True}]},
    }

    result = classify_execution_entries(top, gate, evidence)

    assert [item["execution_status"] for item in result] == ["blocked", "reused_historical", "fresh_required"]
    assert result[0]["gate_errors"] == ["target_port_missing:80"]
    assert result[1]["fresh_units"] == []
    assert [unit["replicate"] for unit in result[2]["fresh_units"]] == [1, 2]


def test_execution_plan_reuses_same_executable_mutation_despite_call_chain_wording():
    item = _top(1, "full", "kind=PodChaos|call_chain_position=entry|parameters=x")
    gate = {"full.yaml": {"decision": "ready_for_injection", "errors": []}}
    item["source_path"] = "full.yaml"
    evidence = {
        "kind=PodChaos|parameters=x": {
            "mutation_instance_key": item["mutation_instance_key"],
            "reports": [
                {"replicate": 1, "valid": True, "mutation_sha256": item["mutation_sha256"]},
                {"replicate": 2, "valid": True, "mutation_sha256": item["mutation_sha256"]},
            ]
        }
    }

    result = classify_execution_entries([item], gate, evidence)

    assert result[0]["execution_status"] == "reused_historical"


def test_execution_plan_rejects_historical_mutation_sha_mismatch():
    item = _top(1, "full", "kind=PodChaos|call_chain_position=entry|parameters=x")
    item["source_path"] = "full.yaml"
    gate = {"full.yaml": {"decision": "ready_for_injection", "errors": []}}
    evidence = {
        item["executable_mutation_key"]: {
            "mutation_instance_key": item["mutation_instance_key"],
            "reports": [
                {"replicate": 1, "valid": True, "mutation_sha256": "wrong"},
                {"replicate": 2, "valid": True, "mutation_sha256": "wrong"},
            ],
        }
    }

    with pytest.raises(ValueError, match="historical mutation SHA-256"):
        classify_execution_entries([item], gate, evidence)


def test_execution_plan_rejects_gate_manifest_hash_mismatch(tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"top11": []}), encoding="utf-8")
    gate = tmp_path / "gate.json"
    gate.write_text(json.dumps({"selection_manifest_sha256": "wrong", "results": []}), encoding="utf-8")
    discovery = tmp_path / "discovery.json"
    discovery.write_text(json.dumps({"hypotheses": []}), encoding="utf-8")
    reports = tmp_path / "reports"
    reports.mkdir()

    with pytest.raises(ValueError, match="does not match manifest SHA-256"):
        build_execution_plan(manifest, gate, discovery, reports, tmp_path / "plan.json")


def test_execution_plan_requires_gate_entry_for_each_top11_path(tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"top11": [{"source_path": "missing.yaml"}]}),
        encoding="utf-8",
    )
    gate = tmp_path / "gate.json"
    gate.write_text(json.dumps({"results": []}), encoding="utf-8")
    discovery = tmp_path / "discovery.json"
    discovery.write_text(json.dumps({"hypotheses": []}), encoding="utf-8")
    reports = tmp_path / "reports"
    reports.mkdir()

    with pytest.raises(ValueError, match="missing Top 11 mutation provenance"):
        build_execution_plan(manifest, gate, discovery, reports, tmp_path / "plan.json")
