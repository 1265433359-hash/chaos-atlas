from __future__ import annotations

from unittest.mock import patch

import tools.run_p02_formal_batch as batch
import tools.run_p02_podchaos as runner


def test_formal_schedule_has_balanced_independent_method_outputs() -> None:
    rows = batch.schedule(3)

    assert len(rows) == 15
    assert len({(row["arm"], row["mutation_id"], row["replicate"]) for row in rows}) == 15
    assert sum(row["arm"] == "ChaosAtlas-KB-open" for row in rows) == 6
    assert sum(row["arm"] == "ChaosAtlas-noKB-open" for row in rows) == 6
    assert sum(row["arm"] == "ChaosEater-adapter-open" for row in rows) == 3
    assert [rows[index * 5]["arm"] for index in range(3)] == [
        "ChaosAtlas-KB-open",
        "ChaosAtlas-noKB-open",
        "ChaosEater-adapter-open",
    ]


def test_report_paths_keep_arm_mutation_and_replicate_separate(tmp_path) -> None:
    row = {
        "arm": "ChaosAtlas-noKB-open",
        "mutation_id": "mutation-2",
        "replicate": 3,
    }

    assert batch.report_path(tmp_path, row) == (
        tmp_path / "ChaosAtlas-noKB-open" / "mutation-2" / "rep-3.json"
    )


def test_residual_chaos_returns_global_resource_identity() -> None:
    payload = {
        "items": [
            {
                "kind": "NetworkChaos",
                "metadata": {"namespace": "other-lab", "name": "leftover"},
            }
        ]
    }
    with patch.object(runner, "kubectl_json", return_value=(payload, None)) as call:
        result = runner.residual_chaos()

    assert result == [{"kind": "NetworkChaos", "namespace": "other-lab", "name": "leftover"}]
    call.assert_called_once_with(["get", "podchaos,networkchaos,stresschaos", "-A"])


def test_namespace_health_requires_every_deployment_and_pod_ready() -> None:
    deployments = {
        "items": [
            {
                "metadata": {"name": "api-gateway"},
                "spec": {"replicas": 1},
                "status": {"readyReplicas": 1, "availableReplicas": 1, "updatedReplicas": 1},
            }
        ]
    }
    pods = {
        "items": [
            {
                "metadata": {"name": "api-gateway-abc", "uid": "uid-1"},
                "status": {"conditions": [{"type": "Ready", "status": "False"}]},
            }
        ]
    }
    with patch.object(runner, "kubectl_json", side_effect=[(deployments, None), (pods, None)]):
        health = runner.namespace_health()

    assert health["healthy"] is False
    assert health["pods"][0]["ready"] is False
