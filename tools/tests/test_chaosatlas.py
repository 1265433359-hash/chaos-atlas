from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.chaosatlas import _bounded_artifact_path, _classify_live_outcome, _collect_live_evidence, _live_defense_evidence, _live_lifecycle_evidence, _live_rca_projection, _live_scenario, _runtime_oracle, main, run_closed_loop
from tools.chaosatlas_batch import build_live_batch_plan, run_live_batch
from tools.compile_scenario_node import compile_scenario
from tools.chaosatlas_adapters import OfflineProjectAdapter
from tools.chaosatlas_contracts import STAGES


REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE = REPO_ROOT / "artifacts" / "project_profiles" / "sock-shop" / "project_profile.json"


def test_bounded_artifact_path_shortens_long_windows_filename() -> None:
    root = Path("C:/Users/23741/Desktop/XIAO/ChaosAtlas/") / ("r" * 170)

    path = _bounded_artifact_path(root, "knowledge_drafts", "KB-RCA-opentelemetry-demo-checkout-network-partition-intent")

    assert path.name.startswith("artifact-")
    assert len(str(path)) < 260


def test_runtime_oracle_carries_bounded_observation_window() -> None:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    profile["business_oracles"][0].update(
        {"service": "front-end", "remote_port": 80, "observation_window_s": 60, "probe_retry_interval_s": 2}
    )

    oracle = _runtime_oracle(profile)

    assert oracle["observation_window_s"] == 60.0
    assert oracle["probe_retry_interval_s"] == 2.0


def test_runtime_oracle_accepts_http_body_contract_and_headers() -> None:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    profile["business_oracles"][0].update(
        {
            "success_contract": "http_200_and_expected_body",
            "request_headers": {"Host": "nginx-fixture.local"},
            "expected_body": "chaosatlas-nginx-ingress-fixture",
        }
    )

    oracle = _runtime_oracle(profile)

    assert oracle["expected_status"] == 200
    assert oracle["request_headers"] == {"Host": "nginx-fixture.local"}
    assert oracle["expected_body"] == "chaosatlas-nginx-ingress-fixture"


def test_runtime_oracle_accepts_explicit_grpc_contract() -> None:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    profile["business_oracles"][0].update(
        {
            "kind": "grpc",
            "service": "checkout",
            "remote_port": 5050,
            "entrypoint": "/oteldemo.CheckoutService/PlaceOrder",
            "success_contract": "grpc_place_order_order_id_and_shipping_tracking_id",
            "client": "artifacts/opentelemetry-demo/otel_client.py",
            "supporting_services": [{"service": "cart", "remote_port": 7070}],
        }
    )

    oracle = _runtime_oracle(profile)

    assert oracle["kind"] == "grpc"
    assert oracle["client"].endswith("otel_client.py")
    assert oracle["supporting_services"][0]["service"] == "cart"


def test_live_classification_distinguishes_transient_degradation() -> None:
    assert _classify_live_outcome("executed", True, "business_unreachable") == "business_not_reachable"
    assert _classify_live_outcome("executed", True, "degraded") == "availability_degraded"
    assert _classify_live_outcome("executed", True, "observed") == "response_observed"


def test_live_redundancy_evidence_promotes_preserved_response_to_defense_claim() -> None:
    fault = {
        "kind": "pod_kill",
        "observation": {"status": "pass", "samples": [{"status_code": 200}]},
        "recovery": {"confirmed": True, "state": {"pre_kill_uids": ["old-1", "old-2"], "ready_uids": ["new-1", "old-2"]}},
        "cleanup": {"confirmed": True},
        "attestation": {
            "baseline": True,
            "injection": True,
            "observation": True,
            "recovery": True,
            "cleanup": True,
            "independent_oracle": True,
            "valid": True,
        },
    }
    defense = _live_defense_evidence(fault, observation_window_s=60)

    assert defense["claim_type"] == "redundancy"
    assert _classify_live_outcome("executed", True, "observed", defense) == "availability_defended"


def test_dry_run_executes_correct_stage_order_and_writes_all_artifacts(tmp_path: Path) -> None:
    output = tmp_path / "run"

    result = run_closed_loop(profile_path=PROFILE, output_root=output, mode="dry-run", seed=1001)

    assert result["status"] == "dry_run_ready"
    assert result["completed_stages"] == list(STAGES)
    promotion = json.loads((output / "promote_defense.json").read_text(encoding="utf-8"))
    assert promotion["payload"]["status"] == "not_run"
    for name in (
        "inventory.json",
        "server_deployment_detection.json",
        "candidate_space.json",
        "retrieval.json",
        "project_portrait.json",
        "hypothesis_registry.json",
        "knowledge_consumption.json",
        "hypotheses.json",
        "finding_report.json",
        "rca_report.json",
        "knowledge_draft.json",
        "regression_intents.json",
        "cleanup_report.json",
        "summary.md",
        "checkpoint.json",
    ):
        assert (output / name).is_file(), name

    portrait = json.loads((output / "project_portrait.json").read_text(encoding="utf-8"))
    registry = json.loads((output / "hypothesis_registry.json").read_text(encoding="utf-8"))
    assert portrait["claim_scope"] == "advisory"
    assert registry["claim_scope"] == "advisory"
    assert registry["payload"]["hypothesis_count"] > 1
    assert registry["payload"]["execution_eligible_count"] == registry["payload"]["counts"]["runtime"]
    assert registry["payload"]["hypothesis_count"] > 1  # policy budget remains bounded separately
    assert not (output / "registry_quality_report.json").exists()
    assert not (output / "registry_policy_shadow.json").exists()


