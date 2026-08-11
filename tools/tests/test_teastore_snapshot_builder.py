import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _snapshot():
    path = ROOT / "artifacts" / "experiments" / "heldout" / "teastore_knowledge_snapshot_pre.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_teastore_snapshot_is_explicitly_pre_and_hashable():
    data = _snapshot()
    assert data["status"] == "valid"
    assert data["full_pre"] is True
    assert data["contract"]["candidate_map"] == {}
    assert all("..." not in item["path"] for item in data["provenance"]["source_files"])


def test_teastore_retry_does_not_claim_timeout_protection():
    data = _snapshot()
    contracts = data["contract"]["contracts"]
    assert contracts
    assert all(entry["loss_bounded"] is False for entry in contracts.values())
    assert all(entry["timeout_ms"] == "unknown" for entry in contracts.values())


def test_teastore_source_provenance_has_full_hashes():
    data = _snapshot()
    assert all(len(value) == 64 for value in data["provenance"]["sha256"].values())
