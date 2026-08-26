from __future__ import annotations

import json
import shutil
from pathlib import Path
from uuid import uuid4

import tools.chaosatlas_batch as batch_module
from tools.chaosatlas_batch import (
    append_batch_state,
    build_batch_manifest,
    enrich_batch_result_from_artifacts,
    run_live_batch,
    summarize_batch_results,
    validate_batch_resume,
)


def test_build_batch_manifest_is_stable_and_captures_immutable_inputs():
    manifest = build_batch_manifest(
        profile_sha256="profile-hash",
        kube_context="minikube",
        namespace="sock-shop-lab",
        candidate_space_sha256="candidate-hash",
        selected_candidate_ids=["front-end:pod_kill", "catalogue:pod_kill"],
        approve_live=False,
    )

    assert manifest["schema_version"] == "chaosatlas-live-batch-manifest-v1"
    assert manifest["immutable"]["kube_context"] == "minikube"
    assert manifest["selected_candidate_ids"] == ["front-end:pod_kill", "catalogue:pod_kill"]
    assert manifest["approval_contract"] == {"approve_live": False}


def test_append_batch_state_writes_append_only_records():
    root = Path.cwd() / f".pytest-tmp-batch-productization-{uuid4().hex}"
    try:
        path = root / "batch_state.jsonl"
        append_batch_state(path, candidate_id="front-end:pod_kill", state="planned")
        append_batch_state(path, candidate_id="front-end:pod_kill", state="preflight_blocked", reason="approval_required")

        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        assert [row["state"] for row in rows] == ["planned", "preflight_blocked"]
        assert rows[-1]["reason"] == "approval_required"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_summarize_batch_results_distinguishes_cleanup_failure_and_blocked():
    summary = summarize_batch_results(
        [
            {"candidate_id": "a", "status": "live_completed", "cleanup_status": "verified", "classification": "availability_degraded", "rca_status": "confirmed", "knowledge_status": "promoted"},
            {"candidate_id": "b", "status": "environment_blocked", "error": "approval required"},
            {"candidate_id": "c", "status": "live_completed", "cleanup_status": "failed", "classification": "availability_degraded"},
        ],
        planned_count=3,
    )

    assert summary["status"] == "partial"
    assert summary["planned_count"] == 3
    assert summary["completed_count"] == 1
    assert summary["blocked_count"] == 1
    assert summary["cleanup_failed_count"] == 1
    assert summary["confirmed_finding_count"] == 1
    assert summary["rca_confirmed_count"] == 1
    assert summary["knowledge_promoted_count"] == 1


