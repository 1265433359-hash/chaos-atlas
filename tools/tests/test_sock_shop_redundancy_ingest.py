from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from tools.sock_shop_redundancy_ingest import build_redundancy_round


ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / "artifacts" / "sock-shop" / "rca_loop" / "runtime-live-r2"


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def test_redundancy_ingest_promotes_only_a_valid_counterfactual(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    for name in ("result.json", "timeline.jsonl", "before.json", "after.json", "mutation.yaml", "scale_events.json"):
        original = ROOT / "artifacts" / "sock-shop" / "rca_loop" / "runtime-live-r4-redundancy" / name
        if original.is_file():
            shutil.copyfile(original, source / name)
    output = tmp_path / "output"
    result = build_redundancy_round(parent_root=PARENT, source_root=source, output_root=output)
    assert result["knowledge_status"] == "local_reusable"
    case = json.loads(next((output / "cases").glob("*.json")).read_text(encoding="utf-8"))
    assert case["weakness_status"] == "confirmed"
    assert case["rca_status"] == "bounded"
    assert case["knowledge_status"] == "local_reusable"
    assert "isolated_scale_to_two_counterfactual" not in case["hypotheses"][0]["unsupported_claims"]
    assert case["hypotheses"][0]["unsupported_claims"] == []
    assert (output / "knowledge_drafts" / "regression_intents.json").is_file()


def test_redundancy_ingest_fails_closed_for_non_defended_result(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    _write_json(source / "result.json", {"summary": {"classification": "observation_inconclusive", "deterministic": False}})
    with pytest.raises(ValueError, match="defended"):
        build_redundancy_round(parent_root=PARENT, source_root=source, output_root=tmp_path / "output")
