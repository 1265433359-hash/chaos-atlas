import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HELDOUT = ROOT / "artifacts" / "experiments" / "heldout"


def _read(name):
    return json.loads((HELDOUT / name).read_text(encoding="utf-8"))


def test_v12_registry_is_frozen_and_pool_qualified():
    registry = _read("heldout_v12_candidate_registry.json")
    assert registry["status"] == "frozen"
    assert registry["candidate_count"] == 83
    assert registry["candidate_ids_unique"] is True
    assert registry["pooled_counts"] == {
        "protected": 16,
        "unprotected": 35,
        "unknown": 32,
        "legal_total": 83,
    }
    assert all(registry["pooled_gate"].values())


def test_v12_registry_has_no_result_derived_fields_and_hash_lock():
    registry = _read("heldout_v12_candidate_registry.json")
    snapshot = _read("heldout_v12_freeze_snapshot.json")
    ids = [candidate["candidate_id"] for candidate in registry["candidates"]]
    assert len(ids) == len(set(ids))
    forbidden = {"verdict", "weakness", "selected", "outcome", "result"}
    assert not any(forbidden.intersection(candidate) for candidate in registry["candidates"])
    digest = hashlib.sha256(
        ("\n".join(sorted(ids))).encode("utf-8")
    ).hexdigest()
    assert snapshot["candidate_ids_sha256"] == digest