def test_run_live_batch_persists_manifest_state_and_aggregate():
    root = Path.cwd() / f".pytest-tmp-batch-execution-{uuid4().hex}"
    try:
        profile_path = root / "profile.json"
        profile_path.parent.mkdir(parents=True)
        profile_path.write_text(
            json.dumps({
                "project_id": "sock-shop",
                "namespace": "sock-shop-lab",
                "business_oracles": [{"service": "front-end", "remote_port": 80}],
            }),
            encoding="utf-8",
        )

        class Adapter:
            def inventory(self, profile=None):
                return {"project_id": "sock-shop", "namespace": "sock-shop-lab", "inventory_sha256": "inventory-hash"}

            def detect_server_deployment(self, inventory):
                return {"status": "verified"}

            def map_test_nodes(self, detection):
                return {"status": "verified", "candidates": [{"candidate_id": "front-end:pod_kill", "target": "front-end"}]}

        def fake_run_closed_loop(**kwargs):
            return {"status": "environment_blocked", "input_snapshot_sha256": "snapshot"}

        original = batch_module.run_closed_loop
        batch_module.run_closed_loop = fake_run_closed_loop
        try:
            output = root / "batch"
            result = run_live_batch(profile_path=profile_path, output_root=output, live_adapter=Adapter())
        finally:
            batch_module.run_closed_loop = original

        assert result["status"] == "environment_blocked"
        assert (output / "batch_manifest.json").is_file()
        assert (output / "batch_state.jsonl").is_file()
        assert json.loads((output / "batch_summary.json").read_text(encoding="utf-8"))["blocked_count"] == 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_run_live_batch_forwards_seed_to_child_and_manifest(monkeypatch):
    root = Path.cwd() / f".pytest-tmp-batch-seed-{uuid4().hex}"
    try:
        profile_path = root / "profile.json"
        profile_path.parent.mkdir(parents=True)
        profile_path.write_text(
            json.dumps({
                "project_id": "sock-shop",
                "project_commit": "sock-shop-fixture-commit",
                "namespace": "sock-shop-lab",
                "business_oracles": [{"service": "front-end", "remote_port": 80}],
            }),
            encoding="utf-8",
        )

        class Adapter:
            def inventory(self, profile=None):
                return {"project_id": "sock-shop", "namespace": "sock-shop-lab", "inventory_sha256": "inventory-hash"}

            def detect_server_deployment(self, inventory):
                return {"status": "verified"}

            def map_test_nodes(self, detection):
                return {"status": "verified", "candidates": [{"candidate_id": "front-end:pod_kill", "target": "front-end"}]}

        captured = []

        def fake_run_closed_loop(**kwargs):
            captured.append(kwargs["seed"])
            output = Path(kwargs["output_root"])
            output.mkdir(parents=True, exist_ok=True)
            (output / "cleanup_report.json").write_text(json.dumps({"status": "verified"}), encoding="utf-8")
            return {"status": "environment_blocked"}

        monkeypatch.setattr(batch_module, "run_closed_loop", fake_run_closed_loop)
        output = root / "batch"
        result = run_live_batch(
            profile_path=profile_path,
            output_root=output,
            live_adapter=Adapter(),
            max_candidates=1,
            seed=1002,
        )

        assert result["status"] == "environment_blocked"
        assert captured == [1002]
        manifest = json.loads((output / "batch_manifest.json").read_text(encoding="utf-8"))
        assert manifest["immutable"]["seed"] == 1002
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_validate_batch_resume_rejects_changed_immutable_inputs():
    original = build_batch_manifest(
        profile_sha256="profile-hash",
        kube_context="minikube",
        namespace="sock-shop-lab",
        candidate_space_sha256="candidate-hash",
        selected_candidate_ids=["front-end:pod_kill"],
        approve_live=False,
    )
    changed = {**original, "immutable": {**original["immutable"], "kube_context": "docker-desktop"}}

    try:
        validate_batch_resume(original, changed, latest_states={"front-end:pod_kill": "planned"})
    except ValueError as exc:
        assert "immutable input changed" in str(exc)
    else:
        raise AssertionError("changed context must reject resume")


def test_validate_batch_resume_rejects_live_mutation_boundary():
    manifest = build_batch_manifest(
        profile_sha256="profile-hash",
        kube_context="minikube",
        namespace="sock-shop-lab",
        candidate_space_sha256="candidate-hash",
        selected_candidate_ids=["front-end:pod_kill"],
        approve_live=True,
    )

    try:
        validate_batch_resume(manifest, manifest, latest_states={"front-end:pod_kill": "live_completed"})
    except ValueError as exc:
        assert "mutation boundary" in str(exc)
    else:
        raise AssertionError("live mutation must reject resume")


