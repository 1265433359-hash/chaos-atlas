from unittest.mock import patch

from tools.run_chaos_experiment import wait_for_container_ready


def _pod(*, ready: bool, restarts: int) -> dict:
    return {
        "metadata": {"name": "frontend-0", "uid": "pod-uid"},
        "status": {
            "conditions": [{"type": "Ready", "status": "True" if ready else "False"}],
            "containerStatuses": [{"name": "server", "restartCount": restarts}],
        },
    }


def test_container_kill_recovery_accepts_same_pod_uid_after_restart() -> None:
    snapshots = iter(
        [
            ({"items": [_pod(ready=True, restarts=0)]}, None),
            ({"items": [_pod(ready=False, restarts=1)]}, None),
            ({"items": [_pod(ready=True, restarts=1)]}, None),
            ({"items": [_pod(ready=True, restarts=1)]}, None),
        ]
    )
    with patch(
        "tools.run_chaos_experiment.kubectl_json",
        side_effect=lambda *args, **kwargs: next(snapshots),
    ):
        recovered, state, errors = wait_for_container_ready(
            "chaosatlas-online-boutique",
            {"labelSelectors": {"app": "frontend"}},
            timeout=1,
            interval=0,
            expected_pod_count=1,
            pre_restart_counts={"frontend-0": 0},
            target_pod_names={"frontend-0"},
            container_names={"server"},
            stable_checks=2,
        )

    assert recovered is True
    assert errors == []
    assert state["recovery_mode"] == "container_restart"
    assert state["ready_pods"] == ["frontend-0"]
    assert state["restarted_pods"] == ["frontend-0"]
