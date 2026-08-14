from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from tools import run_p09_chaos as runner


def test_direct_script_invocation_bootstraps_repository_imports() -> None:
    script = Path(__file__).resolve().parents[1] / "run_p09_chaos.py"
    completed = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert "usage:" in completed.stdout.lower()


def mutation(kind: str = "NetworkChaos") -> dict:
    document = {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": kind,
        "metadata": {"name": "p09-test", "namespace": "chaosatlas-p09"},
        "spec": {
            "mode": "one",
            "selector": {
                "namespaces": ["chaosatlas-p09"],
                "labelSelectors": {
                    "app.kubernetes.io/name": "redis",
                    "app.kubernetes.io/part-of": "chaosatlas-p09",
                    "chaosatlas.io/profile": "minimal",
                },
            },
            "action": "delay",
            "delay": {"latency": "200ms", "correlation": "100", "jitter": "0ms"},
            "duration": "30s",
        },
    }
    return document


def test_validate_accepts_supported_namespace_local_mutations() -> None:
    for kind in ("PodChaos", "NetworkChaos", "StressChaos"):
        document = mutation(kind)
        if kind == "StressChaos":
            document["spec"].pop("action")
            document["spec"].pop("delay")
            document["spec"]["stressors"] = {"cpu": {"workers": 1, "load": 60}}
        assert runner.validate_mutation(document) == ("p09-test", document["spec"]["selector"]["labelSelectors"])


def test_validate_rejects_cross_namespace_or_broad_mode() -> None:
    document = mutation()
    document["metadata"]["namespace"] = "default"
    with pytest.raises(ValueError, match="chaosatlas-p09"):
        runner.validate_mutation(document)

    document = mutation()
    document["spec"]["mode"] = "all"
    with pytest.raises(ValueError, match="mode=one"):
        runner.validate_mutation(document)


def test_lifecycle_snapshot_counts_injection_and_recovery() -> None:
    snapshot = runner.lifecycle_snapshot(
        {
            "status": {
                "conditions": [
                    {"type": "AllInjected", "status": "True"},
                    {"type": "AllRecovered", "status": "True"},
                ],
                "experiment": {
                    "containerRecords": [
                        {"injectedCount": 1, "recoveredCount": 1}
                    ]
                },
            }
        }
    )
    assert snapshot["injected_count"] == 1
    assert snapshot["recovered_count"] == 1
    assert snapshot["all_recovered"] is True


def test_wait_lifecycle_recovery_requires_recovery_evidence() -> None:
    snapshots = iter([
        ({"status": {"experiment": {"containerRecords": [{"injectedCount": 1, "recoveredCount": 0}]}}}, None),
        ({"status": {"conditions": [{"type": "AllRecovered", "status": "True"}], "experiment": {"containerRecords": [{"injectedCount": 1, "recoveredCount": 1}]}}}, None),
    ])
    with patch.object(runner, "kubectl_json", side_effect=lambda args: next(snapshots)):
        result = runner.wait_lifecycle("NetworkChaos", "p09-test", "recovered", timeout=1)
    assert result["recovered_count"] == 1
    assert result["all_recovered"] is True


def test_podchaos_recovery_uses_replacement_identity() -> None:
    with patch.object(
        runner,
        "wait_replacement",
        return_value=(True, {"new_ready_uids": ["new-uid"], "stable_checks": 3}),
    ) as replacement:
        recovered, detail = runner.recover_podchaos(
            {"old-uid"},
            {"app.kubernetes.io/name": "redis"},
            10,
        )
    assert recovered is True
    assert detail["new_ready_uids"] == ["new-uid"]
    replacement.assert_called_once()


def test_cleanup_requires_explicit_not_found() -> None:
    with patch.object(
        runner,
        "kubectl",
        side_effect=[(0, "deleted", ""), (1, "", "Error from server (NotFound): not found")],
    ):
        result = runner.cleanup("NetworkChaos", "p09-test")
    assert result["absent_confirmed"] is True
