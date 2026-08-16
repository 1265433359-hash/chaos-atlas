import hashlib
import json
from pathlib import Path

from tools.run_sock_shop_r5_selection_batch import build_units, run_batch


def _files(tmp_path: Path):
    mutations = []
    for index in range(2):
        path = tmp_path / f"m-{index}.yaml"
        path.write_text("kind: PodChaos\n", encoding="utf-8")
        mutations.append(path)
    selection = tmp_path / "selection.json"
    selection.write_text(
        json.dumps(
            {
                "groups": {
                    "overlap_high_confidence": [
                        {
                            "group": "overlap_high_confidence",
                            "full_hypothesis_id": "full-1",
                            "ablation_hypothesis_id": "ab-overlap-1",
                            "mutation_path": str(mutations[0]),
                            "mutation_sha256": hashlib.sha256(mutations[0].read_bytes()).hexdigest(),
                        }
                    ],
                    "ablation_only_random": [
                        {
                            "group": "ablation_only_random",
                            "ablation_hypothesis_id": "ab-only-1",
                            "mutation_path": str(mutations[1]),
                            "mutation_sha256": hashlib.sha256(mutations[1].read_bytes()).hexdigest(),
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    gate = tmp_path / "gate.json"
    gate.write_text(
        json.dumps(
            {
                "status": "passed",
                "selection_manifest_sha256": hashlib.sha256(selection.read_bytes()).hexdigest(),
                "summary": {"selected": 2, "ready_for_injection": 2, "blocked": 0},
            }
        ),
        encoding="utf-8",
    )
    return selection, gate


def test_build_units_expands_each_selected_mutation_to_two_fresh_replicates(tmp_path):
    selection, gate = _files(tmp_path)

    units = build_units(selection, gate, tmp_path / "runtime")

    assert len(units) == 4
    assert {unit["replicate"] for unit in units} == {1, 2}
    assert {unit["group"] for unit in units} == {"overlap_high_confidence", "ablation_only_random"}
    assert all(unit["arm"] == "ChaosAtlas-ablation-r5" for unit in units)


def test_batch_runs_serially_and_writes_completed_progress(tmp_path, monkeypatch):
    selection, gate = _files(tmp_path)
    calls = []

    class Completed:
        returncode = 0

    def fake_run(command, **_kwargs):
        calls.append(command)
        report = Path(command[command.index("--report") + 1])
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            json.dumps({"status": "completed", "observation": {"classification": "no_business_impact_observed"}}),
            encoding="utf-8",
        )
        return Completed()

    monkeypatch.setattr("tools.run_sock_shop_r5_selection_batch.subprocess.run", fake_run)
    runtime = tmp_path / "runtime"

    result = run_batch(selection, gate, runtime)

    assert result["status"] == "completed"
    assert result["completed_units"] == 4
    assert len(calls) == 4
    assert all(row["skipped_existing"] is False for row in result["rows"])
    assert (runtime / "batch-progress.json").exists()
