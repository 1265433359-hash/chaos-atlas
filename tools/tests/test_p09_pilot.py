from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from tools.p09_pilot import PilotCompileError, compile_api_pod_kill
import tools.run_p09_podchaos as runner


def candidate() -> dict:
    return {
        "candidate_id": "P09-api-pod_kill-01",
        "project_id": "P09",
        "target": "api",
        "fault_family": "pod_kill",
        "fault_parameters": {"duration_s": 0, "mode": "one"},
        "workload_id": "P09-primary-workload",
        "support_status": "unknown",
    }


def topology() -> dict:
    return {
        "graph_hash": "a" * 64,
        "nodes": [
            {
                "id": "compose/service/api",
                "kind": "ComposeService",
                "name": "api",
                "role": "workload",
                "labels": {},
            }
        ],
        "edges": [],
    }


def profile() -> str:
    return """apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: chaosatlas-p09
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: api
  template:
    metadata:
      labels:
        app.kubernetes.io/name: api
        app.kubernetes.io/part-of: chaosatlas-p09
"""


def test_compile_frozen_api_pod_kill_with_explicit_runtime_mapping(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(profile(), encoding="utf-8")

    result = compile_api_pod_kill(candidate(), topology(), profile_path)
    mutation = yaml.safe_load(result["yaml"])

    assert mutation["kind"] == "PodChaos"
    assert mutation["metadata"]["namespace"] == "chaosatlas-p09"
    assert mutation["spec"]["mode"] == "one"
    assert mutation["spec"]["selector"] == {
        "namespaces": ["chaosatlas-p09"],
        "labelSelectors": {
            "app.kubernetes.io/name": "api",
            "app.kubernetes.io/part-of": "chaosatlas-p09",
        },
    }
    assert result["provenance"]["candidate_id"] == "P09-api-pod_kill-01"
    assert result["provenance"]["support_status_before_pilot"] == "unknown"


def test_compile_rejects_any_other_candidate(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(profile(), encoding="utf-8")
    value = candidate()
    value["candidate_id"] = "P09-web-pod_kill-05"

    with pytest.raises(PilotCompileError, match="only the frozen P09 API PodKill"):
        compile_api_pod_kill(value, topology(), profile_path)


def test_runner_rejects_non_p09_or_wrong_selector(tmp_path: Path) -> None:
    mutation = yaml.safe_load(compile_api_pod_kill(candidate(), topology(), _write(tmp_path, profile()))["yaml"])
    mutation["metadata"]["namespace"] = "default"
    with pytest.raises(ValueError, match="chaosatlas-p09"):
        runner.validate_mutation(mutation)

    mutation["metadata"]["namespace"] = "chaosatlas-p09"
    mutation["spec"]["selector"]["labelSelectors"] = {"app.kubernetes.io/name": "web"}
    with pytest.raises(ValueError, match="exact API selector"):
        runner.validate_mutation(mutation)

    mutation = yaml.safe_load(
        compile_api_pod_kill(candidate(), topology(), _write(tmp_path, profile()))["yaml"]
    )
    mutation["spec"]["selector"]["pods"] = {"api-1": ["api"]}
    with pytest.raises(ValueError, match="exact selector shape"):
        runner.validate_mutation(mutation)


def test_runner_residual_check_is_global() -> None:
    with patch.object(runner, "kubectl_json", return_value=({"items": []}, None)) as call:
        assert runner.residual_chaos() == []
    call.assert_called_once_with(
        ["get", "podchaos,networkchaos,stresschaos", "-A"]
    )


def test_cleanup_requires_explicit_not_found() -> None:
    with patch.object(
        runner,
        "kubectl",
        side_effect=[(0, "deleted", ""), (1, "", "Error from server (NotFound): not found")],
    ):
        result = runner.cleanup("pilot")
    assert result["absent_confirmed"] is True


def test_runner_refuses_to_overwrite_existing_report(tmp_path: Path) -> None:
    mutation = tmp_path / "mutation.yaml"
    report = tmp_path / "rep-1.json"
    mutation.write_text("unused", encoding="utf-8")
    report.write_text("preserve", encoding="utf-8")

    with patch(
        "sys.argv",
        ["run_p09_podchaos.py", str(mutation), "--report", str(report)],
    ), pytest.raises(SystemExit, match="refusing to overwrite existing report"):
        runner.main()
    assert report.read_text(encoding="utf-8") == "preserve"


def test_runner_exposes_p02_lifecycle_options(capsys) -> None:
    with patch(
        "sys.argv",
        [
            "run_p09_podchaos.py",
            "--help",
        ],
    ), pytest.raises(SystemExit) as exc:
        runner.main()

    assert exc.value.code == 0
    help_text = capsys.readouterr().out
    assert "--washout-seconds" in help_text
    assert "--washout-stable-successes" in help_text
    assert "--capture-diagnostics" in help_text


def test_runner_blocks_apply_when_execution_gate_is_blocked(tmp_path: Path) -> None:
    mutation_path = tmp_path / "mutation.yaml"
    report_path = tmp_path / "rep-1.json"
    mutation_path.write_text(
        compile_api_pod_kill(candidate(), topology(), _write(tmp_path, profile()))["yaml"],
        encoding="utf-8",
    )

    with patch(
        "sys.argv",
        ["run_p09_podchaos.py", str(mutation_path), "--report", str(report_path)],
    ), patch.object(
        runner,
        "execution_gate_check",
        return_value={
            "decision": "blocked",
            "errors": ["P09 profile gate does not allow runtime apply"],
            "mutation_applied": False,
        },
    ), patch.object(runner, "residual_chaos", return_value=[]), patch.object(
        runner, "kubectl"
    ) as kubectl_call:
        assert runner.main() == 2

    assert all(call.args[0][0] != "apply" for call in kubectl_call.call_args_list)
    result = json.loads(report_path.read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert result["execution_gate"]["decision"] == "blocked"
    assert result["injection"]["applied"] is False


@pytest.mark.parametrize("option", ["--baseline-successes", "--washout-successes"])
def test_runner_rejects_nonpositive_oracle_success_count(tmp_path: Path, option: str) -> None:
    report = tmp_path / "rep-1.json"
    with patch(
        "sys.argv",
        ["run_p09_podchaos.py", "mutation.yaml", "--report", str(report), option, "0"],
    ), pytest.raises(SystemExit) as exc:
        runner.main()
    assert exc.value.code == 2
    assert not report.exists()


def test_runner_cleans_up_after_ambiguous_apply_failure(tmp_path: Path) -> None:
    mutation_path = tmp_path / "mutation.yaml"
    report_path = tmp_path / "rep-1.json"
    mutation_path.write_text(
        compile_api_pod_kill(candidate(), topology(), _write(tmp_path, profile()))["yaml"],
        encoding="utf-8",
    )

    with patch(
        "sys.argv",
        ["run_p09_podchaos.py", str(mutation_path), "--report", str(report_path)],
    ), patch.object(
        runner,
        "execution_gate_check",
        return_value={"decision": "ready_for_injection", "errors": []},
    ), patch.object(
        runner,
        "kubectl",
        side_effect=[
            (0, "minikube\n", ""),
            (1, "", "apply response lost"),
        ],
    ) as kubectl_call, patch.object(runner, "residual_chaos", side_effect=[[], []]), patch.object(
        runner, "wait_namespace_stable", return_value={"healthy": True}
    ), patch.object(runner, "collect_oracle", return_value=([{"status_code": 200}], True)), patch.object(
        runner,
        "pod_snapshot",
        return_value=[{"name": "api-1", "uid": "old", "ready": True, "terminating": False}],
    ), patch.object(
        runner,
        "cleanup",
        return_value={"absent_confirmed": True},
    ) as cleanup_call, patch.object(
        runner,
        "wait_replacement",
        return_value=(True, {"new_ready_uids": ["new"]}),
    ):
        assert runner.main() == 2

    cleanup_call.assert_called_once()
    apply_call = kubectl_call.call_args_list[1]
    assert apply_call.args == (["apply", "-f", "-"],)
    assert apply_call.kwargs["input_text"] == mutation_path.read_bytes().decode("utf-8")
    result = json.loads(report_path.read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert result["cleanup"]["absent_confirmed"] is True
    assert result["schema_version"] == "unified-lifecycle-v1"
    assert result["project_id"] == "P09"
    assert result["mutation"]["sha256"]
    assert "baseline" in result
    assert "injection" in result
    assert "observation" in result
    assert "recovery" in result
    assert "washout" in result
    assert "diagnostics" in result
    assert result["human_review"] == "pending"
    assert result["comparison_eligibility"]["eligible"] is False


def test_cli_accepts_utf8_bom_candidate_pool(tmp_path: Path) -> None:
    from tools import p09_pilot

    pool = tmp_path / "pool.json"
    topo = tmp_path / "topology.json"
    profile_path = _write(tmp_path, profile())
    output = tmp_path / "output"
    pool.write_text(json.dumps({"candidates": [candidate()]}), encoding="utf-8-sig")
    topo.write_text(json.dumps(topology()), encoding="utf-8-sig")

    with patch(
        "sys.argv",
        [
            "p09_pilot.py",
            "--candidate-pool",
            str(pool),
            "--topology",
            str(topo),
            "--profile",
            str(profile_path),
            "--output-dir",
            str(output),
        ],
    ):
        assert p09_pilot.main() == 0
    mutation_path = output / "p09-api-pod-kill.yaml"
    provenance = json.loads(
        (output / "p09-api-pod-kill.provenance.json").read_text(encoding="utf-8")
    )
    assert mutation_path.exists()
    assert provenance["mutation_sha256"] == __import__("hashlib").sha256(
        mutation_path.read_bytes()
    ).hexdigest()


def test_cli_refuses_to_overwrite_nonempty_output_directory(tmp_path: Path) -> None:
    from tools import p09_pilot

    pool = tmp_path / "pool.json"
    topo = tmp_path / "topology.json"
    profile_path = _write(tmp_path, profile())
    output = tmp_path / "output"
    output.mkdir()
    sentinel = output / "existing.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    pool.write_text(json.dumps({"candidates": [candidate()]}), encoding="utf-8")
    topo.write_text(json.dumps(topology()), encoding="utf-8")

    with patch(
        "sys.argv",
        [
            "p09_pilot.py",
            "--candidate-pool",
            str(pool),
            "--topology",
            str(topo),
            "--profile",
            str(profile_path),
            "--output-dir",
            str(output),
        ],
    ), pytest.raises(SystemExit, match="refusing to overwrite nonempty output directory"):
        p09_pilot.main()
    assert sentinel.read_text(encoding="utf-8") == "preserve"


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "profile.yaml"
    path.write_text(content, encoding="utf-8")
    return path
