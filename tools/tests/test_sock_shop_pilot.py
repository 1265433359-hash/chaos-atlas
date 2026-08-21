from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.sock_shop_pilot import attach_pilot_contract_to_case, build_sock_shop_podkill_contract, run_sock_shop_preflight


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "artifacts" / "sock-shop" / "sock-shop-lab-manifest.yaml"
PROFILE = ROOT / "artifacts" / "project_profiles" / "sock-shop" / "project_profile.json"


def test_build_sock_shop_podkill_contract_is_bound_to_single_frontend(tmp_path: Path):
    contract = build_sock_shop_podkill_contract(
        manifest_path=MANIFEST,
        profile_path=PROFILE,
        output_root=tmp_path / "pilot",
    )
    assert contract["status"] == "static_ready"
    assert contract["namespace"] == "sock-shop-lab"
    assert contract["target"] == "deployment:front-end"
    assert contract["mutation_manifest"]["kind"] == "PodChaos"
    assert contract["mutation_manifest"]["metadata"]["namespace"] == "sock-shop-lab"
    assert contract["oracle"]["success_contract"] == "HTTP 200"
    assert (tmp_path / "pilot" / "contract.json").is_file()
    assert (tmp_path / "pilot" / "mutation.yaml").is_file()


def test_build_sock_shop_contract_rejects_non_singleton_target(tmp_path: Path):
    source = tmp_path / "manifest.yaml"
    source.write_text(
        MANIFEST.read_text(encoding="utf-8").replace(
            "  name: front-end\n  namespace: sock-shop-lab\nspec:\n  replicas: 1",
            "  name: front-end\n  namespace: sock-shop-lab\nspec:\n  replicas: 2",
            1,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="single replica"):
        build_sock_shop_podkill_contract(
            manifest_path=source,
            profile_path=PROFILE,
            output_root=tmp_path / "pilot",
        )


class Runner:
    def __init__(self, responses: dict[tuple[str, ...], tuple[int, str, str]]):
        self.responses = responses
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, args: list[str], timeout: int = 30, input_text: str | None = None):
        self.calls.append(tuple(args))
        return self.responses.get(tuple(args), (1, "", "not configured"))


def test_sock_shop_preflight_is_read_only_and_requires_ready_target(tmp_path: Path):
    contract = build_sock_shop_podkill_contract(
        manifest_path=MANIFEST,
        profile_path=PROFILE,
        output_root=tmp_path / "pilot",
    )
    runner = Runner({
        ("get", "namespace", "sock-shop-lab", "-o", "json"): (0, "{}", ""),
        ("get", "deployment", "front-end", "-n", "sock-shop-lab", "-o", "json"): (
            0,
            json.dumps({"spec": {"replicas": 1}, "status": {"readyReplicas": 1}}),
            "",
        ),
        ("get", "crd", "podchaos.chaos-mesh.org", "-o", "json"): (0, "{}", ""),
        ("get", "pods", "-n", "sock-shop-lab", "-l", "name=front-end", "-o", "json"): (
            0,
            json.dumps({"items": [{"metadata": {"name": "front-end-1"}, "status": {"phase": "Running"}}]}),
            "",
        ),
    })
    result = run_sock_shop_preflight(contract, runner=runner)
    assert result["status"] == "ready_for_approval"
    assert result["apply_allowed"] is False
    assert all(not call[:1] in {("apply",), ("delete",)} for call in runner.calls)


def test_sock_shop_preflight_blocks_when_target_pod_is_missing(tmp_path: Path):
    contract = build_sock_shop_podkill_contract(
        manifest_path=MANIFEST,
        profile_path=PROFILE,
        output_root=tmp_path / "pilot",
    )
    runner = Runner({
        ("get", "namespace", "sock-shop-lab", "-o", "json"): (0, "{}", ""),
        ("get", "deployment", "front-end", "-n", "sock-shop-lab", "-o", "json"): (0, json.dumps({"spec": {"replicas": 1}, "status": {"readyReplicas": 0}}), ""),
        ("get", "crd", "podchaos.chaos-mesh.org", "-o", "json"): (0, "{}", ""),
        ("get", "pods", "-n", "sock-shop-lab", "-l", "name=front-end", "-o", "json"): (0, json.dumps({"items": []}), ""),
    })
    result = run_sock_shop_preflight(contract, runner=runner)
    assert result["status"] == "blocked"
    assert any("Ready" in error or "Pod" in error for error in result["errors"])


def test_pilot_contract_attaches_mutation_to_pending_case(tmp_path: Path):
    contract = build_sock_shop_podkill_contract(
        manifest_path=MANIFEST,
        profile_path=PROFILE,
        output_root=tmp_path / "pilot",
    )
    case = {
        "project_id": "sock-shop",
        "project_commit": "sock-shop-fixture-commit",
        "namespace": "sock-shop-lab",
        "test_node": {"target": "deployment:front-end"},
        "weakness_status": "candidate",
        "rca_status": "pending",
        "knowledge_status": "none",
    }
    enriched = attach_pilot_contract_to_case(case, contract)
    assert enriched["namespace"] == "sock-shop-lab"
    assert enriched["test_node"]["mutation_manifest"]["kind"] == "PodChaos"
    assert enriched["cleanup_contract"]["must_be_absent"] is True
    assert case.get("cleanup_contract") is None


def test_pilot_contract_rejects_case_target_mismatch(tmp_path: Path):
    contract = build_sock_shop_podkill_contract(
        manifest_path=MANIFEST,
        profile_path=PROFILE,
        output_root=tmp_path / "pilot",
    )
    case = {
        "project_id": "sock-shop",
        "project_commit": "sock-shop-fixture-commit",
        "test_node": {"target": "deployment:carts"},
    }
    with pytest.raises(ValueError, match="target"):
        attach_pilot_contract_to_case(case, contract)
