from __future__ import annotations

from tools.main_experiment_orchestrator import ACTIVE_LEDGER, active_experiment_arms, build_run_rows


def test_default_experiment_scope_excludes_chaoseater() -> None:
    assert active_experiment_arms() == ["ChaosAtlas-KB-open", "ChaosAtlas-noKB-open"]
    assert ACTIVE_LEDGER.name == "active_atlas_experiment_ledger.json"

    gate = {
        "status": "ready",
        "execution_ready": True,
        "method_result_eligible": True,
        "namespace": "chaosatlas-p02",
        "blocker": None,
        "baseline": {},
        "health": {},
        "recovery": {},
        "cleanup": {},
    }
    ce_gate = {"status": "pass_static", "reason": None}
    rows = build_run_rows("P02", gate, ce_gate)

    assert {row["arm"] for row in rows} == {
        "ChaosAtlas-KB-open",
        "ChaosAtlas-noKB-open",
    }


def test_chaoseater_requires_explicit_unfreeze() -> None:
    assert "ChaosEater-official" in active_experiment_arms(include_chaoseater=True)

    gate = {
        "status": "ready",
        "execution_ready": True,
        "method_result_eligible": True,
        "namespace": "chaosatlas-p02",
        "blocker": None,
        "baseline": {},
        "health": {},
        "recovery": {},
        "cleanup": {},
    }
    ce_gate = {"status": "pass_static", "reason": None}
    rows = build_run_rows("P02", gate, ce_gate, include_chaoseater=True)

    assert {row["arm"] for row in rows} == {
        "ChaosAtlas-KB-open",
        "ChaosAtlas-noKB-open",
        "ChaosEater-official",
    }


def test_run_rows_carry_explicit_policy_rollout_configuration() -> None:
    gate = {
        "status": "ready", "execution_ready": True, "method_result_eligible": True,
        "namespace": "chaosatlas-p02", "blocker": None, "baseline": {}, "health": {}, "recovery": {}, "cleanup": {},
    }
    rows = build_run_rows("P02", gate, {"status": "pass_static", "reason": None}, policy_mode="shadow", policy_budget=2)
    assert rows[0]["policy_mode"] == "shadow"
    assert rows[0]["policy_budget"] == 2
