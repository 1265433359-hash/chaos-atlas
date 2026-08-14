from pathlib import Path

import hashlib
import json

import pytest

from tools.run_sock_shop_two_arm_batch import find_completed_report, report_path_for, runtime_units


def test_sock_shop_batch_expands_six_handoffs_to_48_units(tmp_path: Path) -> None:
    discovery = tmp_path / "discovery"
    for seed in (1001, 1002, 1003):
        for method in ("ChaosAtlas-full", "ChaosAtlas-ablation"):
            directory = discovery / f"seed-{seed}" / method.lower()
            mutations = directory / "mutations"
            mutations.mkdir(parents=True)
            selected = []
            for index in range(4):
                signature = hashlib.sha256(f"{seed}:{method}:{index}".encode()).hexdigest()
                selected.append({"hypothesis_id": f"H{index + 1}", "canonical_signature": signature})
                (mutations / f"{signature[:12]}.yaml").write_text("kind: PodChaos\n", encoding="utf-8")
            (directory / "handoff.json").write_text(json.dumps({"status": "handoff_ready", "selected_hypotheses": selected}), encoding="utf-8")
    units = runtime_units(discovery, tmp_path / "runtime")
    assert len(units) == 48
    assert report_path_for(tmp_path, "ChaosAtlas-full", 1001, "H1", 2).name == "H1-rep-2.json"


def test_sock_shop_batch_can_limit_to_full_v2_only(tmp_path: Path) -> None:
    discovery = tmp_path / "discovery"
    for seed in (1001, 1002, 1003):
        method = "ChaosAtlas-full-v2"
        directory = discovery / f"seed-{seed}" / method.lower()
        mutations = directory / "mutations"
        mutations.mkdir(parents=True)
        selected = []
        for index in range(4):
            signature = hashlib.sha256(f"{seed}:{method}:{index}".encode()).hexdigest()
            selected.append({"hypothesis_id": f"hyp-{index + 1:03d}", "canonical_signature": signature})
            (mutations / f"{signature[:12]}.yaml").write_text("kind: PodChaos\n", encoding="utf-8")
        (directory / "handoff.json").write_text(json.dumps({"status": "handoff_ready", "selected_hypotheses": selected}), encoding="utf-8")

    units = runtime_units(discovery, tmp_path / "runtime", methods=("ChaosAtlas-full-v2",))

    assert len(units) == 24
    assert {unit["method"] for unit in units} == {"ChaosAtlas-full-v2"}
    assert report_path_for(tmp_path, "ChaosAtlas-full-v2", 1001, "hyp-001", 2) == (
        tmp_path / "sock-shop" / "seed-1001" / "chaosatlas-full-v2" / "hyp-001-rep-2.json"
    )


def test_sock_shop_batch_rejects_handoff_with_fewer_than_four_hypotheses(tmp_path: Path) -> None:
    discovery = tmp_path / "discovery"
    directory = discovery / "seed-1001" / "chaosatlas-full"
    (directory / "mutations").mkdir(parents=True)
    signature = hashlib.sha256(b"only-one").hexdigest()
    (directory / "handoff.json").write_text(
        json.dumps({"status": "handoff_ready", "selected_hypotheses": [{"hypothesis_id": "H1", "canonical_signature": signature}]}),
        encoding="utf-8",
    )
    (directory / "mutations" / f"{signature[:12]}.yaml").write_text("kind: PodChaos\n", encoding="utf-8")

    with pytest.raises(ValueError, match="exactly four"):
        runtime_units(discovery, tmp_path / "runtime")


def test_find_completed_report_ignores_failed_prior_report(tmp_path: Path) -> None:
    report = report_path_for(tmp_path / "prior", "ChaosAtlas-full", 1001, "H1", 1)
    report.parent.mkdir(parents=True)
    report.write_text(json.dumps({"status": "failed"}), encoding="utf-8")
    assert find_completed_report([tmp_path / "prior"], "ChaosAtlas-full", 1001, "H1", 1) is None
    report.write_text(json.dumps({"status": "completed"}), encoding="utf-8")
    assert find_completed_report([tmp_path / "prior"], "ChaosAtlas-full", 1001, "H1", 1) == report
