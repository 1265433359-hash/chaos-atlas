from __future__ import annotations

import json
from pathlib import Path

from tools.sock_shop_disambiguation_ingest import build_disambiguation_round


def _write_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def test_build_disambiguation_round_appends_evidence_without_promoting_knowledge(tmp_path: Path):
    parent = tmp_path / "parent"
    (parent / "cases").mkdir(parents=True)
    (parent / "hypotheses").mkdir()
    _write_json(parent / "manifest.json", {"project_id": "sock-shop", "project_commit": "fixture", "round_id": "runtime-live-r1"})
    case = {
        "schema_version": "chaosatlas-weakness-case-v1",
        "weakness_id": "WS-sock-shop-front-end-podchaos-pod-kill",
        "project_id": "sock-shop",
        "project_commit": "fixture",
        "round_id": "runtime-live-r1",
        "case_family": "single_replica_podkill",
        "test_node": {
            "family": "PodChaos",
            "operation": "pod-kill",
            "source_ref": "case-source.json",
            "target_role": "front-end deployment",
        },
        "symptom": {"oracle": "http_200"},
        "weakness_status": "confirmed",
        "rca_status": "bounded",
        "knowledge_status": "provisional",
        "evidence_refs": [],
        "hypothesis_ids": [],
        "hypotheses": [],
        "next_actions": [{"status": "pending"}],
    }
    _write_json(parent / "cases" / f"{case['weakness_id']}.json", case)
    _write_json(parent / "case-source.json", {"fixture": True})
    _write_json(
        parent / "action_plan.json",
        {
            "available_preconditions": ["frozen_manifest", "frozen_verdicts", "captured_ready_samples", "captured_window"],
            "case_plans": [{"weakness_id": case["weakness_id"], "plan": {"status": "pending"}}],
        },
    )
    source = tmp_path / "r2"
    _write_json(source / "result.json", {"summary": {"classification": "observation_inconclusive", "deterministic": False}, "sample_count": 3})
    _write_json(source / "manifest.json", {"round_id": "pilot-r3-disambiguation-r2", "schema_version": "fixture"})
    _write_json(source / "injection_status.json", {"status": {"conditions": [{"type": "AllInjected", "status": "True"}]}})
    (source / "timeline.jsonl").write_text('{"business":{"status_code":200}}\n', encoding="utf-8")

    output = tmp_path / "output"
    result = build_disambiguation_round(parent_root=parent, source_root=source, output_root=output)
    assert result["status"] == "observation_inconclusive"
    assert result["knowledge_status"] == "provisional"
    emitted = json.loads(next((output / "cases").glob("*.json")).read_text(encoding="utf-8"))
    assert emitted["rca_status"] == "bounded"
    assert emitted["knowledge_status"] == "provisional"
    assert len(emitted["evidence_refs"]) == 3
    assert (output / "knowledge_drafts" / "regression_intents.json").is_file()
