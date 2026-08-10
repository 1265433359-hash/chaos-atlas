"""Stage D candidate-pool generator tests.

All tests are unit-level: they read the frozen snapshots (read-only) and write
generated YAML into pytest tmp dirs. They never write to the versioned
artifacts tree and never run any selection/experiment.
"""

import json
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import build_heldout_candidate_pools as gp  # noqa: E402

HELDOUT = ROOT / "artifacts" / "experiments" / "heldout"


def _snapshot(project: str) -> dict:
    return json.loads((HELDOUT / f"{project.lower()}_knowledge_snapshot_pre.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# protection_class rule (static, project-agnostic)
# ---------------------------------------------------------------------------

def test_protection_class_rules():
    # explicit_timeout absorbs delay -> protected; loss is unknown (loss_bounded=false).
    assert gp.protection_class({"contract": "explicit_timeout", "loss_bounded": False}, "delay", None) == "protected"
    assert gp.protection_class({"contract": "explicit_timeout", "loss_bounded": False}, "loss", None) == "unknown"
    # retry-only with unverified timeout -> never protected.
    assert gp.protection_class({"contract": "retry_policy_timeout_unknown"}, "delay", None) == "unknown"
    assert gp.protection_class({"contract": "retry_policy_timeout_unknown"}, "loss", None) == "unknown"
    # no_timeout -> unprotected.
    assert gp.protection_class({"contract": "no_timeout"}, "delay", None) == "unprotected"
    assert gp.protection_class({"contract": "no_timeout"}, "loss", None) == "unprotected"
    # kill: single-replica no-PDB -> unprotected; redundancy -> protected.
    assert gp.protection_class(None, "kill", {"replicas": 1, "pdb": None}) == "unprotected"
    assert gp.protection_class(None, "kill", {"replicas": 3, "pdb": {"minAvailable": 1}}) == "protected"
    with pytest.raises(ValueError):
        gp.protection_class({"contract": "some_unknown_contract"}, "delay", None)
    with pytest.raises(ValueError):
        gp.protection_class(None, "cpu", None)


# ---------------------------------------------------------------------------
# full neutral candidate construction from the frozen snapshots
# ---------------------------------------------------------------------------

def test_hotel_full_pool_is_unprotected_only():
    snapshot = _snapshot("HOTEL")
    full = gp.build_full_candidates("HOTEL", snapshot)
    # 5 no_timeout edges x (delay 3 tiers + loss 3 tiers) + 8 verified k8s services.
    assert len(full) == 5 * 6 + 8
    classes = {c["protection_class"] for c in full}
    assert classes == {"unprotected"}
    # REVIEW/ATTRACTIONS are k8s-unavailable and must never appear.
    assert all(c["target_service"] not in {"REVIEW", "ATTRACTIONS"} for c in full)
    assert all(c["mode"] == "one" for c in full)
    # every network candidate carries the frozen contract SHA.
    for c in full:
        if c["fault_family"] in ("delay", "loss"):
            assert len(c["contract_source_sha256"]) == 64


def test_socialnet_full_pool_has_all_three_classes_and_excludes_unverified():
    snapshot = _snapshot("SOCIALNET")
    full = gp.build_full_candidates("SOCIALNET", snapshot)
    classes = {c["protection_class"] for c in full}
    assert classes == {"protected", "unprotected", "unknown"}
    assert sum(1 for c in full if c["protection_class"] == "protected") == 9 * 3  # 9 delay edges x 3 tiers
    assert sum(1 for c in full if c["protection_class"] == "unknown") == 9 * 3  # 9 loss edges x 3 tiers
    assert sum(1 for c in full if c["protection_class"] == "unprotected") == 12  # kill targets
    # the 3 unverified edges must never appear as source_edge.
    unverified = set(snapshot["contract"].get("unverified_contract_edges", []))
    edges = {c["source_edge"] for c in full if c["source_edge"]}
    assert not (edges & unverified)


def test_teastore_retry_only_edges_are_never_protected():
    snapshot = _snapshot("TEASTORE")
    full = gp.build_full_candidates("TEASTORE", snapshot)
    # 4 retry-only edges x (delay 3 + loss 3) -> unknown; 7 deployments -> unprotected kill.
    assert len(full) == 4 * 6 + 7
    assert all(c["protection_class"] != "protected" for c in full)
    assert sum(1 for c in full if c["protection_class"] == "unknown") == 24
    assert sum(1 for c in full if c["protection_class"] == "unprotected") == 7


def test_candidate_ids_unique_and_fault_tokens_present():
    for project in ("HOTEL", "SOCIALNET", "TEASTORE"):
        full = gp.build_full_candidates(project, _snapshot(project))
        ids = [c["candidate_id"] for c in full]
        assert len(ids) == len(set(ids))
        # fault families appear in the id tokens (decision_engine fault_of compatible).
        for c in full:
            assert c["fault_family"].upper() in c["candidate_id"].upper()
            # single project prefix only (regression: 'HOTEL-HOTEL-...' must never occur).
            assert not c["candidate_id"].startswith(f"{project}-{project}-")


# ---------------------------------------------------------------------------
# deterministic quota draw
# ---------------------------------------------------------------------------

def test_socialnet_pilot_draw_meets_8_8_8():
    snapshot = _snapshot("SOCIALNET")
    full = gp.build_full_candidates("SOCIALNET", snapshot)
    pilot = gp.draw_pool(full, gp.PILOT_QUOTA, gp.PILOT_PER_PROJECT)
    assert len(pilot) == 24
    c = gp.counts(pilot)
    assert c["protected"] == 8 and c["unprotected"] == 8 and c["unknown"] == 8
    assert set(c["fault_family"]) == {"delay", "loss", "kill"}
    # deterministic: same input -> same draw.
    pilot2 = gp.draw_pool(full, gp.PILOT_QUOTA, gp.PILOT_PER_PROJECT)
    assert [x["candidate_id"] for x in pilot] == [x["candidate_id"] for x in pilot2]

    # formal: classes are quota-capped; unprotected has only 12 kill targets
    # (<16) -> the pool freezes at 44 and the 4-candidate gap is reported.
    formal = gp.draw_pool(full, gp.FORMAL_QUOTA, gp.FORMAL_PER_PROJECT)
    formal_st = gp.quota_status("SOCIALNET", gp.counts(formal), gp.FORMAL_QUOTA, gp.FORMAL_PER_PROJECT)
    assert formal_st["counts"]["total"] == 44
    assert formal_st["counts"]["protected"] == 16 and formal_st["counts"]["unknown"] == 16
    assert formal_st["counts"]["unprotected"] == 12
    assert formal_st["shortfall"]["unprotected"]["missing"] == 4
    assert formal_st["status"] == "quota_shortfall"


def test_draw_covers_all_three_fault_families_per_class_slice():
    # regression: a quota slice must not collapse to a single fault family
    # (HOTEL unprotected pilot was all-kill before the class/fault rotation).
    hotel_pilot = gp.draw_pool(gp.build_full_candidates("HOTEL", _snapshot("HOTEL")),
                               gp.PILOT_QUOTA, gp.PILOT_PER_PROJECT)
    ff = {c["fault_family"] for c in hotel_pilot}
    assert ff == {"delay", "loss", "kill"}

    tea_pilot = gp.draw_pool(gp.build_full_candidates("TEASTORE", _snapshot("TEASTORE")),
                             gp.PILOT_QUOTA, gp.PILOT_PER_PROJECT)
    assert {c["fault_family"] for c in tea_pilot} == {"delay", "loss", "kill"}


def test_hotel_and_teastore_quota_shortfalls_are_detected_not_padded():
    hotel = gp.draw_pool(gp.build_full_candidates("HOTEL", _snapshot("HOTEL")),
                         gp.PILOT_QUOTA, gp.PILOT_PER_PROJECT)
    hotel_st = gp.quota_status("HOTEL", gp.counts(hotel), gp.PILOT_QUOTA, gp.PILOT_PER_PROJECT)
    # HOTEL has no protected/unknown static evidence: pilot freezes at the
    # legally reachable 8 (0/8/0); protected/unknown gaps are reported, never padded.
    assert hotel_st["counts"]["total"] == 8
    assert hotel_st["counts"]["protected"] == 0
    assert hotel_st["counts"]["unprotected"] == 8
    assert hotel_st["counts"]["unknown"] == 0
    assert hotel_st["status"] == "quota_shortfall"
    assert hotel_st["shortfall"]["protected"]["missing"] == 8
    assert hotel_st["shortfall"]["unknown"]["missing"] == 8

    tea = gp.draw_pool(gp.build_full_candidates("TEASTORE", _snapshot("TEASTORE")),
                       gp.PILOT_QUOTA, gp.PILOT_PER_PROJECT)
    tea_st = gp.quota_status("TEASTORE", gp.counts(tea), gp.PILOT_QUOTA, gp.PILOT_PER_PROJECT)
    assert tea_st["counts"]["total"] == 15
    assert tea_st["counts"]["protected"] == 0
    assert tea_st["counts"]["unprotected"] == 7
    assert tea_st["counts"]["unknown"] == 8


# ---------------------------------------------------------------------------
# YAML rendering (mode=one, parseable, correct selector facts)
# ---------------------------------------------------------------------------

def test_render_yaml_network_and_kill(tmp_path):
    # SOCIALNET network edge (app label from committed ablation templates).
    snapshot = _snapshot("SOCIALNET")
    full = gp.build_full_candidates("SOCIALNET", snapshot)
    network = next(c for c in full if c["fault_family"] == "delay")
    text = gp.render_yaml("SOCIALNET", network)
    doc = yaml.safe_load(text)
    assert doc["kind"] == "NetworkChaos"
    assert doc["spec"]["mode"] == "one"
    assert doc["spec"]["action"] == "delay"
    # app label follows the committed ablation mapping for the edge target.
    assert doc["spec"]["selector"]["labelSelectors"]["app"] == gp.SOCIALNET_EDGE_APP_LABEL[network["target_service"]]
    assert doc["spec"]["selector"]["namespaces"] == ["heldout-socialnet-lab"]
    assert doc["spec"]["duration"] == "30s"
    assert doc["spec"]["direction"] == "to"

    # SOCIALNET kill (snapshot availability key as app label).
    kill = next(c for c in full if c["fault_family"] == "kill")
    kdoc = yaml.safe_load(gp.render_yaml("SOCIALNET", kill))
    assert kdoc["kind"] == "PodChaos"
    assert kdoc["spec"]["action"] == "pod-kill"
    assert kdoc["spec"]["mode"] == "one"

    # HOTEL/TEASTORE convention-based labels render and parse.
    hotel = gp.build_full_candidates("HOTEL", _snapshot("HOTEL"))
    assert yaml.safe_load(gp.render_yaml("HOTEL", hotel[0]))["spec"]["mode"] == "one"
    tea = gp.build_full_candidates("TEASTORE", _snapshot("TEASTORE"))
    assert yaml.safe_load(gp.render_yaml("TEASTORE", tea[0]))["spec"]["mode"] == "one"


def test_annotate_writes_yaml_to_tmp_only(tmp_path):
    snapshot = _snapshot("SOCIALNET")
    full = gp.build_full_candidates("SOCIALNET", snapshot)
    annotated = gp.annotate_with_yaml("SOCIALNET", full[:3], tmp_path)
    for c in annotated:
        assert c["yaml_path"].endswith(".yaml")
        assert len(c["yaml_sha256"]) == 64
        assert (tmp_path / f"SOCIALNET/{c['candidate_id']}.yaml").exists()
    # the out_dir parameter is the only write target: tmp_path must NOT be
    # under the versioned heldout tree.
    assert not str(tmp_path).startswith(str(HELDOUT))
