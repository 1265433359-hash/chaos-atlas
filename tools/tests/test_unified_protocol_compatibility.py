from __future__ import annotations

import json
from pathlib import Path

import tools.run_p02_formal_batch as p02_batch
from tools.p02_execution_gate import check as p02_gate
from tools.p09_open_discovery_mutation import runtime_map_from_profile


ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "artifacts" / "experiments" / "chaosatlas_10_projects"


def test_p02_formal_batch_keeps_gate_before_runner() -> None:
    source = (ROOT / "tools" / "run_p02_formal_batch.py").read_text(
        encoding="utf-8"
    )
    assert "gate = check(mutation, args.chaos_namespace)" in source
    assert 'gate.get("decision") != "ready_for_injection"' in source


def test_p02_existing_gate_artifact_is_not_marked_as_injected() -> None:
    path = EXP / "open_discovery_results" / "P02" / "seed-1001" / "p02_execution_gate.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    assert value["mutation_applied"] is False
    assert value["summary"]["ready_for_injection"] >= 1


def test_p08_static_gate_stays_blocked_without_runtime_authorization() -> None:
    path = EXP / "runtime_profiles" / "P08-r5" / "profile-manifest.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    assert value["runtime_apply_allowed"] is False


def test_p09_reviewed_profile_builds_namespace_local_runtime_mapping() -> None:
    profile = EXP / "runtime_profiles" / "P09-r4" / "minimal-profile.yaml"
    mapping = runtime_map_from_profile(profile)
    assert mapping["targets"]["compose/service/api"]["namespace"] == "chaosatlas-p09"
    assert mapping["targets"]["compose/service/api"]["workload"]["name"] == "api"
    assert mapping["targets"]["compose/service/api"]["selector"][
        "app.kubernetes.io/part-of"
    ] == "chaosatlas-p09"