def test_registry_shadow_dry_run_writes_advisory_reports_without_side_effects(tmp_path: Path) -> None:
    output = tmp_path / "registry-shadow"

    result = run_closed_loop(profile_path=PROFILE, output_root=output, mode="dry-run", seed=1001, registry_shadow=True)

    assert result["status"] == "dry_run_ready"
    quality = json.loads((output / "registry_quality_report.json").read_text(encoding="utf-8"))
    shadow = json.loads((output / "registry_policy_shadow.json").read_text(encoding="utf-8"))
    assert quality["claim_scope"] == "advisory"
    assert shadow["claim_scope"] == "advisory"
    assert shadow["payload"]["execution_budget"] == 1
    assert shadow["payload"]["mutation_executed"] is False
    assert shadow["payload"]["policy_state_updated"] is False
    assert shadow["payload"]["formal_knowledge_written"] is False
    assert shadow["payload"]["static_hypothesis_count"] > 0


def test_dry_run_writes_phase6_contract_index_and_audit(tmp_path: Path) -> None:
    output = tmp_path / "run"

    result = run_closed_loop(profile_path=PROFILE, output_root=output, mode="dry-run", seed=1001)

    assert result["status"] == "dry_run_ready"
    contract = json.loads((output / "execution_contract.json").read_text(encoding="utf-8"))
    assert contract["mode"] == "dry-run"
    assert contract["budget"]["max_candidates"] == 1
    index = json.loads((output / "artifact_index.json").read_text(encoding="utf-8"))
    assert index["artifacts"]
    assert any(item["path"] == "run_manifest.json" for item in index["artifacts"])
    audit = json.loads((output / "phase6_audit.json").read_text(encoding="utf-8"))
    assert audit["status"] == "dry_run_ready"
    assert audit["knowledge_base_updated"] is False
    assert audit["cleanup"]["status"] == "verified"


def test_dry_run_writes_deterministic_evidence_plan(tmp_path: Path) -> None:
    output = tmp_path / "run"

    result = run_closed_loop(profile_path=PROFILE, output_root=output, mode="dry-run")

    assert result["status"] == "dry_run_ready"
    plan = json.loads((output / "evidence_plan.json").read_text(encoding="utf-8"))["payload"]
    assert plan["status"] == "planned"
    assert plan["selection"]["candidate_budget"] == 1
    assert plan["actions"]
    index = json.loads((output / "artifact_index.json").read_text(encoding="utf-8"))
    assert any(item["path"] == "evidence_plan.json" for item in index["artifacts"])


def test_run_manifest_records_explicit_kube_context(tmp_path: Path) -> None:
    output = tmp_path / "run"

    result = run_closed_loop(
        profile_path=PROFILE,
        output_root=output,
        mode="dry-run",
        kube_context="minikube",
    )

    assert result["status"] == "dry_run_ready"
    manifest = json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["kube_context"] == "minikube"


def test_live_preflight_block_writes_phase6_audit_without_executor(tmp_path: Path) -> None:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    profile["business_oracles"][0].update({"service": "front-end", "remote_port": 80})
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    fixture = OfflineProjectAdapter(
        REPO_ROOT / "tools" / "tests" / "fixtures" / "chaosatlas_offline" / "sock-shop" / "project_facts.json",
        workspace_root=REPO_ROOT,
    )
    calls: list[object] = []

    class FixtureLiveAdapter:
        def inventory(self):
            return fixture.inventory(profile)

        def detect_server_deployment(self, inventory):
            return fixture.detect_server_deployment(inventory)

        def map_test_nodes(self, detection):
            return fixture.map_test_nodes(detection)

    class BlockedPreflight:
        def run(self):
            return {"status": "environment_blocked", "checks": {}, "errors": ["residual chaos"], "read_only": True}

    def executor(*args):
        calls.append(args)
        return {"status": "executed"}

    output = tmp_path / "run"
    result = run_closed_loop(
        profile_path=profile_path,
        output_root=output,
        mode="live",
        live_adapter=FixtureLiveAdapter(),
        live_preflight=BlockedPreflight(),
        live_executor=executor,
    )

    assert result["status"] == "environment_blocked"
    assert calls == []
    audit = json.loads((output / "phase6_audit.json").read_text(encoding="utf-8"))
    assert audit["status"] == "environment_blocked"
    assert audit["execution_contract"]["mode"] == "live"
    assert audit["knowledge_base_updated"] is False


