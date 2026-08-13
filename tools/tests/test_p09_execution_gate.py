from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import yaml

from tools.p09_execution_gate import check


def mutation_document() -> dict:
    return {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "PodChaos",
        "metadata": {"name": "p09-test", "namespace": "chaosatlas-p09"},
        "spec": {
            "action": "pod-kill",
            "mode": "one",
            "selector": {
                "namespaces": ["chaosatlas-p09"],
                "labelSelectors": {
                    "app.kubernetes.io/name": "api",
                    "app.kubernetes.io/part-of": "chaosatlas-p09",
                },
            },
        },
    }


def write_case(tmp_path: Path, *, allowed: bool) -> tuple[Path, Path]:
    mutation = tmp_path / "mutation.yaml"
    mutation.write_text(
        yaml.safe_dump(mutation_document(), sort_keys=False), encoding="utf-8"
    )
    gate = tmp_path / "profile-preflight.json"
    gate.write_text(
        json.dumps({"runtime_apply_allowed": allowed}), encoding="utf-8"
    )
    return mutation, gate


def fake_kubectl_json(args: list[str]):
    if args[:2] == ["get", "pods"]:
        return {
            "items": [
                {
                    "metadata": {"name": "api-1", "uid": "uid-1"},
                    "status": {
                        "conditions": [{"type": "Ready", "status": "True"}]
                    },
                }
            ]
        }, None
    return {}, None


def test_blocked_profile_gate_never_becomes_ready(tmp_path: Path) -> None:
    mutation, gate = write_case(tmp_path, allowed=False)
    with patch(
        "tools.p09_execution_gate.kubectl",
        side_effect=[
            (0, "", ""),
            (1, "", "Error from server (NotFound): pods not found"),
        ],
    ), patch(
        "tools.p09_execution_gate.kubectl_json",
        side_effect=fake_kubectl_json,
    ):
        result = check(mutation, profile_gate=gate)

    assert result["decision"] == "blocked"
    assert "P09 profile gate does not allow runtime apply" in result["errors"]
    assert result["mutation_applied"] is False


def test_allowed_profile_gate_accepts_ready_namespace_local_pod(
    tmp_path: Path,
) -> None:
    mutation, gate = write_case(tmp_path, allowed=True)
    with patch(
        "tools.p09_execution_gate.kubectl",
        side_effect=[
            (0, "", ""),
            (1, "", "Error from server (NotFound): not found"),
        ],
    ), patch(
        "tools.p09_execution_gate.kubectl_json",
        side_effect=fake_kubectl_json,
    ):
        result = check(mutation, profile_gate=gate)

    assert result["decision"] == "ready_for_injection"
