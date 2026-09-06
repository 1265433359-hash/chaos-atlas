import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from chaosatlas.isolation.lease_store import LeaseStore
from chaosatlas.isolation.manager import IsolationManager
from chaosatlas.isolation.providers import ProviderRegistry
from chaosatlas.oracles import transaction_integration
from chaosatlas.oracles.transaction_integration import (
    LeaseTransactionDependencyFactory,
    bind_transaction_oracle_profile,
    load_approved_contract,
)
from chaosatlas.orchestration.engine import RunEngine, RunRequest


ROOT = Path(__file__).resolve().parents[1]
APPROVAL = ROOT / "projects" / "chaosatlas-apps" / "oracle-approvals" / "87f929e0d52510871fb19d8e8bc40a46f1002dd9ff921d5d26be0579a5648db3"


def test_profile_binding_pins_exact_approved_transaction_contract():
    path = ROOT / "projects" / "chaosatlas-apps" / "immich" / "profile.json"
    profile = json.loads(path.read_text(encoding="utf-8"))

    runtime = bind_transaction_oracle_profile(profile, APPROVAL)
    oracle = runtime["business_oracles"][0]

    assert oracle["kind"] == "transaction_http"
    assert oracle["approved_oracle_id"] == "immich-asset-roundtrip-v3"
    assert oracle["approved_contract_sha256"] == "30c4b6e7ec2b3f845668cc98f7778479654616740c30a7978b398cd10a7b3328"
    assert profile["business_oracles"][0]["kind"] == "http"


def test_approved_contract_loader_rejects_outside_repository(tmp_path):
    with pytest.raises(ValueError, match="inside repository projects"):
        load_approved_contract(tmp_path, "immich")


def test_run_request_requires_isolation_for_approved_transaction_batch(tmp_path):
    with pytest.raises(ValueError, match="requires isolated live mode"):
        RunRequest(
            profile_path=tmp_path / "profile.json",
            output_root=tmp_path / "run",
            mode="live",
            approve_live=True,
            oracle_approval_dir=APPROVAL,
        )


def test_run_engine_routes_transaction_dependencies_through_isolated_batch(monkeypatch, tmp_path):
    profile_path = ROOT / "projects" / "chaosatlas-apps" / "immich" / "profile.json"
    captured = {}
    dependency_factory = object()

    def fake_dependency_factory(**kwargs):
        captured["dependency_factory_args"] = kwargs
        return dependency_factory

    def fake_batch(**kwargs):
        captured["batch"] = kwargs
        runtime = json.loads(Path(kwargs["profile_path"]).read_text(encoding="utf-8"))
        captured["runtime_profile"] = runtime
        return {"status": "completed", "executed_count": 1, "completed_count": 1}

    def fake_isolated(**kwargs):
        profile = json.loads(Path(kwargs["profile_path"]).read_text(encoding="utf-8"))
        transformed = kwargs["profile_transform"](profile)
        runtime_path = tmp_path / "runtime-profile.json"
        runtime_path.write_text(json.dumps(transformed), encoding="utf-8")
        context = SimpleNamespace(
            manager=object(), lease_id="lease-1234567890abcdef", project_id="immich",
            namespace="ca-l2-immich-1234567890", kube_context="chaosatlas-apps",
        )
        return kwargs["execute"](
            runtime_path, tmp_path / "inner", "chaosatlas-apps", context,
        )

    monkeypatch.setattr(
        "chaosatlas.orchestration.engine.LeaseTransactionDependencyFactory",
        fake_dependency_factory,
    )
    monkeypatch.setattr("chaosatlas.orchestration.batch.run_live_batch", fake_batch)
    monkeypatch.setattr("chaosatlas.orchestration.isolated_run.run_isolated_live", fake_isolated)

    result = RunEngine().run(RunRequest(
        profile_path=profile_path,
        output_root=tmp_path / "run",
        mode="live",
        approve_live=True,
        candidate_id="immich:any:image_pull_failure",
        isolation_fault="image_pull_failure",
        approve_isolation=True,
        oracle_approval_dir=APPROVAL,
    ))

    assert result["status"] == "completed"
    assert captured["runtime_profile"]["business_oracles"][0]["kind"] == "transaction_http"
    assert captured["dependency_factory_args"]["lease_id"] == "lease-1234567890abcdef"
    assert captured["batch"]["candidate_runner"] is not None


def test_lease_dependency_factory_bootstraps_and_persists_only_binding_metadata(monkeypatch, tmp_path):
    manager = IsolationManager(
        store=LeaseStore(tmp_path / "state"), providers=ProviderRegistry([]),
    )
    manager.status = lambda _lease_id: {
        "state": "ready", "target_name": "ca-l2-demo-1234567890",
        "runtime_locator": {"kube_context": "test-context"}, "project_id": "demo",
    }
    events = []

    class Environment:
        def __init__(self, *_args, **_kwargs):
            pass

        def open(self):
            events.append("open-bootstrap")

        def close(self):
            events.append("close-bootstrap")

    class Runtime:
        def __init__(self, *_args, **_kwargs):
            pass

        def bind_principal(self, _references):
            return {"principal_id": "principal-1", "credential_bindings": []}

        def release(self):
            return {"status": "cleanup_verified"}

    contract = {
        "project_id": "demo", "project_revision": "a" * 64,
        "oracle_id": "demo-v3", "contract_sha256": "b" * 64,
        "credential_refs": [],
        "runtime_scope": {"service": "demo", "image_digest": "sha256:" + "c" * 64},
    }
    monkeypatch.setattr(transaction_integration, "load_approved_contract", lambda *_: (ROOT / "projects" / "demo.json", contract))
    monkeypatch.setattr(transaction_integration, "KubernetesIdentityEnvironment", Environment)
    monkeypatch.setattr(transaction_integration, "BOOTSTRAPPERS", {"demo": lambda _env: ({"principal_id": "principal-1"}, {"fixture": "ok"})})
    monkeypatch.setattr(transaction_integration, "LeaseRuntime", Runtime)
    monkeypatch.setattr(transaction_integration, "SecretHeaders", lambda *_: (lambda _reference: {}))
    monkeypatch.setattr(transaction_integration, "build_project_fixtures", lambda *_: ({"fixture": "ok"}, None))
    factory = LeaseTransactionDependencyFactory(
        manager=manager, lease_id="lease-1234567890abcdef",
        approval_dir=APPROVAL, project_id="demo",
    )
    oracle = {
        "service": "demo", "remote_port": 8080, "approved_oracle_id": "demo-v3",
        "approved_contract_sha256": "b" * 64,
        "approved_image_digest": "sha256:" + "c" * 64,
    }

    dependencies = factory(
        oracle, "ca-l2-demo-1234567890", "test-context", tmp_path / "run",
    )

    persisted = json.loads((tmp_path / "run" / "transaction-runtime-binding.json").read_text(encoding="utf-8"))
    assert events == ["open-bootstrap", "close-bootstrap"]
    assert dependencies.contract["oracle_id"] == "demo-v3"
    assert Path(dependencies.ledger_root) == tmp_path / "transaction-state"
    assert persisted["principal_binding"]["principal_id"] == "principal-1"
    assert "secret" not in json.dumps(persisted).lower()
