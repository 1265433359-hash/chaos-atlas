from __future__ import annotations

import json
from pathlib import Path

from tools.chaosatlas_adapters import FakeExecutor, KnowledgeProvider, OfflineProjectAdapter


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "chaosatlas_offline"


def _profile(project_id: str, namespace: str) -> dict:
    return {
        "schema_version": "chaosatlas-project-profile-v1",
        "project_id": project_id,
        "project_commit": f"{project_id}-fixture-commit",
        "revision_kind": "fixture",
        "source": {"manifest_roots": ["artifacts/sock-shop"], "source_roots": ["artifacts/sock-shop"]},
        "namespace_policy": {"allowed_namespaces": [namespace], "isolation_required": True},
        "business_oracles": [{"id": "homepage", "kind": "http", "entrypoint": "/", "success_contract": "http_200"}],
        "observability": {"logs": {"provider": "fixture"}, "events": {"provider": "fixture"}},
        "recovery": {"deadline_s": 30, "require_business_probe": True, "require_cleanup": True},
        "cleanup": {"owner": "chaosatlas", "must_be_empty": True},
        "sensitive_data_policy": {"redact_fields": ["password"]},
    }


def test_offline_adapter_inventory_is_project_scoped() -> None:
    facts_path = FIXTURE_ROOT / "sock-shop" / "project_facts.json"
    adapter = OfflineProjectAdapter(facts_path, workspace_root=REPO_ROOT)

    result = adapter.inventory(_profile("sock-shop", "sock-shop-lab"))

    assert result["project_id"] == "sock-shop"
    assert result["services"]
    assert result["business_oracles"]
    assert result["claim_scope"] == "static"


def test_server_deployment_detection_builds_candidates_without_runtime_verdict() -> None:
    facts_path = FIXTURE_ROOT / "sock-shop" / "project_facts.json"
    adapter = OfflineProjectAdapter(facts_path, workspace_root=REPO_ROOT)
    inventory = adapter.inventory(_profile("sock-shop", "sock-shop-lab"))

    result = adapter.detect_server_deployment(inventory)

    assert result["status"] == "verified"
    assert result["candidates"]
    assert result["capability_name"] == "server_deployment_detection"
    assert "runtime_verdict" not in json.dumps(result)


def test_fake_executor_marks_outputs_as_synthetic_and_completes_cleanup() -> None:
    plan = {"candidate_id": "candidate-1", "expected_invariant": "business_probe_success"}

    result = FakeExecutor().run(plan)

    assert result["evidence_status"] == "synthetic"
    assert result["lifecycle"] == ["preflight", "baseline", "inject", "observe", "recover", "cleanup"]
    assert result["cleanup_confirmed"] is True
    assert result["runtime_verdict"] == "not_run"


def test_knowledge_provider_reads_local_provisional_card_snapshot(tmp_path: Path) -> None:
    card = {
        "id": "KB-RCA-sock-shop-front-end-pod-kill-intent",
        "status": "provisional",
        "project": "sock-shop",
        "test_node": {"family": "pod_kill", "operation": "pod_kill"},
    }
    (tmp_path / f"{card['id']}.json").write_text(json.dumps(card), encoding="utf-8")

    result = KnowledgeProvider().retrieve(
        project_id="sock-shop",
        candidate_space={"candidate_count": 1},
        root=tmp_path,
    )

    assert result["cards"][0]["id"] == card["id"]
    assert result["cards"][0]["status"] == "provisional"
