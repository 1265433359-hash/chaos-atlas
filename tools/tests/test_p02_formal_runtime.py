from __future__ import annotations

import hashlib
import itertools
import json
import subprocess
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import tools.run_p02_formal_batch as batch
import tools.run_p02_podchaos as runner


def test_kubectl_forces_utf8_and_normalizes_missing_streams() -> None:
    completed = subprocess.CompletedProcess(["kubectl"], 0, stdout=None, stderr=None)
    with patch.object(runner.subprocess, "run", return_value=completed) as call:
        code, out, err = runner.kubectl(["logs", "deployment/discovery-server"])

    assert (code, out, err) == (0, "", "")
    assert call.call_args.kwargs["encoding"] == "utf-8"
    assert call.call_args.kwargs["errors"] == "replace"


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


def test_formal_batch_plan_freezes_diagnostic_and_washout_protocol(tmp_path, capsys) -> None:
    output = tmp_path / "new-r3"
    with patch(
        "sys.argv",
        [
            "run_p02_formal_batch.py",
            "--output",
            str(output),
            "--replicates",
            "1",
            "--washout-seconds",
            "75",
        ],
    ):
        assert batch.main() == 0

    manifest = __import__("json").loads(capsys.readouterr().out)
    assert manifest["protocol"]["washout_seconds"] == 75.0
    assert manifest["protocol"]["capture_diagnostics"] is True


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


def test_washout_records_delayed_failure_then_requires_sustained_recovery() -> None:
    live = Mock()
    live.poll.return_value = None
    clock = itertools.count(step=1.0)
    samples = [
        {"status_code": 200},
        {"status_code": 500},
        {"status_code": 200},
        {"status_code": 200},
    ]
    with (
        patch.object(runner, "reconnect_forward", return_value=live),
        patch.object(runner, "stop_forward"),
        patch.object(runner, "request", side_effect=samples),
        patch.object(runner.time, "monotonic", side_effect=lambda: next(clock)),
        patch.object(runner.time, "sleep"),
    ):
        observed, consecutive, stable, warnings = runner.collect_post_cleanup_washout(
            duration=3,
            stable_successes=2,
            timeout=10,
            interval=0,
        )

    assert observed == samples
    assert consecutive == 2
    assert stable is True
    assert warnings == []


def test_sidecar_records_exact_hash_size_and_status(tmp_path) -> None:
    path = tmp_path / "rep-1.api-gateway.log"

    metadata = runner.write_sidecar(path, "diagnostic text\n", status="captured", return_code=0)

    expected = b"diagnostic text\n"
    assert path.read_bytes() == expected
    assert metadata["status"] == "captured"
    assert metadata["size_bytes"] == len(expected)
    assert metadata["sha256"] == hashlib.sha256(expected).hexdigest()
    assert metadata["error"] is None


def _urlopen_response(value) -> MagicMock:
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(value).encode("utf-8")
    return response


def test_zipkin_diagnostic_records_unavailable(tmp_path) -> None:
    report = tmp_path / "rep-1.json"
    with patch.object(runner, "start_service_forward", side_effect=RuntimeError("no tunnel")):
        metadata = runner.capture_zipkin(report, "2026-08-13T00:00:00+00:00")

    payload = json.loads((tmp_path / "rep-1.zipkin.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "unavailable"
    assert metadata["trace_unavailable"] is True
    assert payload["traces"] == []


def test_zipkin_diagnostic_distinguishes_empty_and_captured(tmp_path) -> None:
    proc = Mock()
    proc.poll.return_value = None
    started = datetime.now(timezone.utc)
    since = started.isoformat()
    recent_span = {"id": "span-1", "timestamp": int(started.timestamp() * 1_000_000), "duration": 1}
    with (
        patch.object(runner, "start_service_forward", return_value=proc),
        patch.object(runner, "wait_forward"),
        patch.object(runner, "stop_forward"),
        patch.object(runner.urllib.request, "urlopen", return_value=_urlopen_response([])),
    ):
        empty = runner.capture_zipkin(tmp_path / "rep-2.json", since)
    with (
        patch.object(runner, "start_service_forward", return_value=proc),
        patch.object(runner, "wait_forward"),
        patch.object(runner, "stop_forward"),
        patch.object(runner.urllib.request, "urlopen", return_value=_urlopen_response([[recent_span]])),
    ):
        captured = runner.capture_zipkin(tmp_path / "rep-3.json", since)

    assert empty["status"] == "empty"
    assert empty["trace_unavailable"] is True
    assert empty["trace_count"] == 0
    assert captured["status"] == "captured"
    assert captured["trace_unavailable"] is False
    assert captured["trace_count"] == 1
