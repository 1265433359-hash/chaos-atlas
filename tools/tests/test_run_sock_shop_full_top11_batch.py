import hashlib
import json
from pathlib import Path

import pytest

from tools.run_sock_shop_full_top11_batch import build_units, run_batch


def _mutation(tmp_path: Path, name: str) -> Path:
    path = tmp_path / f"{name}.yaml"
    path.write_text(
        "apiVersion: chaos-mesh.org/v1alpha1\nkind: PodChaos\n"
        f"metadata:\n  name: {name}\n  namespace: chaosatlas-sock-shop\n"
        "spec:\n  action: pod-kill\n  mode: one\n  selector:\n"
        "    namespaces: [chaosatlas-sock-shop]\n    labelSelectors: {name: front-end}\n",
        encoding="utf-8",
    )
    return path


def test_build_units_only_creates_two_replicates_for_fresh_entries(tmp_path):
    mutation = _mutation(tmp_path, "fresh")
    plan = {
        "entries": [
            {
                "rank": 1,
                "hypothesis_id": "fresh-h",
                "execution_status": "fresh_required",
                "source_path": str(mutation),
                "mutation_sha256": hashlib.sha256(mutation.read_bytes()).hexdigest(),
            },
            {"rank": 2, "hypothesis_id": "reused", "execution_status": "reused_historical"},
            {"rank": 3, "hypothesis_id": "blocked", "execution_status": "blocked"},
        ]
    }

    units = build_units(plan, tmp_path / "runtime")

    assert [unit["replicate"] for unit in units] == [1, 2]
    assert all(unit["hypothesis_id"] == "fresh-h" for unit in units)
    assert all("rank-01" in unit["report"].name for unit in units)


def test_build_units_rejects_changed_mutation(tmp_path):
    mutation = _mutation(tmp_path, "fresh")
    plan = {
        "entries": [
            {
                "rank": 1,
                "hypothesis_id": "fresh-h",
                "execution_status": "fresh_required",
                "source_path": str(mutation),
                "mutation_sha256": "wrong",
            }
        ]
    }

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        build_units(plan, tmp_path / "runtime")


def test_plan_fixture_is_json_serializable(tmp_path):
    mutation = _mutation(tmp_path, "fresh")
    plan = {
        "entries": [
            {
                "rank": 1,
                "hypothesis_id": "fresh-h",
                "execution_status": "fresh_required",
                "source_path": str(mutation),
                "mutation_sha256": hashlib.sha256(mutation.read_bytes()).hexdigest(),
            }
        ]
    }
    assert json.loads(json.dumps(plan))["entries"][0]["rank"] == 1


def test_run_batch_writes_completed_empty_result(tmp_path):
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps({"entries": []}), encoding="utf-8")

    result = run_batch(plan_path, tmp_path / "runtime")

    assert result["status"] == "completed"
    assert result["completed_units"] == 0
    assert result["total_units"] == 0
    assert (tmp_path / "runtime" / "batch-progress.json").exists()