def test_live_blocked_evidence_plan_stops_before_executor(tmp_path: Path) -> None:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    profile["business_oracles"][0].update({"service": "front-end", "remote_port": 80})
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    fixture = OfflineProjectAdapter(
        REPO_ROOT / "tools" / "tests" / "fixtures" / "chaosatlas_offline" / "sock-shop" / "project_facts.json",
        workspace_root=REPO_ROOT,
    )
    calls: list[object] = []

    class FixtureLiveAdapter:
        def inventory(self):
            return fixture.inventory(profile)

        def detect_server_deployment(self, inventory):
            return fixture.detect_server_deployment(inventory)

        def map_test_nodes(self, detection):
            result = fixture.map_test_nodes(detection)
            result["candidates"][0]["recovery_contract"] = {}
            return result

    class ReadyPreflight:
        def run(self):
            return {"status": "ready_for_injection", "checks": {}, "read_only": True}

    def executor(*args):
        calls.append(args)
        return {"status": "executed"}

    output = tmp_path / "run"
    result = run_closed_loop(
        profile_path=profile_path,
        output_root=output,
        mode="live",
        approve_live=True,
        live_adapter=FixtureLiveAdapter(),
        live_preflight=ReadyPreflight(),
        live_executor=executor,
    )

    assert result["status"] == "environment_blocked"
    assert calls == []
    plan = json.loads((output / "evidence_plan.json").read_text(encoding="utf-8"))["payload"]
    assert plan["status"] == "blocked"
    audit = json.loads((output / "phase6_audit.json").read_text(encoding="utf-8"))
    assert audit["status"] == "environment_blocked"


def test_dry_run_knowledge_root_is_read_only(tmp_path: Path) -> None:
    output = tmp_path / "run"
    knowledge_root = tmp_path / "knowledge-read"
    knowledge_root.mkdir()
    marker = knowledge_root / "marker.json"
    marker.write_text("{}\n", encoding="utf-8")

    run_closed_loop(profile_path=PROFILE, output_root=output, mode="dry-run", knowledge_root=knowledge_root)

    assert marker.read_text(encoding="utf-8") == "{}\n"
    assert not (knowledge_root / "defense_card.json").exists()


def test_hypotheses_record_deterministic_advisory_fallback(tmp_path: Path) -> None:
    output = tmp_path / "run"

    run_closed_loop(profile_path=PROFILE, output_root=output, mode="dry-run")

    hypotheses = json.loads((output / "hypotheses.json").read_text(encoding="utf-8"))["payload"]
    assert hypotheses["advisory_status"] == "deterministic_fallback"


def test_advisory_provider_can_only_reference_known_candidates(tmp_path: Path) -> None:
    output = tmp_path / "run"

    def provider(payload: dict) -> dict:
        candidate_id = payload["candidate_space"]["candidates"][0]["candidate_id"]
        return {
            "hypotheses": [{
                "candidate_id": candidate_id,
                "mechanism": "bounded deployment hypothesis",
                "expected_observations": ["business oracle"],
                "missing_evidence": ["mechanism evidence"],
                "next_actions": ["collect scoped logs"],
            }],
            "global_missing_evidence": ["mechanism evidence"],
        }

    run_closed_loop(
        profile_path=PROFILE,
        output_root=output,
        mode="dry-run",
        advisory_provider=provider,
    )

    hypotheses = json.loads((output / "hypotheses.json").read_text(encoding="utf-8"))["payload"]
    assert hypotheses["advisory_status"] == "completed"
    assert hypotheses["advisory"]["hypotheses"][0]["candidate_id"] in hypotheses["candidate_ids"]


def test_cli_explicit_deepseek_advisory_provider_is_used_only_when_selected(tmp_path: Path, monkeypatch) -> None:
    class FakeProvider:
        def __call__(self, payload: dict) -> dict:
            candidate_id = payload["candidate_space"]["candidates"][0]["candidate_id"]
            return {
                "hypotheses": [{
                    "candidate_id": candidate_id,
                    "mechanism": "bounded model advisory",
                    "expected_observations": ["business oracle evidence"],
                    "missing_evidence": ["runtime evidence"],
                    "next_actions": ["collect scoped events"],
                }],
                "global_missing_evidence": [],
                "advisory_metadata": {"backend": "test", "model": "deepseek-v4-flash"},
            }

    monkeypatch.setattr(
        "tools.deepseek_advisory.create_deepseek_advisory_provider",
        lambda **kwargs: FakeProvider(),
    )
    output = tmp_path / "run"
    code = main([
        "run",
        "--profile", str(PROFILE),
        "--mode", "dry-run",
        "--output", str(output),
        "--advisory-provider", "deepseek",
        "--api-key-file", str(tmp_path / "unused.key"),
    ])

    assert code == 0
    hypotheses = json.loads((output / "hypotheses.json").read_text(encoding="utf-8"))["payload"]
    assert hypotheses["advisory_status"] == "completed"
    assert hypotheses["advisory"]["advisory_metadata"]["model"] == "deepseek-v4-flash"


