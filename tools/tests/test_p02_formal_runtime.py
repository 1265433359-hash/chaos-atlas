from __future__ import annotations

from unittest.mock import Mock, patch

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


def test_post_recovery_retries_tunnel_startup_until_http_oracle_succeeds() -> None:
    live = Mock()
    live.poll.return_value = None
    sample = {"status_code": 200}
    with (
        patch.object(runner, "stop_forward"),
        patch.object(runner, "reconnect_forward", side_effect=[RuntimeError("port not listening"), live]),
        patch.object(runner, "request", return_value=sample),
        patch.object(runner.time, "sleep"),
    ):
        proc, samples, successes, warnings = runner.collect_post_recovery(None, 1, timeout=5)

    assert proc is live
    assert samples == [sample]
    assert successes == 1
    assert warnings == ["post_recovery_port_forward_retry: port not listening"]


def test_post_recovery_requires_full_success_count() -> None:
    live = Mock()
    live.poll.return_value = None
    with (
        patch.object(runner, "stop_forward"),
        patch.object(runner, "reconnect_forward", return_value=live),
        patch.object(runner, "request", side_effect=[{"status_code": 200}, {"status_code": 200}]),
    ):
        _, samples, successes, warnings = runner.collect_post_recovery(None, 2, timeout=5)

    assert len(samples) == 2
    assert successes == 2
    assert warnings == []