def test_run_live_batch_resume_skips_cleanup_verified_child(monkeypatch):
    root = Path.cwd() / f".pytest-tmp-batch-resume-{uuid4().hex}"
    try:
        profile_path = root / "profile.json"
        profile_path.parent.mkdir(parents=True)
        profile_path.write_text(
            json.dumps({
                "project_id": "sock-shop",
                "namespace": "sock-shop-lab",
                "business_oracles": [{"service": "front-end", "remote_port": 80}],
            }),
            encoding="utf-8",
        )

        class Adapter:
            def inventory(self, profile=None):
                return {"project_id": "sock-shop", "namespace": "sock-shop-lab", "inventory_sha256": "inventory-hash"}

            def detect_server_deployment(self, inventory):
                return {"status": "verified"}

            def map_test_nodes(self, detection):
                return {"status": "verified", "candidates": [{"candidate_id": "front-end:pod_kill", "target": "front-end"}]}

        calls = 0

        def fake_run_closed_loop(**kwargs):
            nonlocal calls
            calls += 1
            output = Path(kwargs["output_root"])
            output.mkdir(parents=True, exist_ok=True)
            (output / "cleanup_report.json").write_text(json.dumps({"status": "verified"}), encoding="utf-8")
            return {"status": "live_completed"}

        monkeypatch.setattr(batch_module, "run_closed_loop", fake_run_closed_loop)
        output = root / "batch"
        first = run_live_batch(profile_path=profile_path, output_root=output, live_adapter=Adapter(), approve_live=True)
        second = run_live_batch(profile_path=profile_path, output_root=output, live_adapter=Adapter(), approve_live=True, resume=True)

        assert first["status"] == "completed"
        assert second["status"] == "completed"
        assert calls == 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_enrich_batch_result_reads_child_classification_rca_and_knowledge():
    child = Path.cwd() / f".pytest-tmp-batch-artifact-enrichment-{uuid4().hex}"
    try:
        child.mkdir(parents=True)
        (child / "finding_report.json").write_text(json.dumps({"payload": {"result": "availability_degraded"}}), encoding="utf-8")
        (child / "rca_report.json").write_text(json.dumps({"payload": {"rca_status": "confirmed"}}), encoding="utf-8")
        (child / "knowledge_draft.json").write_text(json.dumps({"payload": {"knowledge_status": "provisional"}}), encoding="utf-8")

        result = enrich_batch_result_from_artifacts({"status": "live_completed"}, child)

        assert result["classification"] == "availability_degraded"
        assert result["rca_status"] == "confirmed"
        assert result["knowledge_status"] == "provisional"
    finally:
        shutil.rmtree(child, ignore_errors=True)


