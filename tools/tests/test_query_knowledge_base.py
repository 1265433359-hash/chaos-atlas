from __future__ import annotations

import json
from pathlib import Path

from tools import query_knowledge_base as qkb


def _draft(tmp_path: Path) -> Path:
    root = tmp_path / "rca_loop" / "knowledge_drafts"
    root.mkdir(parents=True)
    card = {
        "id": "KB-RCA-SOCK-CATDB-001",
        "project": "sock-shop",
        "status": "provisional",
        "weakness_id": "WS-sock-shop-catalogue-catalogue-db-podchaos-pod-kill",
        "weakness_status": "confirmed",
        "rca_status": "bounded",
        "knowledge_status": "provisional",
        "test_node": {"family": "PodChaos", "operation": "pod-kill"},
    }
    (root / "KB-RCA-SOCK-CATDB-001.json").write_text(json.dumps(card), encoding="utf-8")
    return root


def test_rca_root_loads_drafts_without_touching_formal_kb(tmp_path: Path) -> None:
    drafts_root = _draft(tmp_path)
    cards = qkb.load_cards(rca_root=drafts_root)
    assert [c["id"] for c in cards] == ["KB-RCA-SOCK-CATDB-001"]


def test_rca_status_and_weakness_id_filters(tmp_path: Path) -> None:
    drafts_root = _draft(tmp_path)

    class Args:
        rca_status = "bounded"
        knowledge_status = None
        weakness_id = "WS-sock-shop-catalogue-catalogue-db-podchaos-pod-kill"

    cards = qkb.load_cards(rca_root=drafts_root)
    assert [c["id"] for c in cards if qkb.matches(c, Args())] == ["KB-RCA-SOCK-CATDB-001"]

    class ArgsNoMatch:
        rca_status = "confirmed"
        knowledge_status = None
        weakness_id = None

    assert [c for c in cards if qkb.matches(c, ArgsNoMatch())] == []


def test_knowledge_status_filter(tmp_path: Path) -> None:
    drafts_root = _draft(tmp_path)

    class Args:
        rca_status = None
        knowledge_status = "local_reusable"
        weakness_id = None

    cards = qkb.load_cards(rca_root=drafts_root)
    assert [c for c in cards if qkb.matches(c, Args())] == []
