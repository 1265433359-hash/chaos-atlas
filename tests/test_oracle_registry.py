import pytest

from chaosatlas.oracles import (
    OracleRegistry,
    ProbeWorkflowOracle,
    TransactionOracleDependencies,
    build_default_oracle_registry,
)
from chaosatlas.orchestration.engine import RunEngine, RunRequest, _runtime_oracle
from test_transaction_v3_session import Runtime, Transport, frozen


def test_builtin_http_oracle_uses_workflow_contract():
    registry = build_default_oracle_registry()
    calls = []

    def probe(phase, context):
        calls.append((phase, context))
        return {"status": "pass", "samples": []}

    oracle = registry.create(
        {"kind": "http"},
        namespace="test-lab",
        default_probe=probe,
    )

    assert oracle.prepare_fixture({})["status"] == "not_required"
    assert oracle.probe("baseline", {"manifest": "x"})["status"] == "pass"
    assert oracle.collect_evidence({})["status"] == "collected"
    assert oracle.cleanup_fixture({})["cleanup_confirmed"] is True
    assert calls == [("baseline", {"manifest": "x"})]


def test_project_workflow_can_be_registered_without_engine_branch():
    registry = OracleRegistry()
    registry.register(
        "immich_asset_roundtrip",
        lambda _contract, _runtime: ProbeWorkflowOracle(
            lambda phase, _context: {"status": "pass", "phase": phase},
            "immich_asset_roundtrip",
        ),
    )
    profile = {
        "business_oracles": [{
            "kind": "immich_asset_roundtrip",
            "service": "immich-server",
            "remote_port": 2283,
            "entrypoint": "/api/assets",
            "success_contract": "asset_create_read_delete",
        }]
    }

    contract = _runtime_oracle(profile, oracle_registry=registry)
    oracle = registry.create(contract, namespace="chaosatlas-immich", default_probe=lambda *_: {})

    assert contract["kind"] == "immich_asset_roundtrip"
    assert oracle.probe("observe", {})["oracle_kind"] == "immich_asset_roundtrip"


def test_registry_rejects_unknown_oracle_kind():
    registry = build_default_oracle_registry()

    try:
        registry.create({"kind": "unknown"}, namespace="test-lab")
    except ValueError as exc:
        assert "does not support unknown" in str(exc)
    else:
        raise AssertionError("unknown oracle kind was accepted")


def test_registered_transaction_oracle_requires_explicit_dependencies(tmp_path):
    registry = build_default_oracle_registry()
    assert registry.supports("transaction_http")

    with pytest.raises(ValueError, match="lease-bound dependencies"):
        registry.create(
            {"kind": "transaction_http"}, namespace="test-lab",
        )

    runtime = Runtime()
    transport = Transport()
    runtime.open = lambda: transport
    workflow = registry.create(
        {"kind": "transaction_http"}, namespace="test-lab",
        transaction_dependencies=TransactionOracleDependencies(
            runtime=runtime,
            contract=frozen(),
            fixtures={},
            credential_headers=lambda _reference: {},
            ledger_root=tmp_path,
            journal=lambda _event: None,
            synthetic_test_only=True,
        ),
    )

    assert workflow.replayer.transport is transport


def test_single_live_run_uses_shared_candidate_loop_with_budget_one(monkeypatch, tmp_path):
    captured = {}

    def fake_batch(**kwargs):
        captured.update(kwargs)
        return {"status": "completed"}

    monkeypatch.setattr("chaosatlas.orchestration.batch.run_live_batch", fake_batch)

    result = RunEngine().run(RunRequest(
        profile_path=tmp_path / "profile.json",
        output_root=tmp_path / "out",
        mode="live",
        approve_live=True,
        candidate_id="candidate-1",
    ))

    assert result["status"] == "completed"
    assert captured["candidate_ids"] == ["candidate-1"]
    assert captured["max_candidates"] == 1
    assert callable(captured["candidate_runner"])
