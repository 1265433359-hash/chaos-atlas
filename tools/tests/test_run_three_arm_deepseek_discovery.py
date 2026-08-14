from __future__ import annotations

import json
from pathlib import Path

from tools.run_three_arm_deepseek_discovery import (
    METHODS,
    bundle_path_for,
    discovery_status,
    run_matrix,
)


def test_three_arm_bundle_paths_are_versioned() -> None:
    root = Path("inputs")
    assert bundle_path_for(root, "demo", 1001, "ChaosAtlas-full-v1") == (
        root / "input_bundles" / "demo" / "seed-1001" / "chaosatlas-full-v1.json"
    )
    assert bundle_path_for(root, "demo", 1001, "ChaosAtlas-full-v2") == (
        root / "input_bundles" / "demo" / "seed-1001" / "chaosatlas-full-v2.json"
    )
    assert bundle_path_for(root, "demo", 1001, "ChaosAtlas-ablation") == (
        root / "input_bundles" / "demo" / "seed-1001" / "chaosatlas-ablation.json"
    )
    assert METHODS == ("ChaosAtlas-full-v1", "ChaosAtlas-full-v2", "ChaosAtlas-ablation")


def test_three_arm_discovery_status_requires_four_selected_and_compiled() -> None:
    handoff = {"status": "handoff_ready", "selected_hypotheses": [{}, {}, {}, {}]}
    mutations = {"status": "valid", "generated": [{}, {}, {}, {}]}
    assert discovery_status(handoff, mutations) == "valid"
    assert discovery_status({**handoff, "selected_hypotheses": [{}, {}, {}]}, mutations) == "method_invalid"
    assert discovery_status(handoff, {**mutations, "generated": [{}, {}, {}]}) == "method_invalid"


def test_run_matrix_preflight_can_limit_to_full_v2_only(tmp_path: Path) -> None:
    input_root = tmp_path / "inputs"
    for seed in (1001, 1002, 1003):
        seed_dir = input_root / "input_bundles" / "demo" / f"seed-{seed}"
        seed_dir.mkdir(parents=True)
        for filename, method in {
            "chaosatlas-full-v1.json": "ChaosAtlas-full-v1",
            "chaosatlas-full-v2.json": "ChaosAtlas-full-v2",
            "chaosatlas-ablation.json": "ChaosAtlas-ablation",
        }.items():
            (seed_dir / filename).write_text(
                json.dumps(
                    {
                        "method_id": method,
                        "seed": seed,
                        "common_input": {
                            "project_id": "demo",
                            "topology": {"nodes": [], "edges": []},
                        },
                        "knowledge_view": None,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
    profile = tmp_path / "profile.json"
    profile.write_text('{"runtime_ready": true}\n', encoding="utf-8")
    key = tmp_path / "key.txt"
    key.write_text("not-used", encoding="utf-8")

    result = run_matrix(
        input_root,
        profile,
        tmp_path / "discovery",
        key,
        execute=False,
        project_id="demo",
        methods=("ChaosAtlas-full-v2",),
    )

    preflight = json.loads((tmp_path / "discovery" / "preflight.json").read_text(encoding="utf-8"))
    assert result["calls"] == 3
    assert preflight["methods"] == ["ChaosAtlas-full-v2"]
    assert {row["method_id"] for row in preflight["records"]} == {"ChaosAtlas-full-v2"}
