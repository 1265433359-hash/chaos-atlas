import hashlib
import json
from pathlib import Path

import pytest

from tools.materialize_p09_selection import materialize


ROOT = Path(__file__).resolve().parents[2]
SELECTION_ROOT = ROOT / "artifacts/experiments/chaosatlas_10_projects/selection_results/P09/teacher-minikube-dual-r1"
POOL = ROOT / "artifacts/experiments/chaosatlas_10_projects/candidate_pools/P09/candidate_pool.json"


def test_materializes_all_selections_without_merging_method_ownership(tmp_path):
    manifest = materialize(SELECTION_ROOT, POOL, tmp_path)
    assert manifest["selection_count"] == 6
    assert manifest["materialized_count"] == 48
    assert len({item["arm"] + str(item["seed"]) for item in manifest["runs"]}) == 6
    assert all(item["human_review"] == "pending" for item in manifest["runs"])
    assert all(item["knowledge_base_updated"] is False for item in manifest["runs"])
    assert len({item["candidate_id"] for item in manifest["runs"]}) <= 16


def test_materialized_yaml_and_provenance_are_hash_bound(tmp_path):
    materialize(SELECTION_ROOT, POOL, tmp_path)
    provenance = sorted(tmp_path.rglob("provenance.json"))[0]
    doc = json.loads(provenance.read_text(encoding="utf-8"))
    mutation = Path(doc["mutation_path"])
    if not mutation.is_absolute():
        mutation = ROOT / mutation
    assert mutation.exists()
    assert hashlib.sha256(mutation.read_bytes()).hexdigest() == doc["mutation_sha256"]
    yaml_text = mutation.read_text(encoding="utf-8")
    assert "namespace: chaosatlas-p09" in yaml_text
    assert "mode: one" in yaml_text
    assert "chaosatlas-p09" in yaml_text


def test_materializer_rejects_invalid_selection(tmp_path):
    broken = tmp_path / "broken"
    (broken / "seed-1001" / "arm").mkdir(parents=True)
    (broken / "seed-1001" / "arm" / "result.json").write_text(
        json.dumps({"status": "invalid", "selected": []}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="valid selection"):
        materialize(broken, POOL, tmp_path / "out")
