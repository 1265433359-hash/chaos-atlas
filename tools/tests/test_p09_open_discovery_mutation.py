from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from tools.p09_open_discovery_mutation import (
    P09MutationCompileError,
    compile_frozen_discovery_results,
    compile_p09_hypothesis,
)


def topology() -> dict:
    return {
        "graph_hash": "g" * 64,
        "nodes": [
            {
                "id": "compose/service/api",
                "kind": "ComposeService",
                "name": "api",
                "role": "workload",
                "labels": {},
            }
        ],
        "edges": [],
    }


def runtime_map() -> dict:
    return {
        "targets": {
            "compose/service/api": {
                "namespace": "chaosatlas-p09",
                "workload": {"kind": "Deployment", "name": "api"},
                "selector": {
                    "app.kubernetes.io/name": "api",
                    "app.kubernetes.io/part-of": "chaosatlas-p09",
                },
            }
        }
    }


def hypothesis() -> dict:
    core = {
        "target": "compose/service/api",
        "target_kind": "service",
        "fault_family": "pod_kill",
        "parameters": {"mode": "one"},
    }
    return {
        "project_id": "P09",
        "project_commit": "c" * 40,
        "namespace": "chaosatlas-p09",
        "hypothesis_id": "h-api-kill",
        "canonical_signature": hashlib.sha256(
            __import__("json").dumps(
                core, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest(),
        **core,
    }


def test_compile_frozen_p09_hypothesis_to_podchaos(tmp_path: Path) -> None:
    result = compile_p09_hypothesis(
        hypothesis=hypothesis(),
        topology=topology(),
        runtime_map=runtime_map(),
        output_dir=tmp_path,
    )

    mutation = yaml.safe_load(result["yaml"])

    assert mutation["metadata"]["namespace"] == "chaosatlas-p09"
    assert mutation["kind"] == "PodChaos"
    assert result["provenance"]["human_review"] == "pending"
    assert result["provenance"]["execution_ready"] is False
    assert result["manifest"]["mutation_sha256"] == hashlib.sha256(
        result["yaml"].encode("utf-8")
    ).hexdigest()


def test_compile_rejects_non_p09_namespace(tmp_path: Path) -> None:
    item = hypothesis()
    item["namespace"] = "default"

    with pytest.raises(P09MutationCompileError, match="namespace"):
        compile_p09_hypothesis(item, topology(), runtime_map(), tmp_path)


def test_compile_rejects_missing_runtime_mapping(tmp_path: Path) -> None:
    with pytest.raises(P09MutationCompileError, match="runtime mapping"):
        compile_p09_hypothesis(hypothesis(), topology(), {"targets": {}}, tmp_path)


def test_compile_refuses_nonempty_output_directory(tmp_path: Path) -> None:
    (tmp_path / "existing.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(P09MutationCompileError, match="non-empty"):
        compile_p09_hypothesis(hypothesis(), topology(), runtime_map(), tmp_path)


def test_compile_frozen_results_deduplicates_signatures_and_writes_manifest(
    tmp_path: Path,
) -> None:
    source = tmp_path / "seed-1001" / "chaosatlas-kb-open"
    source.mkdir(parents=True)
    result = {
        "status": "valid",
        "project_id": "P09",
        "compiled": {
            "accepted": [hypothesis(), hypothesis()],
        },
    }
    (source / "result.json").write_text(
        json.dumps(result), encoding="utf-8"
    )
    output = tmp_path / "compiled"

    summary = compile_frozen_discovery_results(
        results_root=tmp_path,
        topology=topology(),
        runtime_map=runtime_map(),
        output_dir=output,
    )

    assert summary["status"] == "completed"
    assert summary["unique_hypotheses"] == 1
    assert summary["generated_mutations"] == 1
    assert (output / "mutation-001" / "manifest.json").exists()
    assert (output / "summary.json").exists()


def test_compile_frozen_results_refuses_nonempty_output(tmp_path: Path) -> None:
    source = tmp_path / "seed-1001" / "chaosatlas-kb-open"
    source.mkdir(parents=True)
    (source / "result.json").write_text(
        json.dumps({"status": "valid", "compiled": {"accepted": []}}),
        encoding="utf-8",
    )
    output = tmp_path / "compiled"
    output.mkdir()
    (output / "keep").write_text("keep", encoding="utf-8")

    with pytest.raises(P09MutationCompileError, match="non-empty"):
        compile_frozen_discovery_results(
            results_root=tmp_path,
            topology=topology(),
            runtime_map=runtime_map(),
            output_dir=output,
        )
