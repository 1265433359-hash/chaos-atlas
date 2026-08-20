from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.rca_loop import sha256_json
from tools.sock_shop_rca import (
    actions_for_case,
    build_sock_shop_pilot,
    hypotheses_for_case,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
VERDICT_PATH = REPO_ROOT / "artifacts" / "sock-shop" / "sock_shop_verdicts.json"


def _build(tmp_path: Path) -> dict:
    return build_sock_shop_pilot(
        verdict_path=VERDICT_PATH,
        output_root=tmp_path / "rca_loop",
        project_commit="sock-shop-fixture-commit",
        round_id="pilot-r1",
    )


def test_sock_shop_pilot_builds_three_case_families(tmp_path: Path) -> None:
    output = _build(tmp_path)
    assert [case["case_family"] for case in output["cases"]] == [
        "single_replica_podkill",
        "catalogue_db_podkill",
        "http_abort_propagation",
    ]
    assert all(case["weakness_status"] == "confirmed" for case in output["cases"])
    assert output["cases"][1]["rca_status"] == "bounded"


def test_pilot_writes_expected_artifact_layout(tmp_path: Path) -> None:
    output = _build(tmp_path)
    root = tmp_path / "rca_loop"
    assert (root / "manifest.json").is_file()
    assert len(list((root / "cases").glob("*.json"))) == 3
    assert len(list((root / "hypotheses").glob("*.json"))) >= 3
    plan = json.loads((root / "action_plan.json").read_text(encoding="utf-8"))
    assert plan["schema_version"]
    assert len(plan["case_plans"]) == 3
    # manifest matches the returned object and records input provenance
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest == output
    assert manifest["input"]["verdict_sha256"] == sha256_json(
        json.loads(VERDICT_PATH.read_text(encoding="utf-8"))
    )
    assert manifest["knowledge_base_updated"] is False


def test_every_case_has_a_selected_next_action(tmp_path: Path) -> None:
    output = _build(tmp_path)
    for case in output["cases"]:
        assert case["next_actions"], case["case_family"]
        assert case["next_actions"][0]["status"] == "planned"


def test_catalogue_db_case_stays_bounded_with_competing_hypotheses(tmp_path: Path) -> None:
    output = _build(tmp_path)
    case = output["cases"][1]
    assert case["rca_status"] == "bounded"
    mechanisms = {hyp["mechanism_class"] for hyp in case["hypotheses"]}
    assert mechanisms == {"database_connection_unavailable", "catalogue_error_propagation"}
    assert all(hyp["status"] == "pending" for hyp in case["hypotheses"])


def test_http_abort_case_never_names_missing_timeout(tmp_path: Path) -> None:
    output = _build(tmp_path)
    case = output["cases"][2]
    blob = json.dumps(case)
    assert "missing_timeout" not in blob
    assert case["rca_status"] == "bounded"
    assert case["hypotheses"][0]["mechanism_class"] == "transport_error_propagation"
    assert case["hypotheses"][0]["mechanism_level"] == "service_boundary"


def test_single_replica_case_limits_mechanism_to_no_redundancy(tmp_path: Path) -> None:
    output = _build(tmp_path)
    case = output["cases"][0]
    assert case["rca_status"] == "bounded"
    assert case["hypotheses"][0]["mechanism_class"] == "singleton_workload_no_redundancy"
    assert case["hypotheses"][0]["mechanism_level"] == "deployment"


def test_pilot_output_contains_no_secrets_or_absolute_paths(tmp_path: Path) -> None:
    _build(tmp_path)
    root = tmp_path / "rca_loop"
    for path in root.rglob("*.json"):
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        assert "fake_password" not in lowered
        assert "mysql_root_password" not in lowered
        assert "c:\\users" not in lowered
        for evidence in _iter_evidence(json.loads(text)):
            ref = evidence["source_ref"]
            assert not ref.startswith(("/", "\\"))
            assert ":" not in ref
            assert ".." not in ref.split("/")


def _iter_evidence(node):
    if isinstance(node, dict):
        if "evidence_id" in node and "source_ref" in node:
            yield node
        for value in node.values():
            yield from _iter_evidence(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_evidence(item)


def test_pilot_rejects_non_empty_output_root(tmp_path: Path) -> None:
    root = tmp_path / "rca_loop"
    root.mkdir()
    (root / "stale.txt").write_text("do not overwrite", encoding="utf-8")
    with pytest.raises(FileExistsError):
        build_sock_shop_pilot(
            verdict_path=VERDICT_PATH,
            output_root=root,
            project_commit="sock-shop-fixture-commit",
            round_id="pilot-r1",
        )
    assert (root / "stale.txt").read_text(encoding="utf-8") == "do not overwrite"


def test_pilot_is_deterministic_across_runs(tmp_path: Path) -> None:
    first = _build(tmp_path / "a")
    second = _build(tmp_path / "b")
    assert first == second
    a = (tmp_path / "a" / "rca_loop" / "cases").rglob("*.json")
    for path_a in a:
        path_b = tmp_path / "b" / "rca_loop" / "cases" / path_a.name
        assert path_a.read_text(encoding="utf-8") == path_b.read_text(encoding="utf-8")


def test_hypotheses_for_case_requires_known_family() -> None:
    with pytest.raises(ValueError):
        hypotheses_for_case({"case_family": "unknown", "weakness_id": "WS-x"})


def test_actions_for_case_are_schema_complete(tmp_path: Path) -> None:
    output = _build(tmp_path)
    for case in output["cases"]:
        actions = actions_for_case(case, case["hypotheses"])
        assert actions
        for action in actions:
            for field in (
                "action_id",
                "kind",
                "target_scope",
                "hypotheses_separated",
                "evidence_gain",
                "cost",
                "risk",
                "environment_uncertainty",
                "preconditions",
                "cleanup",
                "output_schema",
                "stop_conditions",
            ):
                assert field in action, field
            assert action["stop_conditions"]


# ---------------------------------------------------------------------------
# Task 8: closed-loop end-to-end over the real pilot artifacts
# ---------------------------------------------------------------------------


def test_pilot_round_trip_is_stable_with_validation(tmp_path: Path) -> None:
    from tools.compile_rca_regression import compile_regression_intents, project_knowledge_draft
    from tools.validate_rca_loop import validate_artifact

    output = _build(tmp_path)
    root = tmp_path / "rca_loop"
    report = validate_artifact(root)
    assert report["valid"] is True, report["errors"]
    drafts = [
        project_knowledge_draft(case, case["hypotheses"], case["next_actions"])
        for case in output["cases"]
    ]
    compiled = compile_regression_intents(drafts, snapshot={"cards": drafts})
    assert compiled["snapshot_sha256"] == sha256_json({"cards": drafts})
    assert all(intent["kind"] == "discriminate" for intent in compiled["intents"])
    # every provisional draft plans follow-up evidence rather than reuse
    assert all(draft["next_evidence"] for draft in drafts)
    assert all(draft["knowledge_status"] == "provisional" for draft in drafts)
