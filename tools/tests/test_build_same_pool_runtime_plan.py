from __future__ import annotations

import json
from pathlib import Path

from tools.build_same_pool_fair_inputs import write_freeze
from tools.build_same_pool_runtime_plan import build_runtime_plan


def _write_selection(root: Path, project: str, seed: int, method: str, candidates: list[str]) -> None:
    path = root / project / f"seed-{seed}" / method
    path.mkdir(parents=True, exist_ok=True)
    payload = {
        "project_id": project,
        "seed": seed,
        "method_id": method,
        "candidate_pool_sha256": "pool",
        "selection": {
            "selected_candidates": [
                {"candidate_id": candidate, "rank": index + 1, "reason": "test"}
                for index, candidate in enumerate(candidates)
            ]
        },
        "status": "completed",
    }
    (path / "selection.json").write_text(json.dumps(payload), encoding="utf-8")


def test_runtime_plan_deduplicates_candidates_and_keeps_selection_mapping(tmp_path: Path) -> None:
    freeze = tmp_path / "freeze"
    write_freeze(freeze)
    candidates = json.loads((freeze / "candidate_pools" / "online-boutique" / "candidates.json").read_text(encoding="utf-8"))
    first = candidates[0]["candidate_id"]
    second = candidates[1]["candidate_id"]
    selections = tmp_path / "selections"
    _write_selection(selections, "online-boutique", 1001, "ChaosAtlas-full", [first, second])
    _write_selection(selections, "online-boutique", 1001, "ChaosAtlas-ablation", [first])

    plan = build_runtime_plan(freeze_root=freeze, selection_root=selections, projects=("online-boutique",))

    assert plan["total_unique_candidates"] == 2
    assert plan["total_runtime_units"] == 4
    first_record = next(item for item in plan["candidates"] if item["candidate_id"] == first)
    assert len(first_record["selected_by"]) == 2
    assert first_record["replicates"] == [1, 2]
    assert first_record["mutation_path"].endswith(".yaml")