def test_run_live_batch_policy_valve_selects_guarded_candidate(monkeypatch):
    root = Path.cwd() / f".pytest-tmp-batch-policy-{uuid4().hex}"
    try:
        profile_path = root / "profile.json"
        profile_path.parent.mkdir(parents=True)
        profile_path.write_text(
            json.dumps({
                "project_id": "sock-shop",
                "project_commit": "a" * 40,
                "namespace": "sock-shop-lab",
                "business_oracles": [{"service": "front-end", "remote_port": 80}],
            }),
            encoding="utf-8",
        )

        class Adapter:
            def inventory(self, profile=None):
                return {"project_id": "sock-shop", "namespace": "sock-shop-lab", "inventory_sha256": "inventory-hash"}

            def detect_server_deployment(self, inventory):
                return {"status": "verified"}

            def map_test_nodes(self, detection):
                return {
                    "status": "verified",
                    "candidates": [
                        {"candidate_id": "candidate-a", "target": "front-end", "target_kind": "deployment", "fault_family": "pod_kill", "status": "eligible"},
                        {"candidate_id": "candidate-b", "target": "front-end", "target_kind": "deployment", "fault_family": "pod_kill", "status": "eligible"},
                    ],
                }

        calls: list[str] = []

        def fake_run_closed_loop(**kwargs):
            calls.append(str(kwargs["candidate_id"]))
            output = Path(kwargs["output_root"])
            output.mkdir(parents=True, exist_ok=True)
            (output / "cleanup_report.json").write_text(json.dumps({"status": "verified"}), encoding="utf-8")
            return {"status": "environment_blocked"}

        monkeypatch.setattr(batch_module, "run_closed_loop", fake_run_closed_loop)
        output = root / "batch"
        result = run_live_batch(
            profile_path=profile_path,
            output_root=output,
            live_adapter=Adapter(),
            policy_mode="guarded",
            policy_budget=1,
            policy_context={"boundary_candidate_ids": ["candidate-b"]},
        )

        assert result["status"] == "environment_blocked"
        assert calls == ["candidate-b"]
        selection = json.loads((output / "policy-selection.json").read_text(encoding="utf-8"))
        assert selection["execution_candidate_ids"] == ["candidate-b"]
        assert selection["fallback_used"] is False
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_run_live_batch_guarded_reselects_after_each_feedback(monkeypatch):
    root = Path.cwd() / f".pytest-tmp-batch-policy-rounds-{uuid4().hex}"
    try:
        profile_path = root / "profile.json"
        profile_path.parent.mkdir(parents=True)
        profile_path.write_text(
            json.dumps({
                "project_id": "sock-shop",
                "project_commit": "a" * 40,
                "namespace": "sock-shop-lab",
                "business_oracles": [{"service": "front-end", "remote_port": 80}],
            }),
            encoding="utf-8",
        )

        class Adapter:
            def inventory(self, profile=None):
                return {"project_id": "sock-shop", "project_commit": "a" * 40, "namespace": "sock-shop-lab", "inventory_sha256": "inventory-hash"}

            def detect_server_deployment(self, inventory):
                return {"status": "verified"}

            def map_test_nodes(self, detection):
                return {
                    "status": "verified",
                    "candidates": [
                        {"candidate_id": "candidate-a", "target": "front-end", "target_kind": "deployment", "fault_family": "pod_kill", "status": "eligible", "canonical_signature": "sig-a"},
                        {"candidate_id": "candidate-b", "target": "front-end", "target_kind": "deployment", "fault_family": "pod_kill", "status": "eligible", "canonical_signature": "sig-b"},
                    ],
                }

        calls: list[str] = []

        def fake_run_closed_loop(**kwargs):
            candidate_id = str(kwargs["candidate_id"])
            calls.append(candidate_id)
            output = Path(kwargs["output_root"])
            output.mkdir(parents=True, exist_ok=True)
            (output / "cleanup_report.json").write_text(json.dumps({"status": "verified"}), encoding="utf-8")
            return {
                "status": "live_completed",
                "classification": "availability_degraded",
                "rca_status": "confirmed",
                "evidence_quality": "complete",
                "project_id": "sock-shop",
                "project_commit": "a" * 40,
                "canonical_signature": f"sig-{candidate_id[-1]}",
            }

        monkeypatch.setattr(batch_module, "run_closed_loop", fake_run_closed_loop)
        output = root / "batch"
        result = run_live_batch(
            profile_path=profile_path,
            output_root=output,
            live_adapter=Adapter(),
            policy_mode="guarded",
            policy_budget=1,
            max_candidates=2,
            approve_live=True,
        )

        assert result["status"] == "completed"
        assert calls == ["candidate-a", "candidate-b"]
        assert result["policy_feedback_count"] == 2
        policy_state = json.loads((output / "policy-state.json").read_text(encoding="utf-8"))
        assert policy_state["candidate_states"]["candidate-a"]["run_count"] == 1
        assert policy_state["candidate_states"]["candidate-b"]["run_count"] == 1
        decisions = (output / "policy-decisions.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(decisions) == 3
        assert json.loads(decisions[-1])["stop_reason"] == "blocked"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_run_live_batch_guarded_stop_does_not_call_executor(monkeypatch):
    root = Path.cwd() / f".pytest-tmp-batch-policy-stop-{uuid4().hex}"
    try:
        profile_path = root / "profile.json"
        profile_path.parent.mkdir(parents=True)
        profile_path.write_text(
            json.dumps({
                "project_id": "sock-shop",
                "project_commit": "a" * 40,
                "namespace": "sock-shop-lab",
                "business_oracles": [{"service": "front-end", "remote_port": 80}],
            }),
            encoding="utf-8",
        )

        class Adapter:
            def inventory(self, profile=None):
                return {"project_id": "sock-shop", "project_commit": "a" * 40, "namespace": "sock-shop-lab", "inventory_sha256": "inventory-hash"}

            def detect_server_deployment(self, inventory):
                return {"status": "verified"}

            def map_test_nodes(self, detection):
                return {"status": "verified", "candidates": [{"candidate_id": "candidate-a", "target": "front-end", "status": "blocked", "canonical_signature": "sig-a"}]}

        calls: list[str] = []
        monkeypatch.setattr(batch_module, "run_closed_loop", lambda **kwargs: calls.append(str(kwargs["candidate_id"])) or {"status": "live_completed"})
        output = root / "batch"
        result = run_live_batch(profile_path=profile_path, output_root=output, live_adapter=Adapter(), policy_mode="guarded", approve_live=True)

        assert calls == []
        assert result["policy_stop_reason"] == "blocked"
        assert json.loads((output / "policy-decisions.jsonl").read_text(encoding="utf-8").splitlines()[0])["candidate_id"] is None
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_registry_signal_shadow_records_registry_choice_but_executes_legacy(monkeypatch):
    root = Path.cwd() / f".pytest-tmp-batch-registry-shadow-{uuid4().hex}"
    try:
        profile_path = root / "profile.json"
        profile_path.parent.mkdir(parents=True)
        profile_path.write_text(json.dumps({
            "project_id": "sock-shop",
            "project_commit": "a" * 40,
            "namespace": "sock-shop-lab",
            "business_oracles": [{"service": "front-end", "remote_port": 80}],
        }), encoding="utf-8")

        class Adapter:
            def inventory(self, profile=None):
                return {"project_id": "sock-shop", "project_commit": "a" * 40, "namespace": "sock-shop-lab"}

            def detect_server_deployment(self, inventory):
                return {"status": "verified"}

            def map_test_nodes(self, detection):
                return {"status": "verified", "candidates": [
                    {"candidate_id": "candidate-a", "target": "front-end", "fault_family": "pod_kill"},
                    {"candidate_id": "candidate-b", "target": "front-end", "fault_family": "pod_kill"},
                ]}

        monkeypatch.setattr(batch_module, "_build_registry_signal", lambda plan, pool: {
            "status": "ready", "input_sha256": "r" * 64, "bonus_cap": 0.25,
            "allowed_candidate_ids": ["candidate-b", "candidate-a"],
            "priority_bonus": {"candidate-b": 0.25, "candidate-a": 0.0},
            "fallback_reason": None,
        })
        calls = []

        def fake_run_closed_loop(**kwargs):
            calls.append(str(kwargs["candidate_id"]))
            output = Path(kwargs["output_root"])
            output.mkdir(parents=True, exist_ok=True)
            (output / "cleanup_report.json").write_text(json.dumps({"status": "verified"}), encoding="utf-8")
            return {"status": "environment_blocked"}

        monkeypatch.setattr(batch_module, "run_closed_loop", fake_run_closed_loop)
        output = root / "batch"
        result = run_live_batch(profile_path=profile_path, output_root=output, live_adapter=Adapter(), policy_mode="shadow", policy_budget=1)

        assert result["status"] == "environment_blocked"
        assert calls == ["candidate-a"]
        registry_decision = json.loads((output / "registry-policy-decisions.jsonl").read_text(encoding="utf-8").splitlines()[0])
        assert registry_decision["registry_signal_status"] == "ready"
        assert registry_decision["registry_selected_candidate_ids"] == ["candidate-b"]
        assert registry_decision["execution_candidate_ids"] == ["candidate-a"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_registry_signal_guarded_executes_registry_selected_candidate(monkeypatch):
    root = Path.cwd() / f".pytest-tmp-batch-registry-guarded-{uuid4().hex}"
    try:
        profile_path = root / "profile.json"
        profile_path.parent.mkdir(parents=True)
        profile_path.write_text(json.dumps({
            "project_id": "sock-shop",
            "project_commit": "a" * 40,
            "namespace": "sock-shop-lab",
            "business_oracles": [{"service": "front-end", "remote_port": 80}],
        }), encoding="utf-8")

        class Adapter:
            def inventory(self, profile=None):
                return {"project_id": "sock-shop", "project_commit": "a" * 40, "namespace": "sock-shop-lab"}

            def detect_server_deployment(self, inventory):
                return {"status": "verified"}

            def map_test_nodes(self, detection):
                return {"status": "verified", "candidates": [
                    {"candidate_id": "candidate-a", "target": "front-end", "fault_family": "pod_kill"},
                    {"candidate_id": "candidate-b", "target": "front-end", "fault_family": "pod_kill"},
                ]}

        monkeypatch.setattr(batch_module, "_build_registry_signal", lambda plan, pool: {
            "status": "ready", "input_sha256": "g" * 64, "bonus_cap": 0.25,
            "allowed_candidate_ids": ["candidate-b", "candidate-a"],
            "priority_bonus": {"candidate-b": 0.25, "candidate-a": 0.0},
            "fallback_reason": None,
        })
        calls = []

        def fake_run_closed_loop(**kwargs):
            calls.append(str(kwargs["candidate_id"]))
            output = Path(kwargs["output_root"])
            output.mkdir(parents=True, exist_ok=True)
            (output / "cleanup_report.json").write_text(json.dumps({"status": "verified"}), encoding="utf-8")
            return {"status": "environment_blocked"}

        monkeypatch.setattr(batch_module, "run_closed_loop", fake_run_closed_loop)
        output = root / "batch"
        result = run_live_batch(profile_path=profile_path, output_root=output, live_adapter=Adapter(), policy_mode="guarded", policy_budget=1)

        assert result["status"] == "environment_blocked"
        assert calls == ["candidate-b"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_run_live_batch_promotes_complete_runs_when_knowledge_write_is_explicit(monkeypatch):
    root = Path.cwd() / f".pytest-tmp-batch-knowledge-{uuid4().hex}"
    try:
        profile_path = root / "profile.json"
        profile_path.parent.mkdir(parents=True)
        profile_path.write_text(
            json.dumps({
                "project_id": "sock-shop",
                "project_commit": "a" * 40,
                "namespace": "sock-shop-lab",
                "business_oracles": [{"service": "front-end", "remote_port": 80}],
            }),
            encoding="utf-8",
        )

        class Adapter:
            def inventory(self, profile=None):
                return {"project_id": "sock-shop", "project_commit": "a" * 40, "namespace": "sock-shop-lab"}

            def detect_server_deployment(self, inventory):
                return {"status": "verified"}

            def map_test_nodes(self, detection):
                return {
                    "status": "verified",
                    "candidates": [
                        {"candidate_id": "candidate-a", "target": "front-end"},
                        {"candidate_id": "candidate-b", "target": "front-end"},
                    ],
                }

        calls = []

        def fake_run_closed_loop(**kwargs):
            calls.append(str(kwargs["candidate_id"]))
            output = Path(kwargs["output_root"])
            output.mkdir(parents=True, exist_ok=True)
            (output / "cleanup_report.json").write_text(json.dumps({"status": "verified"}), encoding="utf-8")
            return {"status": "live_completed", "classification": "availability_degraded", "rca_status": "confirmed"}

        promotion_calls = []

        def fake_promote_from_history(*, history_root, output_root, knowledge_write_root):
            promotion_calls.append((Path(history_root), Path(output_root), Path(knowledge_write_root)))
            return {"status": "promoted", "knowledge_status": "local_reusable", "card_id": "KB-1"}

        monkeypatch.setattr(batch_module, "run_closed_loop", fake_run_closed_loop)
        monkeypatch.setattr(batch_module, "promote_from_history", fake_promote_from_history, raising=False)
        output = root / "batch"
        knowledge = root / "knowledge"
        result = run_live_batch(
            profile_path=profile_path,
            output_root=output,
            live_adapter=Adapter(),
            max_candidates=2,
            approve_live=True,
            knowledge_write_root=knowledge,
        )

        assert calls == ["candidate-a", "candidate-b"]
        assert len(promotion_calls) == 1
        history_root, promotion_root, write_root = promotion_calls[0]
        assert history_root == output / "runs"
        assert promotion_root == output / "knowledge-promotion"
        assert write_root == knowledge
        assert result["formal_knowledge_base_updated"] is True
        assert result["knowledge_promotion_status"] == "promoted"
        promotion = json.loads((output / "knowledge_promotion.json").read_text(encoding="utf-8"))
        assert promotion["status"] == "promoted"
    finally:
        shutil.rmtree(root, ignore_errors=True)
