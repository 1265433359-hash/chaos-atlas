import json
from pathlib import Path

import pytest

from tools.run_sock_shop_route_aware_remaining import build_units
from tools.run_sock_shop_route_aware_remaining import run_batch


def _write_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    mutation = tmp_path / "catalogue.yaml"
    mutation.write_text("kind: StressChaos\n", encoding="utf-8")
    manifest = tmp_path / "selection_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "fresh_candidates": [
                    {
                        "hypothesis_id": "stress-catalogue",
                        "kind": "StressChaos",
                        "mutation_path": str(mutation),
                        "mutation_sha256": __import__("hashlib").sha256(mutation.read_bytes()).hexdigest(),
                    },
                    {
                        "hypothesis_id": "dns-catalogue",
                        "kind": "DNSChaos",
                        "mutation_path": str(mutation),
                        "mutation_sha256": __import__("hashlib").sha256(mutation.read_bytes()).hexdigest(),
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    gate = tmp_path / "gate.json"
    gate.write_text(
        json.dumps(
            {
                "status": "passed",
                "summary": {"blocked": 0},
                "selection_manifest_sha256": __import__("hashlib").sha256(manifest.read_bytes()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    return manifest, gate, tmp_path / "reports"


def test_build_units_filters_kinds_and_emits_two_replicates(tmp_path: Path) -> None:
    manifest, gate, reports = _write_inputs(tmp_path)

    units = build_units(manifest, gate, reports, kinds={"StressChaos"})

    assert len(units) == 2
    assert [unit["replicate"] for unit in units] == [1, 2]
    assert all(unit["report"].parent == reports for unit in units)


def test_run_batch_stops_on_incomplete_existing_completed_report(tmp_path: Path) -> None:
    manifest, gate, reports = _write_inputs(tmp_path)
    reports.mkdir()
    existing = reports / "stress-catalogue-rep-1.json"
    existing.write_text(json.dumps({"status": "completed"}), encoding="utf-8")

    result = run_batch(manifest, gate, tmp_path / "runtime", reports, kinds={"StressChaos"})

    assert result["status"] == "stopped_on_failure"
    assert result["rows"][0]["evidence_valid"] is False
    assert "baseline_pass" in result["rows"][0]["validation_reasons"]
    assert result["completed_units"] == 0
