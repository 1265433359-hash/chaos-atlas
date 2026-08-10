import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import build_eshop_socialnet_snapshots as builder  # noqa: E402


def test_builder_uses_full_sha256_pins():
    assert builder.PINNED_KNOWLEDGE_SHA
    assert all(len(value) == 64 for value in builder.PINNED_KNOWLEDGE_SHA.values())


def test_builder_fails_closed_on_knowledge_drift(monkeypatch):
    monkeypatch.setattr(builder, "_sha256", lambda _: "0" * 64)
    with pytest.raises(RuntimeError, match="FAIL-CLOSED"):
        builder._load_current("selection_experience.json")


def test_stage_c_snapshots_remain_scoped_and_correct():
    # Stage C2 (2026-08-10): SOCIALNET helm audited -> valid/full_pre=True;
    # ESHOP has no deployment target -> stays blocked/full_pre=False.
    for name, expected in (
        (
            "eshop_knowledge_snapshot_pre.json",
            {"status": "blocked", "full_pre": False},
        ),
        (
            "socialnet_knowledge_snapshot_pre.json",
            {"status": "valid", "full_pre": True},
        ),
    ):
        snapshot = (ROOT / "artifacts" / "experiments" / "heldout" / name).read_text(
            encoding="utf-8"
        )
        import json

        data = json.loads(snapshot)
        assert data["status"] == expected["status"]
        assert data["full_pre"] is expected["full_pre"]
        assert data["contract"]["candidate_map"] == {}
