import hashlib
import json
from pathlib import Path

import pytest

from tools.sock_shop_three_method import (
    ALLOWED_NAMESPACE,
    METHOD_IDS,
    build_manifest,
    comparison_status,
    event_capture_payload,
    validate_method_id,
)


def test_method_registry_contains_exact_three_full_methods():
    assert METHOD_IDS == (
        "ChaosAtlas-full",
        "ChaosAtlas-ablation",
        "ChaosEater-full",
    )


def test_method_id_and_namespace_fail_closed():
    assert validate_method_id("ChaosAtlas-full") is True
    assert validate_method_id("ChaosEater-adapter") is False
    with pytest.raises(ValueError):
        build_manifest("ChaosAtlas-full", "other-namespace", Path("mutation.yaml"))


def test_comparison_status_requires_all_lifecycle_checks(tmp_path):
    mutation = tmp_path / "mutation.yaml"
    mutation.write_bytes(b"apiVersion: chaos-mesh.org/v1alpha1\n")
    report = {
        "method_id": "ChaosAtlas-full",
        "namespace": ALLOWED_NAMESPACE,
        "mutation": {
            "path": str(mutation),
            "sha256": hashlib.sha256(mutation.read_bytes()).hexdigest(),
        },
        "baseline": {"pass": True},
        "injection": {"applied": True, "injected": True},
        "recovery": {"recovered": True},
        "cleanup": {"absent_confirmed": True, "residual_resources": []},
        "washout": {"stable": True},
        "human_review": "pending",
    }
    assert comparison_status(report)["eligible"] is True
    report["cleanup"]["residual_resources"] = [{"kind": "PodChaos"}]
    assert comparison_status(report)["eligible"] is False


def test_manifest_records_native_chaoseater_boundary(tmp_path):
    mutation = tmp_path / "mutation.yaml"
    mutation.write_text("kind: PodChaos\n", encoding="utf-8")
    manifest = build_manifest("ChaosEater-full", ALLOWED_NAMESPACE, mutation)
    assert manifest["method_id"] == "ChaosEater-full"
    assert manifest["native_input_required"] is True
    assert manifest["adapter_substitution_allowed"] is False


def test_event_capture_payload_is_json_serializable():
    payload = event_capture_payload('{"items":[{"reason":"Killing"}]}')
    assert payload["status"] == "captured"
    assert payload["items"][0]["reason"] == "Killing"
