import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.dify_canary_closed_loop import aggregate_canary_trials, record_canary_trial


def _profile():
    return {
        "project_id": "dify-kubernetes",
        "project_commit": "test-commit",
        "namespace_policy": {"allowed_namespaces": ["lab"]},
        "business_oracles": [{
            "kind": "dify_chatflow",
            "service": "dify-k8s",
            "remote_port": 80,
            "entrypoint": "/v1/chat-messages",
            "expected_status": 200,
            "success_contract": "dify_chatflow_response",
        }],
    }


def _result(status="executed", observation_status="pass"):
    return {
        "action_id": "canary-r1",
        "status": status,
        "baseline": {"status": "pass", "samples": [{"status_code": 200}]},
        "observation": {"status": observation_status, "samples": [{"status_code": 200}]},
        "recovery": {"confirmed": True},
        "cleanup": {"confirmed": True},
        "attestation": {
            "valid": True,
            "comparison_eligible": True,
            "baseline": True,
            "injection": True,
            "observation": True,
            "recovery": True,
            "cleanup": True,
            "independent_oracle": True,
        },
        "errors": [],
    }


def test_standalone_canary_writes_shared_rca_artifacts(tmp_path):
    row = record_canary_trial(
        root=tmp_path / "trial-r1",
        profile=_profile(),
        candidate={
            "candidate_id": "service:postgresql:pod_kill",
            "target": "dify-k8s-postgresql",
            "fault_family": "pod_kill",
            "target_kind": "statefulset",
        },
        result=_result(),
        repetition=1,
    )

    assert row["status"] == "live_completed"
    assert (tmp_path / "trial-r1" / "finding_report.json").is_file()
    assert (tmp_path / "trial-r1" / "rca_report.json").is_file()
    assert (tmp_path / "trial-r1" / "knowledge_draft.json").is_file()
    rca = json.loads((tmp_path / "trial-r1" / "rca_report.json").read_text())
    assert rca["rca_status"] in {"bounded", "confirmed"}


def test_canary_aggregation_runs_promotion_gate(tmp_path):
    rows = []
    for index in range(1, 4):
        rows.append(
            record_canary_trial(
                root=tmp_path / f"trial-r{index}",
                profile=_profile(),
                candidate={
                    "candidate_id": "service:postgresql:pod_kill",
                    "target": "dify-k8s-postgresql",
                    "fault_family": "pod_kill",
                    "target_kind": "statefulset",
                },
                result={**_result(observation_status="degraded"), "action_id": f"canary-r{index}"},
                repetition=index,
            )
        )

    report = aggregate_canary_trials(
        rows=rows,
        output_root=tmp_path / "aggregate",
        knowledge_root=tmp_path / "knowledge",
    )

    assert report["trial_count"] == 3
    assert report["candidates"][0]["stable_anomaly"] is True
    assert report["promotion"]["promoted_card_ids"] == []
