import json
from pathlib import Path
import subprocess
import sys

import yaml

from tools.build_sock_shop_hypothesis_identity_audit import (
    build_identity_audit,
    select_matched_full_only,
)


def _hypothesis(identifier, method, target, confidence):
    return {
        "id": identifier,
        "method": method,
        "category": "Network degradation",
        "target_service": target,
        "action_or_target": "delay",
        "call_chain_position": "business-service",
        "confidence": confidence,
        "stop_snapshot": {"upper95": 1 - confidence},
    }


def _mutation(path: Path, target: str, latency: str = "500ms"):
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "NetworkChaos",
        "metadata": {"name": path.stem, "namespace": "chaosatlas-sock-shop"},
        "spec": {
            "action": "delay",
            "mode": "one",
            "duration": "30s",
            "selector": {
                "namespaces": ["chaosatlas-sock-shop"],
                "labelSelectors": {"name": target},
            },
            "delay": {"latency": latency},
        },
    }
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


def _inputs(root: Path):
    full_mutation = root / "full.yaml"
    ablation_mutation = root / "ablation.yaml"
    _mutation(full_mutation, "catalogue")
    _mutation(ablation_mutation, "catalogue")
    full_hyp = _hypothesis("full-1", "native-full", "catalogue", 0.9)
    ablation_hyp = _hypothesis("ab-1", "chaosatlas-ablation", "catalogue", 0.1)
    full_discovery = root / "full-discovery.json"
    ablation_discovery = root / "ablation-discovery.json"
    full_discovery.write_text(json.dumps({"method": "native-full", "status": "completed", "hypotheses": [full_hyp]}), encoding="utf-8")
    ablation_discovery.write_text(json.dumps({"method": "chaosatlas-ablation", "status": "completed", "hypotheses": [ablation_hyp]}), encoding="utf-8")
    full_plan = root / "full-plan.json"
    ablation_plan = root / "ablation-plan.json"
    candidate = lambda path, hypothesis: {
        "hypothesis_id": hypothesis["id"],
        "path": str(path),
        "sha256": __import__("hashlib").sha256(path.read_bytes()).hexdigest(),
        "hypothesis": hypothesis,
    }
    full_plan.write_text(json.dumps({"methods": {"native-full": {"candidates": [candidate(full_mutation, full_hyp)]}}}), encoding="utf-8")
    ablation_plan.write_text(json.dumps({"methods": {"chaosatlas-ablation": {"candidates": [candidate(ablation_mutation, ablation_hyp)]}}}), encoding="utf-8")
    return full_discovery, ablation_discovery, full_plan, ablation_plan


def test_identity_audit_writes_hash_pinned_overlap_and_selection(tmp_path):
    inputs = _inputs(tmp_path / "inputs")
    output = tmp_path / "audit"

    result = build_identity_audit(*inputs, output_dir=output, sample_seed=17, high_confidence_quantile=0.75)

    assert result["human_review"] == "pending"
    assert result["knowledge_base_updated"] is False
    assert result["sets"]["strict_overlap_count"] == 1
    assert (output / "old_new_key_audit.json").exists()
    assert (output / "overlap_audit.json").exists()
    assert (output / "selection_manifest.json").exists()
    assert (output / "selection_manifest.sha256").exists()
    selection = json.loads((output / "selection_manifest.json").read_text(encoding="utf-8"))
    expected_file_sha = (output / "selection_manifest.sha256").read_text(encoding="utf-8").split()[0]
    actual_file_sha = __import__("hashlib").sha256((output / "selection_manifest.json").read_bytes()).hexdigest()
    assert expected_file_sha == actual_file_sha
    assert selection["selection_content_sha256"]
    assert selection["config"]["sample_seed"] == 17
    assert len(selection["groups"]["overlap_high_confidence"]) == 1
    assert selection["groups"]["overlap_high_confidence"][0]["mutation_source"] == "full"
    assert selection["groups"]["full_only_high_confidence"] == []


def test_identity_audit_refuses_non_empty_output(tmp_path):
    inputs = _inputs(tmp_path / "inputs")
    output = tmp_path / "audit"
    output.mkdir()
    (output / "keep.txt").write_text("keep", encoding="utf-8")

    try:
        build_identity_audit(*inputs, output_dir=output)
    except FileExistsError as exc:
        assert "non-empty" in str(exc)
    else:
        raise AssertionError("expected non-empty output refusal")


def test_direct_script_invocation_bootstraps_repository_imports(tmp_path):
    inputs = _inputs(tmp_path / "inputs")
    output = tmp_path / "audit"
    completed = subprocess.run(
        [
            sys.executable,
            "tools/build_sock_shop_hypothesis_identity_audit.py",
            "--full-discovery",
            str(inputs[0]),
            "--ablation-discovery",
            str(inputs[1]),
            "--full-runtime-plan",
            str(inputs[2]),
            "--ablation-runtime-plan",
            str(inputs[3]),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert completed.returncode == 0, completed.stderr
    assert (output / "selection_manifest.json").exists()


def test_full_only_selection_is_capped_to_available_ablation_only_pool():
    full = [
        {"confidence_score": 0.95, "mutation_instance_key": "full-a"},
        {"confidence_score": 0.90, "mutation_instance_key": "full-b"},
        {"confidence_score": 0.80, "mutation_instance_key": "full-c"},
    ]
    ablation = [
        {"mutation_instance_key": "ab-a"},
        {"mutation_instance_key": "ab-b"},
    ]

    full_selected, ablation_selected, metadata = select_matched_full_only(
        full,
        ablation,
        threshold=0.75,
        sample_seed=17,
    )

    assert [item["mutation_instance_key"] for item in full_selected] == ["full-a", "full-b"]
    assert len(ablation_selected) == 2
    assert metadata["full_high_confidence_candidates"] == 3
    assert metadata["matched_sample_size"] == 2
