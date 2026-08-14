from __future__ import annotations

from pathlib import Path

import hashlib
import json

from tools.run_otel_two_arm_batch import report_path_for, runtime_units


def test_runtime_units_expand_six_calls_to_48_repetitions(tmp_path: Path) -> None:
    discovery = tmp_path / "discovery"
    for seed in (1001, 1002, 1003):
        for method in ("ChaosAtlas-full", "ChaosAtlas-ablation"):
            directory = discovery / f"seed-{seed}" / method.lower()
            mutation_dir = directory / "mutations"
            mutation_dir.mkdir(parents=True)
            selected = []
            for index in range(4):
                signature = f"{seed}{method[-1]}{index}".encode().hex().ljust(64, "0")[:64]
                selected.append({"hypothesis_id": f"H{index + 1}", "canonical_signature": signature})
                (mutation_dir / f"{signature[:12]}.yaml").write_text("kind: PodChaos\n", encoding="utf-8")
            (directory / "handoff.json").write_text(json.dumps({"status": "handoff_ready", "selected_hypotheses": selected}), encoding="utf-8")
    units = runtime_units(discovery, tmp_path / "runtime")
    assert len(units) == 48
    assert {unit["replicate"] for unit in units} == {1, 2}


def test_runtime_units_can_limit_to_full_v2_only(tmp_path: Path) -> None:
    discovery = tmp_path / "discovery"
    for seed in (1001, 1002, 1003):
        method = "ChaosAtlas-full-v2"
        directory = discovery / f"seed-{seed}" / method.lower()
        mutation_dir = directory / "mutations"
        mutation_dir.mkdir(parents=True)
        selected = []
        for index in range(4):
            signature = hashlib.sha256(f"{seed}:{method}:{index}".encode()).hexdigest()
            selected.append({"hypothesis_id": f"H{index + 1}", "canonical_signature": signature})
            (mutation_dir / f"{signature[:12]}.yaml").write_text("kind: PodChaos\n", encoding="utf-8")
        (directory / "handoff.json").write_text(json.dumps({"status": "handoff_ready", "selected_hypotheses": selected}), encoding="utf-8")

    units = runtime_units(discovery, tmp_path / "runtime", methods=("ChaosAtlas-full-v2",))

    assert len(units) == 24
    assert {unit["method"] for unit in units} == {"ChaosAtlas-full-v2"}
    assert report_path_for(tmp_path, "ChaosAtlas-full-v2", 1001, "H1", 1) == (
        tmp_path / "opentelemetry-demo" / "seed-1001" / "chaosatlas-full-v2" / "H1-rep-1.json"
    )


def test_report_path_keeps_method_seed_hypothesis_and_replicate(tmp_path: Path) -> None:
    path = report_path_for(tmp_path, "ChaosAtlas-full", 1002, "H3", 2)
    assert path == tmp_path / "opentelemetry-demo" / "seed-1002" / "chaosatlas-full" / "H3-rep-2.json"


def test_prior_completed_reports_are_reused_but_environment_blocked_report_is_retryable(tmp_path: Path) -> None:
    discovery = tmp_path / "discovery"
    for seed in (1001, 1002, 1003):
        for method in ("ChaosAtlas-full", "ChaosAtlas-ablation"):
            directory = discovery / f"seed-{seed}" / method.lower()
            mutation_dir = directory / "mutations"
            mutation_dir.mkdir(parents=True)
            selected = []
            for index in range(4):
                signature = f"{seed}{method[-1]}{index}".encode().hex().ljust(64, "0")[:64]
                selected.append({"hypothesis_id": f"H{index + 1}", "canonical_signature": signature})
                (mutation_dir / f"{signature[:12]}.yaml").write_text("kind: PodChaos\n", encoding="utf-8")
            (directory / "handoff.json").write_text(json.dumps({"status": "handoff_ready", "selected_hypotheses": selected}), encoding="utf-8")
    prior = tmp_path / "prior"
    current = tmp_path / "current"
    completed = report_path_for(prior, "ChaosAtlas-full", 1001, "H1", 1)
    completed.parent.mkdir(parents=True)
    completed.write_text(json.dumps({"status": "completed", "observation": {"classification": "no_business_impact_observed"}}), encoding="utf-8")
    retry = report_path_for(prior, "ChaosAtlas-full", 1001, "H2", 1)
    retry.parent.mkdir(parents=True, exist_ok=True)
    retry.write_text(json.dumps({"status": "failed", "injection": {"applied": False}, "preflight": {"decision": "blocked"}, "errors": ["runtime applicability gate: blocked"]}), encoding="utf-8")
    units = runtime_units(discovery, current, prior)
    assert units[0]["prior_report"] == completed
    assert units[2]["prior_report"] == retry


def test_multiple_prior_roots_use_first_matching_report(tmp_path: Path) -> None:
    discovery = tmp_path / "discovery"
    for seed in (1001, 1002, 1003):
        for method in ("ChaosAtlas-full", "ChaosAtlas-ablation"):
            directory = discovery / f"seed-{seed}" / method.lower()
            mutation_dir = directory / "mutations"
            mutation_dir.mkdir(parents=True)
            signature = hashlib.sha256(f"{seed}:{method}".encode()).hexdigest()
            (mutation_dir / f"{signature[:12]}.yaml").write_text("kind: PodChaos\n", encoding="utf-8")
            (directory / "handoff.json").write_text(
                json.dumps({"status": "handoff_ready", "selected_hypotheses": [{"hypothesis_id": "H1", "canonical_signature": signature}]}),
                encoding="utf-8",
            )
    first = tmp_path / "first"
    second = tmp_path / "second"
    second_report = report_path_for(second, "ChaosAtlas-full", 1001, "H1", 1)
    second_report.parent.mkdir(parents=True)
    second_report.write_text(json.dumps({"status": "completed"}), encoding="utf-8")
    units = runtime_units(discovery, tmp_path / "current", [first, second])
    assert units[0]["prior_report"] == second_report
