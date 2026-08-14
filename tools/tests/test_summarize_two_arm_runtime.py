import json
from pathlib import Path

from tools.summarize_two_arm_runtime import summarize


def write_report(path: Path, *, arm: str, replicate: int, classification: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "project_id": "demo",
                "seed": 1001,
                "arm": arm,
                "mutation_id": "H1",
                "replicate": replicate,
                "status": "completed",
                "observation": {"classification": classification},
            }
        ),
        encoding="utf-8",
    )


def test_summary_groups_verified_reports_by_discovery_fault_and_marks_consistency(tmp_path: Path) -> None:
    discovery = tmp_path / "discovery" / "seed-1001" / "chaosatlas-full"
    discovery.mkdir(parents=True)
    (discovery / "handoff.json").write_text(
        json.dumps(
            {
                "seed": 1001,
                "method_id": "ChaosAtlas-full",
                "selected_hypotheses": [
                    {"hypothesis_id": "H1", "target": "workload/api", "target_kind": "service", "fault_family": "pod_kill", "parameters": {"mode": "one"}}
                ],
            }
        ),
        encoding="utf-8",
    )
    runtime = tmp_path / "runtime"
    write_report(runtime / "a.json", arm="ChaosAtlas-full", replicate=1, classification="weakness_observed")
    write_report(runtime / "b.json", arm="ChaosAtlas-full", replicate=2, classification="no_business_impact_observed")

    result = summarize(discovery.parent.parent, [runtime])

    assert result["reports"] == 2
    row = result["hypotheses"][0]
    assert row["fault_family"] == "pod_kill"
    assert row["weakness_repetitions"] == 1
    assert row["no_business_impact_repetitions"] == 1
    assert row["consistency"] == "mixed"
    assert result["human_review"] == "pending"
    assert result["knowledge_base_updated"] is False
