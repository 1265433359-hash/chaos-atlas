from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest
import yaml

from tools.build_same_pool_fair_inputs import build_candidate_pool, write_freeze


FORBIDDEN = ("weakness_observed", "no_business_impact_observed", "runtime-results", "native-full-rca")


def test_build_candidate_pool_is_result_free_and_namespace_local() -> None:
    pool = build_candidate_pool()

    assert set(pool) == {"online-boutique", "opentelemetry-demo", "sock-shop"}
    assert all(pool[project] for project in pool)
    encoded = json.dumps(pool, sort_keys=True)
    assert not any(term in encoded for term in FORBIDDEN)

    for project, candidates in pool.items():
        namespace = {
            "online-boutique": "chaosatlas-online-boutique",
            "opentelemetry-demo": "chaosatlas-otel",
            "sock-shop": "chaosatlas-sock-shop",
        }[project]
        label_key = "name" if project == "sock-shop" else "app"
        ids = [candidate["candidate_id"] for candidate in candidates]
        assert len(ids) == len(set(ids))
        for candidate in candidates:
            doc = yaml.safe_load(candidate["yaml"])
            assert doc["metadata"]["namespace"] == namespace
            assert doc["spec"]["selector"]["namespaces"] == [namespace]
            assert set(doc["spec"]["selector"]["labelSelectors"]) == {label_key}
            assert candidate["yaml_sha256"]


def test_write_freeze_refuses_non_empty_directory(tmp_path: Path) -> None:
    output = tmp_path / "freeze"
    output.mkdir()
    (output / "existing.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError):
        write_freeze(output)


def test_write_freeze_emits_manifest_and_method_inputs(tmp_path: Path) -> None:
    output = tmp_path / "freeze"
    result = write_freeze(output)

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "chaosatlas-same-pool-fair-freeze-v1"
    assert manifest["pool_sha256"] == result["pool_sha256"]
    assert manifest["human_review"] == "pending"
    assert manifest["knowledge_base_updated"] is False
    assert (output / "candidate_pools" / "online-boutique" / "candidates.json").is_file()
    assert (output / "method_inputs" / "online-boutique" / "seed-1001" / "ChaosAtlas-full.json").is_file()
    assert (output / "method_inputs" / "online-boutique" / "seed-1001" / "ChaosAtlas-ablation.json").is_file()
    assert (output / "method_inputs" / "online-boutique" / "seed-1001" / "ChaosEater-adapter.json").is_file()

    full = json.loads((output / "method_inputs" / "online-boutique" / "seed-1001" / "ChaosAtlas-full.json").read_text(encoding="utf-8"))
    ablation = json.loads((output / "method_inputs" / "online-boutique" / "seed-1001" / "ChaosAtlas-ablation.json").read_text(encoding="utf-8"))
    eater = json.loads((output / "method_inputs" / "online-boutique" / "seed-1001" / "ChaosEater-adapter.json").read_text(encoding="utf-8"))
    assert full["candidate_pool_sha256"] == ablation["candidate_pool_sha256"] == eater["candidate_pool_sha256"]
    assert full["knowledge_view"] is not None
    assert ablation["knowledge_view"] is None
    assert eater["knowledge_view"]["style"] == "chaoseater_adapter"


def test_write_freeze_records_actual_yaml_file_hash(tmp_path: Path) -> None:
    output = tmp_path / "freeze"
    write_freeze(output)
    candidates = json.loads((output / "candidate_pools" / "online-boutique" / "candidates.json").read_text(encoding="utf-8"))

    for candidate in candidates[:5]:
        yaml_path = output / candidate["yaml_path"]
        actual = hashlib.sha256(yaml_path.read_bytes()).hexdigest()
        assert candidate["yaml_sha256"] == actual
