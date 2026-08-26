from __future__ import annotations

import json
import shutil

from tools.chaosatlas_adapters import KnowledgeProvider
from tools.chaosatlas_hypothesis import rank_candidates
from tools.defense_knowledge import promote_repeated_defense


def _write_run(root, run_id: str, *, claim_type: str = "redundancy", classification: str = "availability_defended") -> None:
    root.mkdir(parents=True)
    (root / "classify.json").write_text(
        json.dumps(
            {
                "payload": {
                    "result": classification,
                    "claim_scope": "deployment:front-end",
                    "defense_evidence": {
                        "claim_type": claim_type,
                        "mechanism_evidence": True,
                        "independent_oracle": True,
                        "observation_window": True,
                        "observation_window_s": 60,
                    },
                    "attestation": {
                        "baseline": True,
                        "injection": True,
                        "observation": True,
                        "recovery": True,
                        "cleanup": True,
                        "independent_oracle": True,
                        "valid": True,
                    },
                    "evidence_refs": [f"runtime/{run_id}/mechanism.json"],
                }
            }
        ),
        encoding="utf-8",
    )
    (root / "observe.json").write_text(
        json.dumps({"payload": {"observation": {"status": "pass", "samples": [{"status_code": 200}]}}}),
        encoding="utf-8",
    )
    (root / "cleanup_report.json").write_text(json.dumps({"status": "verified", "errors": []}), encoding="utf-8")
    (root / "run_manifest.json").write_text(
        json.dumps({"run_id": run_id, "project_id": "sock-shop", "project_commit": "a" * 40, "target": "front-end"}),
        encoding="utf-8",
    )


def test_two_independent_defended_runs_promote_a_local_reusable_card_and_guard(tmp_path) -> None:
    run_a = tmp_path / "r10"
    run_b = tmp_path / "r11"
    _write_run(run_a, "r10")
    _write_run(run_b, "r11")

    result = promote_repeated_defense(run_roots=[run_a, run_b], output_root=tmp_path / "knowledge")

    assert result["knowledge_status"] == "local_reusable"
    assert result["classification"] == "protected"
    assert result["defense_claim_type"] == "redundancy"
    assert [item["kind"] for item in result["regression"]["intents"]] == ["reproduce", "guard"]
    card = json.loads((tmp_path / "knowledge" / "defense_card.json").read_text(encoding="utf-8"))
    assert card["knowledge_status"] == "local_reusable"
    assert card["weakness_status"] == "protected"
    assert (tmp_path / "knowledge" / f"{card['id']}.json").is_file()
    retrieved = KnowledgeProvider().retrieve(
        project_id="sock-shop",
        candidate_space={"candidate_count": 1, "candidates": [{"candidate_id": "candidate:pod_kill", "fault_family": "pod_kill"}]},
        root=tmp_path / "knowledge",
    )
    assert retrieved["cards"][0]["status"] == "local_reusable"
    assert rank_candidates({"candidates": [{"candidate_id": "candidate:pod_kill", "fault_family": "pod_kill"}]}, retrieved["cards"])["candidates"][0]["retrieval_score"] > 1


def test_defense_promotion_fails_closed_on_one_run_or_mismatched_claim(tmp_path) -> None:
    run_a = tmp_path / "r10"
    run_b = tmp_path / "r11"
    _write_run(run_a, "r10")
    _write_run(run_b, "r11", claim_type="fallback")

    try:
        promote_repeated_defense(run_roots=[run_a, run_b], output_root=tmp_path / "knowledge")
    except ValueError as exc:
        assert "claim_type" in str(exc)
    else:
        raise AssertionError("mismatched defense claims must be rejected")


def test_defense_promotion_rejects_duplicate_run_artifacts(tmp_path) -> None:
    run_a = tmp_path / "r10"
    run_b = tmp_path / "r11"
    _write_run(run_a, "same-run")
    shutil.copytree(run_a, run_b)

    try:
        promote_repeated_defense(run_roots=[run_a, run_b], output_root=tmp_path / "knowledge")
    except ValueError as exc:
        assert "independent" in str(exc)
    else:
        raise AssertionError("duplicate run artifacts must be rejected")
