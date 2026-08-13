from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.run_p08_dual_arm import (
    ARM_NAMES,
    IMAGE,
    NAMESPACE,
    build_appsmith_manifest,
    build_podchaos_manifest,
    prepare_output_dir,
    validate_appsmith_manifest,
    validate_podchaos_manifest,
)


def test_appsmith_manifest_is_digest_pinned_and_namespace_local() -> None:
    document = build_appsmith_manifest()

    assert document["metadata"]["namespace"] == NAMESPACE
    assert document["spec"]["template"]["spec"]["containers"][0]["image"] == IMAGE
    assert "@sha256:" in IMAGE
    assert validate_appsmith_manifest(document) == NAMESPACE


def test_podchaos_manifest_targets_only_p08_appsmith() -> None:
    document = build_podchaos_manifest("ChaosAtlas-KB")

    assert document["metadata"]["namespace"] == NAMESPACE
    assert document["spec"]["selector"]["namespaces"] == [NAMESPACE]
    assert document["spec"]["selector"]["labelSelectors"] == {
        "app.kubernetes.io/name": "appsmith",
        "app.kubernetes.io/part-of": NAMESPACE,
    }
    assert validate_podchaos_manifest(document) == "p08-appsmith-pod-kill-chaosatlas-kb"


def test_validation_rejects_other_namespace() -> None:
    document = build_podchaos_manifest("ChaosAtlas-noKB")
    document["metadata"]["namespace"] = "default"

    with pytest.raises(ValueError, match="chaosatlas-p08"):
        validate_podchaos_manifest(document)


def test_output_directory_refuses_nonempty_directory(tmp_path: Path) -> None:
    output = tmp_path / "p08-dual"
    output.mkdir()
    (output / "existing.json").write_text(json.dumps({}), encoding="utf-8")

    with pytest.raises(FileExistsError, match="nonempty"):
        prepare_output_dir(output)


def test_registered_arms_are_exactly_two() -> None:
    assert ARM_NAMES == ("ChaosAtlas-KB", "ChaosAtlas-noKB")
