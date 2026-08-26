from __future__ import annotations

import json

from tools.defense_promotion_stage import (
    promote_from_history,
    record_promotion_conflict,
    select_history_children,
)


def _write_required_run(root, *, run_id: str = "r1") -> None:
    root.mkdir(parents=True)
    (root / "run_manifest.json").write_text(json.dumps({"run_id": run_id}), encoding="utf-8")
    (root / "classify.json").write_text(json.dumps({"result": "availability_defended"}), encoding="utf-8")
    (root / "observe.json").write_text(json.dumps({"observation": {"status": "pass"}}), encoding="utf-8")
    (root / "cleanup_report.json").write_text(json.dumps({"status": "verified"}), encoding="utf-8")


def _write_defended_run(root, *, run_id: str, claim_type: str = "redundancy") -> None:
    root.mkdir(parents=True)
    (root / "run_manifest.json").write_text(
        json.dumps({"run_id": run_id, "project_id": "sock-shop", "project_commit": "a" * 40}),
        encoding="utf-8",
    )
    (root / "classify.json").write_text(
        json.dumps(
            {
                "payload": {
                    "result": "availability_defended",
                    "defense_evidence": {"claim_type": claim_type, "mechanism_evidence": True},
                    "attestation": {
                        "baseline": True,
                        "injection": True,
                        "observation": True,
                        "recovery": True,
                        "cleanup": True,
                        "independent_oracle": True,
                    },
                    "evidence_refs": [f"runtime/{run_id}.json"],
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


def test_select_history_children_only_reads_immediate_valid_run_roots(tmp_path) -> None:
    valid = tmp_path / "r1"
    _write_required_run(valid)
    nested = tmp_path / "nested" / "r2"
    _write_required_run(nested)
    malformed = tmp_path / "malformed"
    malformed.mkdir()
    (malformed / "run_manifest.json").write_text("{}", encoding="utf-8")

    result = select_history_children(tmp_path)

    assert [item.name for item in result["selected"]] == ["r1"]
    assert result["rejected"] == [
        {"path": "malformed", "reason": "missing_required_artifacts"},
        {"path": "nested", "reason": "missing_required_artifacts"},
    ]


def test_select_history_children_rejects_missing_or_non_directory_entries(tmp_path) -> None:
    _write_required_run(tmp_path / "valid")
    (tmp_path / "README.txt").write_text("not a run", encoding="utf-8")

    result = select_history_children(tmp_path)

    assert [item.name for item in result["selected"]] == ["valid"]
    assert result["rejected"] == [{"path": "README.txt", "reason": "not_directory"}]


def test_promote_from_history_publishes_local_reusable_card(tmp_path) -> None:
    history = tmp_path / "history"
    _write_defended_run(history / "r1", run_id="r1")
    _write_defended_run(history / "r2", run_id="r2")

    result = promote_from_history(
        history_root=history,
        output_root=tmp_path / "out",
        knowledge_write_root=tmp_path / "knowledge",
    )

    assert result["status"] == "promoted"
    assert result["knowledge_status"] == "local_reusable"
    assert (tmp_path / "out" / "knowledge_promotion.json").is_file()
    assert (tmp_path / "knowledge" / "defense_card.json").is_file()
    assert (tmp_path / "knowledge" / "regression_intents.json").is_file()


def test_counterexample_preserves_old_snapshot_and_emits_no_guard(tmp_path) -> None:
    old = tmp_path / "knowledge" / "old.json"
    old.parent.mkdir()
    old.write_text(json.dumps({"knowledge_status": "local_reusable", "id": "old"}), encoding="utf-8")

    result = record_promotion_conflict(
        old_card=old,
        run_root=tmp_path / "bad-run",
        reason="cleanup_not_verified",
        output_root=tmp_path / "out",
    )

    assert result["status"] == "contested"
    assert result["guard_intents"] == []
    assert result["old_snapshot_sha256"]
    assert json.loads(old.read_text(encoding="utf-8"))["id"] == "old"
    assert (tmp_path / "out" / "knowledge_conflict.json").is_file()


def test_promote_from_history_conflict_preserves_existing_card_snapshot(tmp_path) -> None:
    history = tmp_path / "history"
    _write_defended_run(history / "r1", run_id="r1", claim_type="redundancy")
    _write_defended_run(history / "r2", run_id="r2", claim_type="fallback")
    existing = tmp_path / "knowledge" / "defense_card.json"
    existing.parent.mkdir()
    existing.write_text(json.dumps({"id": "existing", "knowledge_status": "local_reusable"}), encoding="utf-8")

    result = promote_from_history(
        history_root=history,
        output_root=tmp_path / "out",
        knowledge_write_root=existing.parent,
    )

    assert result["status"] == "contested"
    assert result["guard_intents"] == []
    assert result["old_snapshot_sha256"]
    assert json.loads(existing.read_text(encoding="utf-8"))["id"] == "existing"
