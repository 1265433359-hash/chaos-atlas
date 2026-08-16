import hashlib
import json
from pathlib import Path

import pytest
import yaml

from tools.build_sock_shop_ablation_yaml15 import build_yaml15_manifest


CATEGORY_KINDS = {
    "Pod disruption": "PodChaos",
    "Network degradation": "NetworkChaos",
    "Resource pressure": "StressChaos",
    "Protocol/HTTP fault": "HTTPChaos",
    "Composite/scheduled fault": "Schedule",
}


def _spec(kind: str, index: int) -> dict:
    selector = {
        "namespaces": [f"source-project-{index}"],
        "labelSelectors": {"private-source.io/app": f"source-service-{index}"},
    }
    if kind == "PodChaos":
        return {"action": "pod-kill" if index < 3 else "pod-failure", "mode": "one", "selector": selector}
    if kind == "NetworkChaos":
        return {
            "action": "delay" if index < 3 else "loss",
            "mode": "all",
            "selector": selector,
            "delay": {"latency": f"{100 + index * 100}ms"},
            "duration": "30s",
        }
    if kind == "StressChaos":
        return {
            "mode": "one",
            "selector": selector,
            "stressors": {"cpu": {"workers": 1, "load": 40 + index * 10}},
            "duration": "45s",
        }
    if kind == "HTTPChaos":
        return {
            "mode": "all",
            "selector": selector,
            "target": "Request",
            "port": 8080,
            "path": f"/private-source-{index}",
            "abort": index == 3,
        }
    return {
        "schedule": "@every 1m",
        "type": "PodChaos",
        "historyLimit": 1,
        "concurrencyPolicy": "Forbid",
        "podChaos": {"action": "pod-kill", "mode": "one", "selector": selector},
        "statusCheck": {"http": {"url": f"https://private-source-{index}.example/health"}},
    }


def _write_corpus(root: Path) -> None:
    for kind in CATEGORY_KINDS.values():
        kind_dir = root / kind
        kind_dir.mkdir(parents=True, exist_ok=True)
        for index in range(4):
            document = {
                "apiVersion": "chaos-mesh.org/v1alpha1",
                "kind": kind,
                "metadata": {
                    "name": f"private-source-{kind.lower()}-{index}",
                    "namespace": f"private-namespace-{index}",
                },
                "spec": _spec(kind, index),
            }
            (kind_dir / f"sample-{index}.yaml").write_text(
                yaml.safe_dump(document, sort_keys=False),
                encoding="utf-8",
            )


def test_builds_three_labeled_examples_per_category_with_dual_hashes(tmp_path):
    raw_yaml = tmp_path / "raw_yaml"
    _write_corpus(raw_yaml)

    manifest = build_yaml15_manifest(raw_yaml, tmp_path / "output")

    assert manifest["schema_version"] == "sock-shop-ablation-yaml15-manifest-v1"
    assert manifest["total_examples"] == 15
    assert manifest["selection_policy"]["runtime_outcomes_used"] is False
    assert set(manifest["categories"]) == set(CATEGORY_KINDS)
    assert all(len(examples) == 3 for examples in manifest["categories"].values())

    for category, examples in manifest["categories"].items():
        for example in examples:
            assert example["category"] == category
            source = raw_yaml / example["source_path"]
            redacted = tmp_path / "output" / example["redacted_path"]
            assert hashlib.sha256(source.read_bytes()).hexdigest() == example["source_sha256"]
            assert hashlib.sha256(redacted.read_bytes()).hexdigest() == example["redacted_sha256"]
            text = redacted.read_text(encoding="utf-8")
            assert "private-source" not in text
            assert "private-namespace" not in text


def test_selection_is_deterministic_and_prompt_contains_only_labeled_redacted_yaml(tmp_path):
    raw_yaml = tmp_path / "raw_yaml"
    _write_corpus(raw_yaml)

    first = build_yaml15_manifest(raw_yaml, tmp_path / "first")
    second = build_yaml15_manifest(raw_yaml, tmp_path / "second")

    assert first["selection_fingerprint_sha256"] == second["selection_fingerprint_sha256"]
    first_prompt = json.loads((tmp_path / "first" / "yaml15-prompt.json").read_text(encoding="utf-8"))
    second_prompt = json.loads((tmp_path / "second" / "yaml15-prompt.json").read_text(encoding="utf-8"))
    assert first_prompt == second_prompt
    assert len(first_prompt["labeled_yaml_examples"]) == 15
    assert all(set(item) == {"category", "yaml"} for item in first_prompt["labeled_yaml_examples"])
    assert "source_path" not in json.dumps(first_prompt)
    assert "sha256" not in json.dumps(first_prompt)


def test_refuses_to_overwrite_non_empty_output_directory(tmp_path):
    raw_yaml = tmp_path / "raw_yaml"
    _write_corpus(raw_yaml)
    output = tmp_path / "output"
    output.mkdir()
    (output / "keep.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError, match="non-empty output directory"):
        build_yaml15_manifest(raw_yaml, output)