def test_cli_forwards_batch_resume_to_live_batch(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_batch(**kwargs):
        captured.update(kwargs)
        return {"status": "completed", "planned_count": 1}

    monkeypatch.setattr("tools.chaosatlas_batch.run_live_batch", fake_batch)
    code = main([
        "run",
        "--profile", str(PROFILE),
        "--mode", "live",
        "--output", str(tmp_path / "batch"),
        "--all-candidates",
        "--resume",
        "--policy-mode", "shadow",
        "--policy-budget", "1",
    ])

    assert code == 0
    assert captured["resume"] is True
    assert captured["policy_mode"] == "shadow"
    assert captured["policy_budget"] == 1


def test_cli_loads_read_only_policy_context_for_batch(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    context_path = tmp_path / "policy-context.json"
    context_path.write_text(json.dumps({"boundary_candidate_ids": ["candidate-b"]}), encoding="utf-8")

    def fake_batch(**kwargs):
        captured.update(kwargs)
        return {"status": "completed", "planned_count": 1}

    monkeypatch.setattr("tools.chaosatlas_batch.run_live_batch", fake_batch)
    code = main([
        "run",
        "--profile", str(PROFILE),
        "--mode", "live",
        "--output", str(tmp_path / "batch"),
        "--all-candidates",
        "--policy-mode", "guarded",
        "--policy-context", str(context_path),
    ])

    assert code == 0
    assert captured["policy_context"] == {"boundary_candidate_ids": ["candidate-b"]}


def test_dry_run_never_emits_runtime_weakness_or_defense_claim(tmp_path: Path) -> None:
    output = tmp_path / "run"
    run_closed_loop(profile_path=PROFILE, output_root=output, mode="dry-run")

    text = "\n".join(path.read_text(encoding="utf-8") for path in output.glob("*.json"))
    assert '"weakness_status": "confirmed"' not in text
    assert '"result": "weakness"' not in text
    assert '"result": "defended"' not in text
    assert '"rca_status": "confirmed"' not in text


def test_invalid_profile_stops_before_inventory(tmp_path: Path) -> None:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    profile["namespace_policy"]["allowed_namespaces"] = ["default"]
    bad_profile = tmp_path / "bad.json"
    bad_profile.write_text(json.dumps(profile), encoding="utf-8")

    result = run_closed_loop(profile_path=bad_profile, output_root=tmp_path / "run", mode="dry-run")

    assert result["status"] == "method_invalid"
    assert not (tmp_path / "run" / "inventory.json").exists()


def test_resume_skips_completed_stages_and_reuses_input_hash(tmp_path: Path) -> None:
    output = tmp_path / "run"
    first = run_closed_loop(profile_path=PROFILE, output_root=output, mode="dry-run")
    second = run_closed_loop(profile_path=PROFILE, output_root=output, mode="dry-run", resume=True)

    assert second["status"] == "dry_run_ready"
    assert first["input_snapshot_sha256"] == second["input_snapshot_sha256"]
    assert second["resumed"] is True


def test_non_empty_output_is_rejected_without_overwriting_files(tmp_path: Path) -> None:
    output = tmp_path / "run"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("preserve", encoding="utf-8")

    with pytest.raises(FileExistsError):
        run_closed_loop(profile_path=PROFILE, output_root=output, mode="dry-run")

    assert marker.read_text(encoding="utf-8") == "preserve"


def test_live_mode_requires_runtime_business_oracle(tmp_path: Path) -> None:
    output = tmp_path / "run"
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    profile["business_oracles"][0].pop("service", None)
    profile["business_oracles"][0].pop("remote_port", None)
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")

    result = run_closed_loop(profile_path=profile_path, output_root=output, mode="live")

    assert result["status"] == "environment_blocked"
    assert "service" in str(result["error"])
    assert not (output / "execute.json").exists()


def test_live_mode_runs_selected_candidate_through_injected_executor(tmp_path: Path) -> None:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    profile["business_oracles"][0].update({"service": "front-end", "remote_port": 80})
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    output = tmp_path / "run"

    fixture = OfflineProjectAdapter(
        REPO_ROOT / "tools" / "tests" / "fixtures" / "chaosatlas_offline" / "sock-shop" / "project_facts.json",
        workspace_root=REPO_ROOT,
    )

    class FixtureLiveAdapter:
        def inventory(self):
            return fixture.inventory(profile)

        def detect_server_deployment(self, inventory):
            return fixture.detect_server_deployment(inventory)

        def map_test_nodes(self, detection):
            return fixture.map_test_nodes(detection)

    class FixtureEvidenceCollector:
        def collect_events(self, **kwargs):
            return {"source_ref": "runtime/events.json", "evidence_id": kwargs["evidence_id"], "polarity": "supports", "claim_scope": kwargs["claim_scope"]}

        def collect_logs(self, **kwargs):
            return {"source_ref": "runtime/logs.log", "evidence_id": kwargs["evidence_id"], "polarity": "supports", "claim_scope": kwargs["claim_scope"]}

    class FixturePreflight:
        def run(self):
            return {"status": "ready_for_injection", "checks": {}, "errors": [], "read_only": True}

    def executor(manifest, phase, fault):
        return {
            "status": "executed",
            "injection_confirmed": True,
            "injected_count": 1,
            "cleanup_confirmed": True,
            "observation": {"status": "business_unreachable", "samples": []},
            "attestation": {
                "valid": False,
                "comparison_eligible": False,
                "baseline": True,
                "injection": True,
                "observation": False,
                "recovery": True,
                "cleanup": True,
            },
        }

    result = run_closed_loop(
        profile_path=profile_path,
        output_root=output,
        mode="live",
        live_executor=executor,
        live_adapter=FixtureLiveAdapter(),
        live_evidence_collector=FixtureEvidenceCollector(),
        live_preflight=FixturePreflight(),
    )

    assert result["status"] == "live_completed"
    execution = json.loads((output / "execute.json").read_text(encoding="utf-8"))
    assert execution["payload"]["phases"][0]["faults"][0]["injection_confirmed"] is True
    evidence = json.loads((output / "evidence_refs.json").read_text(encoding="utf-8"))
    assert len(evidence["records"]) >= 3
    assert any(item.get("kind") == "business_path_replay" for item in evidence["records"])
    assert evidence["planned_action_ids"]
    assert any(item.get("planned_action_id") == "server:deployment:sock-shop:front-end:pod_kill:pod_events" for item in evidence["records"])
    rca = json.loads((output / "rca_report.json").read_text(encoding="utf-8"))
    assert rca["payload"]["rca_status"] == "pending"
    knowledge = json.loads((output / "knowledge_draft.json").read_text(encoding="utf-8"))
    assert knowledge["payload"]["knowledge_status"] == "none"
    assert knowledge["payload"]["promotion_allowed"] is False
    assert json.loads((output / "cleanup_report.json").read_text(encoding="utf-8"))["mode"] == "live"


def test_live_complete_lifecycle_projects_bounded_rca_and_provisional_knowledge(tmp_path: Path) -> None:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    profile["business_oracles"][0].update({"service": "front-end", "remote_port": 80})
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    fixture = OfflineProjectAdapter(
        REPO_ROOT / "tools" / "tests" / "fixtures" / "chaosatlas_offline" / "sock-shop" / "project_facts.json",
        workspace_root=REPO_ROOT,
    )

    class FixtureLiveAdapter:
        def inventory(self):
            return fixture.inventory(profile)

        def detect_server_deployment(self, inventory):
            return fixture.detect_server_deployment(inventory)

        def map_test_nodes(self, detection):
            return fixture.map_test_nodes(detection)

    class FixtureEvidenceCollector:
        def collect_events(self, **kwargs):
            return {"source_ref": "runtime/events.json", "evidence_id": kwargs["evidence_id"], "kind": "kubernetes_event", "polarity": "supports", "claim_scope": kwargs["claim_scope"], "satisfies": ["kubernetes_event_window"]}

        def collect_logs(self, **kwargs):
            return {"source_ref": "runtime/logs.log", "evidence_id": kwargs["evidence_id"], "kind": "runtime_log", "polarity": "supports", "claim_scope": kwargs["claim_scope"], "satisfies": ["runtime_logs_window"]}

    class FixturePreflight:
        def run(self):
            return {"status": "ready_for_injection", "checks": {}, "errors": [], "read_only": True}

    def executor(manifest, phase, fault):
        return {
            "status": "executed",
            "injection_confirmed": True,
            "injected_count": 1,
            "cleanup_confirmed": True,
            "observation": {"status": "pass", "samples": [{"status_code": 200, "latency_ms": 12}]},
            "recovery": {"confirmed": True},
            "cleanup": {"confirmed": True},
            "attestation": {
                "schema_version": "chaosatlas-runtime-result-v1",
                "valid": True,
                "comparison_eligible": True,
                "baseline": True,
                "injection": True,
                "observation": True,
                "recovery": True,
                "cleanup": True,
                "independent_oracle": True,
            },
        }

    output = tmp_path / "run"
    result = run_closed_loop(
        profile_path=profile_path,
        output_root=output,
        mode="live",
        live_executor=executor,
        live_adapter=FixtureLiveAdapter(),
        live_evidence_collector=FixtureEvidenceCollector(),
        live_preflight=FixturePreflight(),
    )

    assert result["status"] == "live_completed"
    rca = json.loads((output / "rca_report.json").read_text(encoding="utf-8"))["payload"]
    assert rca["rca_status"] == "bounded"
    evidence = json.loads((output / "evidence_refs.json").read_text(encoding="utf-8"))["records"]
    assert any("defense_mechanism_evidence" in (item.get("satisfies") or []) for item in evidence)
    assert not any("mechanism_evidence" in (item.get("satisfies") or []) for item in evidence)
    knowledge = json.loads((output / "knowledge_draft.json").read_text(encoding="utf-8"))["payload"]
    assert knowledge["knowledge_status"] == "provisional"
    assert knowledge["promotion_allowed"] is True
    card_path = output / "knowledge_drafts" / f"{knowledge['id']}.json"
    assert card_path.is_file()
    assert json.loads(card_path.read_text(encoding="utf-8"))["knowledge_status"] == "provisional"
    assert (output / "knowledge_drafts" / "regression_intents.json").is_file()
    intents = json.loads((output / "regression_intents.json").read_text(encoding="utf-8"))["payload"]
    assert intents["intents"][0]["kind"] == "discriminate"


@pytest.mark.parametrize(
    ("family", "parameters", "kind"),
    [
        ("pod_kill", {"mode": "one"}, "PodChaos"),
        ("container_kill", {"container": "front-end"}, "PodChaos"),
        ("stress_cpu", {"workers": 1, "load_percent": 80}, "StressChaos"),
        ("stress_memory", {"size_mb": 64}, "StressChaos"),
        ("network_loss", {"loss_percent": 100}, "NetworkChaos"),
        ("network_partition", {}, "NetworkChaos"),
    ],
)
def test_live_scenario_compiles_each_server_fault_family(family: str, parameters: dict, kind: str) -> None:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    profile["business_oracles"][0].update({"service": "front-end", "remote_port": 80})
    fixture = OfflineProjectAdapter(
        REPO_ROOT / "tools" / "tests" / "fixtures" / "chaosatlas_offline" / "sock-shop" / "project_facts.json",
        workspace_root=REPO_ROOT,
    )
    inventory = fixture.inventory(profile)
    candidate = {"target": "front-end", "fault_family": family, "parameters": parameters}
    scenario = _live_scenario(profile=profile, inventory=inventory, candidate=candidate, scenario_id=f"scenario-{family}")
    compiled = compile_scenario(scenario)
    assert compiled["status"] == "verified"
    assert compiled["manifests"][0]["kind"] == kind
    assert compiled["manifests"][0]["spec"]["mode"] == "one"


def test_live_scenario_reads_kubernetes_nested_deployment_shape() -> None:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    inventory = {
        "project_id": "sock-shop",
        "project_commit": "a" * 40,
        "namespace": "sock-shop-lab",
        "deployments": [
            {
                "metadata": {"name": "front-end"},
                "spec": {
                    "replicas": 1,
                    "selector": {"matchLabels": {"name": "front-end"}},
                    "template": {"spec": {"containers": [{"name": "front-end"}]}},
                },
            }
        ],
    }
    scenario = _live_scenario(
        profile=profile,
        inventory=inventory,
        candidate={"target": "front-end", "fault_family": "pod_kill"},
        scenario_id="nested-deployment",
    )
    assert compile_scenario(scenario)["status"] == "verified"


def test_live_batch_isolates_candidate_outputs_and_respects_limit(tmp_path: Path) -> None:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    fixture = OfflineProjectAdapter(
        REPO_ROOT / "tools" / "tests" / "fixtures" / "chaosatlas_offline" / "sock-shop" / "project_facts.json",
        workspace_root=REPO_ROOT,
    )
    calls: list[str] = []

    class FixtureLiveAdapter:
        def inventory(self):
            return fixture.inventory(profile)

        def detect_server_deployment(self, inventory):
            return fixture.detect_server_deployment(inventory)

        def map_test_nodes(self, detection):
            return fixture.map_test_nodes(detection)

    class FixtureEvidenceCollector:
        def collect_events(self, **kwargs):
            return {"source_ref": "runtime/events.json", "evidence_id": kwargs["evidence_id"], "kind": "kubernetes_event", "polarity": "supports", "claim_scope": kwargs["claim_scope"], "satisfies": []}

        def collect_logs(self, **kwargs):
            return {"source_ref": "runtime/logs.log", "evidence_id": kwargs["evidence_id"], "kind": "runtime_log", "polarity": "supports", "claim_scope": kwargs["claim_scope"], "satisfies": []}

    class FixturePreflight:
        def run(self):
            return {"status": "ready_for_injection", "checks": {}, "errors": [], "read_only": True}

    def executor(manifest, phase, fault):
        calls.append(str(fault["kind"]))
        return {
            "status": "executed",
            "injection_confirmed": True,
            "injected_count": 1,
            "cleanup_confirmed": True,
            "observation": {"status": "business_unreachable", "samples": []},
            "attestation": {"valid": False, "comparison_eligible": False, "baseline": True, "injection": True, "observation": False, "recovery": True, "cleanup": True},
        }

    output = tmp_path / "batch"
    result = run_live_batch(
        profile_path=profile_path,
        output_root=output,
        max_candidates=2,
        approve_live=True,
        live_executor=executor,
        live_adapter=FixtureLiveAdapter(),
        live_evidence_collector=FixtureEvidenceCollector(),
        live_preflight=FixturePreflight(),
    )

    assert result["status"] == "completed"
    assert result["planned_count"] == 2
    assert result["completed_count"] == 2
    assert len(calls) == 2
    children = sorted((output / "runs").iterdir())
    assert len(children) == 2
    assert all((child / "rca_report.json").is_file() for child in children)
    assert all(json.loads((child / "knowledge_draft.json").read_text(encoding="utf-8"))["payload"]["knowledge_status"] == "none" for child in children)


def test_live_batch_accepts_profile_aware_offline_adapter() -> None:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    adapter = OfflineProjectAdapter(
        REPO_ROOT / "tools" / "tests" / "fixtures" / "chaosatlas_offline" / "sock-shop" / "project_facts.json",
        workspace_root=REPO_ROOT,
    )

    plan = build_live_batch_plan(profile=profile, adapter=adapter)

    assert plan["status"] == "ready"
    assert plan["candidate_ids"]
    assert all(item["target"] == "front-end" for item in plan["candidates"])


def test_live_batch_forwards_explicit_kube_context_to_each_child(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    profile["business_oracles"][0].update({"service": "front-end", "remote_port": 80})
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    fixture = OfflineProjectAdapter(
        REPO_ROOT / "tools" / "tests" / "fixtures" / "chaosatlas_offline" / "sock-shop" / "project_facts.json",
        workspace_root=REPO_ROOT,
    )
    class BatchAdapter:
        def inventory(self):
            return fixture.inventory(profile)

        def detect_server_deployment(self, inventory):
            return fixture.detect_server_deployment(inventory)

        def map_test_nodes(self, detection):
            return fixture.map_test_nodes(detection)
    captured: list[str | None] = []

    def fake_run_closed_loop(**kwargs):
        captured.append(kwargs.get("kube_context"))
        return {"status": "live_completed", "run_id": "fake"}

    monkeypatch.setattr("tools.chaosatlas_batch.run_closed_loop", fake_run_closed_loop)

    result = run_live_batch(
        profile_path=profile_path,
        output_root=tmp_path / "batch",
        max_candidates=2,
        approve_live=True,
        live_adapter=BatchAdapter(),
        kube_context="minikube",
    )

    assert result["status"] == "completed"
    assert captured == ["minikube", "minikube"]


def test_mechanism_evidence_is_required_for_confirmed_live_rca(tmp_path: Path) -> None:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    fixture = OfflineProjectAdapter(
        REPO_ROOT / "tools" / "tests" / "fixtures" / "chaosatlas_offline" / "sock-shop" / "project_facts.json",
        workspace_root=REPO_ROOT,
    )
    inventory = fixture.inventory(profile)
    candidate = {"candidate_id": "candidate-1", "target": "front-end", "fault_family": "pod_kill", "parameters": {"mode": "one"}}
    fault = {
        "status": "executed",
        "outcome_status": "observed",
        "baseline": {"status": "pass"},
        "observation": {"status": "pass", "samples": [{"status_code": 200}]},
        "recovery": {"confirmed": True},
        "cleanup": {"confirmed": True},
        "attestation": {
            "schema_version": "chaosatlas-runtime-result-v1",
            "valid": True,
            "comparison_eligible": True,
            "baseline": True,
            "injection": True,
            "observation": True,
            "recovery": True,
            "cleanup": True,
            "independent_oracle": True,
        },
        "mechanism_evidence": [{"evidence_id": "mechanism-1", "kind": "runtime_log", "source_ref": "runtime/log.txt", "interpretation": "selected process recorded the injected fault"}],
    }
    mechanism_path = tmp_path / "runtime" / "log.txt"
    mechanism_path.parent.mkdir(parents=True)
    mechanism_path.write_text("selected process recorded the injected fault\n", encoding="utf-8")
    records = _live_lifecycle_evidence(output_root=tmp_path, evidence_prefix="mechanism-test", claim_scope="deployment:front-end", fault=fault)
    updated, _, _ = _live_rca_projection(profile=profile, inventory=inventory, candidate=candidate, fault=fault, evidence_records=records, run_id="mechanism-test")
    assert updated["rca_status"] == "confirmed"


def test_live_evidence_adds_service_boundary_mechanism_record(tmp_path: Path) -> None:
    class Collector:
        def collect_events(self, **kwargs):
            return {
                "source_ref": "runtime/kubernetes/events/mechanism-window-events.json",
                "evidence_id": kwargs["evidence_id"],
                "kind": "kubernetes_event",
                "polarity": "supports",
                "claim_scope": kwargs["claim_scope"],
            }

        def collect_logs(self, **kwargs):
            return {
                "source_ref": "runtime/kubernetes/logs/mechanism-window-logs.log",
                "evidence_id": kwargs["evidence_id"],
                "kind": "runtime_log",
                "polarity": "supports",
                "claim_scope": kwargs["claim_scope"],
            }

    fault = {
        "kind": "pod_kill",
        "target_node_id": "deployment:front-end",
        "baseline": {"status": "pass"},
        "observation": {"status": "degraded", "samples": [{"status_code": None}, {"status_code": 200}]},
        "recovery": {"confirmed": True, "state": {"pre_kill_uids": ["old"], "ready_uids": ["new"]}},
        "cleanup": {"confirmed": True},
        "attestation": {
            "baseline": True,
            "injection": True,
            "observation": True,
            "recovery": True,
            "cleanup": True,
            "valid": True,
            "comparison_eligible": True,
        },
    }

    records = _collect_live_evidence(
        collector=Collector(),
        output_root=tmp_path,
        namespace="sock-shop-lab",
        target="front-end",
        evidence_prefix="mechanism-window",
        claim_scope="deployment:front-end",
        fault=fault,
    )

    mechanism = [item for item in records if "mechanism_evidence" in (item.get("satisfies") or [])]
    assert len(mechanism) == 1
    assert mechanism[0]["kind"] == "recovery"
    assert (tmp_path / mechanism[0]["source_ref"]).is_file()


def test_container_restart_mechanism_evidence_does_not_claim_pod_replacement(tmp_path: Path) -> None:
    class Collector:
        def collect_events(self, **kwargs):
            return {"source_ref": "runtime/events.json", "evidence_id": kwargs["evidence_id"], "kind": "kubernetes_event", "polarity": "supports", "claim_scope": kwargs["claim_scope"]}

        def collect_logs(self, **kwargs):
            return {"source_ref": "runtime/logs.log", "evidence_id": kwargs["evidence_id"], "kind": "runtime_log", "polarity": "supports", "claim_scope": kwargs["claim_scope"]}

    fault = {
        "kind": "container_kill",
        "target_node_id": "deployment:front-end",
        "baseline": {"status": "pass"},
        "observation": {"status": "degraded", "samples": [{"status_code": None}, {"status_code": 200}]},
        "recovery": {
            "confirmed": True,
            "state": {
                "recovery_mode": "container_restart",
                "pre_restart_counts": {"front-end-0": 0},
                "restart_counts": {"front-end-0": 1},
                "restarted_pods": ["front-end-0"],
            },
        },
        "cleanup": {"confirmed": True},
        "attestation": {
            "baseline": True,
            "injection": True,
            "observation": True,
            "recovery": True,
            "cleanup": True,
            "valid": True,
            "comparison_eligible": True,
        },
    }

    records = _collect_live_evidence(
        collector=Collector(),
        output_root=tmp_path,
        namespace="sock-shop-lab",
        target="front-end",
        evidence_prefix="container-restart-mechanism",
        claim_scope="deployment:front-end",
        fault=fault,
    )

    mechanism = next(item for item in records if "mechanism_evidence" in (item.get("satisfies") or []))
    payload = json.loads((tmp_path / mechanism["source_ref"]).read_text(encoding="utf-8"))
    assert payload["recovery_mode"] == "container_restart"
    assert "Pod identity change" not in payload["interpretation"]
    assert "container restart" in payload["interpretation"]


def test_degraded_observation_is_bounded_and_generates_provisional_knowledge(tmp_path: Path) -> None:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    fixture = OfflineProjectAdapter(
        REPO_ROOT / "tools" / "tests" / "fixtures" / "chaosatlas_offline" / "sock-shop" / "project_facts.json",
        workspace_root=REPO_ROOT,
    )
    inventory = fixture.inventory(profile)
    candidate = {"candidate_id": "candidate-degraded", "target": "front-end", "fault_family": "pod_kill", "parameters": {"mode": "one"}}
    fault = {
        "status": "executed",
        "outcome_status": "degraded",
        "baseline": {"status": "pass"},
        "observation": {
            "status": "degraded",
            "samples": [{"status_code": None}, {"status_code": 200}],
        },
        "recovery": {"confirmed": True},
        "cleanup": {"confirmed": True},
        "attestation": {
            "schema_version": "chaosatlas-runtime-result-v1",
            "valid": True,
            "comparison_eligible": True,
            "baseline": True,
            "injection": True,
            "observation": True,
            "recovery": True,
            "cleanup": True,
            "independent_oracle": True,
        },
    }

    records = _live_lifecycle_evidence(
        output_root=tmp_path,
        evidence_prefix="degraded-test",
        claim_scope="deployment:front-end",
        fault=fault,
    )
    updated, ingested, draft = _live_rca_projection(
        profile=profile,
        inventory=inventory,
        candidate=candidate,
        fault=fault,
        evidence_records=records,
        run_id="degraded-test",
    )

    assert any("observation" in (item.get("satisfies") or []) for item in records)
    assert updated["rca_status"] == "bounded"
    assert ingested["promotion"]["allowed"] is True
    assert draft["knowledge_status"] == "provisional"


def test_live_mode_preflight_blocks_before_executor(tmp_path: Path) -> None:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    profile["business_oracles"][0].update({"service": "front-end", "remote_port": 80})
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    fixture = OfflineProjectAdapter(
        REPO_ROOT / "tools" / "tests" / "fixtures" / "chaosatlas_offline" / "sock-shop" / "project_facts.json",
        workspace_root=REPO_ROOT,
    )
    calls = []

    class FixtureLiveAdapter:
        def inventory(self):
            return fixture.inventory(profile)

        def detect_server_deployment(self, inventory):
            return fixture.detect_server_deployment(inventory)

        def map_test_nodes(self, detection):
            return fixture.map_test_nodes(detection)

    class BlockedPreflight:
        def run(self):
            return {"status": "environment_blocked", "checks": {}, "errors": ["residual chaos"], "read_only": True}

    def executor(*args):
        calls.append(args)
        return {"status": "executed"}

    result = run_closed_loop(
        profile_path=profile_path,
        output_root=tmp_path / "run",
        mode="live",
        live_adapter=FixtureLiveAdapter(),
        live_preflight=BlockedPreflight(),
        live_executor=executor,
    )

    assert result["status"] == "environment_blocked"
    assert calls == []
    assert (tmp_path / "run" / "preflight.json").is_file()


@pytest.mark.parametrize(
    "project_id",
    ["sock-shop", "online-boutique", "p02"],
)
def test_offline_replay_uses_one_orchestrator_for_three_projects(tmp_path: Path, project_id: str) -> None:
    profile = (
        REPO_ROOT
        / "tools"
        / "tests"
        / "fixtures"
        / "chaosatlas_offline"
        / project_id
        / "project_profile.json"
    )
    output = tmp_path / project_id

    result = run_closed_loop(profile_path=profile, output_root=output, mode="dry-run")

    assert result["status"] == "dry_run_ready"
    assert result["completed_stages"] == list(STAGES)
    inventory = json.loads((output / "inventory.json").read_text(encoding="utf-8"))
    assert inventory["payload"]["project_id"] == project_id
    assert not any('"result": "weakness"' in path.read_text(encoding="utf-8") for path in output.glob("*.json"))


def test_p02_runtime_profile_uses_exact_case_facts_variant(tmp_path: Path) -> None:
    profile = REPO_ROOT / "artifacts" / "project_profiles" / "p02" / "project_profile.json"

    result = run_closed_loop(profile_path=profile, output_root=tmp_path / "p02-runtime", mode="dry-run")

    assert result["status"] == "dry_run_ready"
    inventory = json.loads((tmp_path / "p02-runtime" / "inventory.json").read_text(encoding="utf-8"))
    assert inventory["payload"]["project_id"] == "P02"
