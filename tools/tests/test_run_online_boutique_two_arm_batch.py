from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.run_online_boutique_two_arm_batch import report_path_for, runtime_units


def test_online_boutique_batch_can_limit_to_full_v2_seed(tmp_path: Path) -> None:
    discovery = tmp_path / "discovery"
    method = "ChaosAtlas-full-v2"
    directory = discovery / "seed-1001" / method.lower()
    mutations = directory / "mutations"
    mutations.mkdir(parents=True)
    selected = []
    for index in range(4):
        signature = hashlib.sha256(f"1001:{method}:{index}".encode()).hexdigest()
        selected.append({"hypothesis_id": f"H{index + 1}", "canonical_signature": signature})
        (mutations / f"{signature[:12]}.yaml").write_text("kind: PodChaos\n", encoding="utf-8")
    (directory / "handoff.json").write_text(
        json.dumps({"status": "handoff_ready", "selected_hypotheses": selected}),
        encoding="utf-8",
    )

    units = runtime_units(discovery, tmp_path / "runtime", methods=("ChaosAtlas-full-v2",), seeds=(1001,))

    assert len(units) == 8
    assert {unit["method"] for unit in units} == {"ChaosAtlas-full-v2"}
    assert report_path_for(tmp_path, "ChaosAtlas-full-v2", 1001, "H1", 2) == (
        tmp_path / "seed-1001" / "chaosatlas-full-v2" / "H1" / "rep-2.json"
    )
