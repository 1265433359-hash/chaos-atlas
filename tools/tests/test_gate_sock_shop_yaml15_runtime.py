import hashlib
import json
import sys

import yaml

import tools.gate_sock_shop_yaml15_runtime as gate_module
from tools.gate_sock_shop_yaml15_runtime import gate_yaml15_runtime_plan


METHOD = "chaosatlas-ablation-yaml15"


def _mutation(path):
    path.write_text(
        yaml.safe_dump(
            {
                "apiVersion": "chaos-mesh.org/v1alpha1",
                "kind": "PodChaos",
                "metadata": {"name": "yaml15-ready", "namespace": "chaosatlas-sock-shop"},
                "spec": {
                    "action": "pod-kill",
                    "mode": "one",
                    "selector": {
                        "namespaces": ["chaosatlas-sock-shop"],
                        "labelSelectors": {"name": "catalogue"},
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_gate_records_compile_blocked_and_server_validates_runtime_candidates(tmp_path, monkeypatch):
    mutation = tmp_path / "mutation.yaml"
    _mutation(mutation)
    digest = hashlib.sha256(mutation.read_bytes()).hexdigest()
    plan_path = tmp_path / "runtime-plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "methods": {
                    METHOD: {
                        "candidates": [
                            {
                                "hypothesis_id": "h-ready",
                                "target_service": "catalogue",
                                "path": str(mutation),
                                "sha256": digest,
                                "gate": {"status": "passed", "reason": "static_compiled"},
                            },
                            {
                                "hypothesis_id": "h-blocked",
                                "target_service": "catalogue-db",
                                "path": None,
                                "sha256": None,
                                "gate": {"status": "failed", "reason": "http_target_not_applicable:catalogue-db"},
                            },
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    class Completed:
        returncode = 0
        stdout = "podchaos.chaos-mesh.org/yaml15-ready configured (server dry run)"
        stderr = ""

    monkeypatch.setattr("tools.gate_sock_shop_yaml15_runtime.subprocess.run", lambda *_a, **_k: Completed())
    monkeypatch.setattr(
        "tools.gate_sock_shop_yaml15_runtime.check_mutation",
        lambda _path: {"decision": "ready_for_injection", "errors": []},
    )

    report = gate_yaml15_runtime_plan(plan_path, tmp_path / "gate.json")

    assert report["status"] == "passed_with_exclusions"
    assert report["summary"] == {
        "generated_families": 2,
        "compile_blocked": 1,
        "server_dry_run_passed": 1,
        "ready_for_injection": 1,
        "runtime_blocked": 0,
    }
    assert report["results"][1]["status"] == "compile_blocked"
    assert report["human_review"] == "pending"
    assert report["knowledge_base_updated"] is False


def test_gate_blocks_hash_mismatch_before_kubectl(tmp_path, monkeypatch):
    mutation = tmp_path / "mutation.yaml"
    _mutation(mutation)
    plan_path = tmp_path / "runtime-plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "methods": {
                    METHOD: {
                        "candidates": [
                            {
                                "hypothesis_id": "h-ready",
                                "target_service": "catalogue",
                                "path": str(mutation),
                                "sha256": "0" * 64,
                                "gate": {"status": "passed", "reason": "static_compiled"},
                            }
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    calls = []
    monkeypatch.setattr(
        "tools.gate_sock_shop_yaml15_runtime.subprocess.run",
        lambda *_a, **_k: calls.append(True),
    )

    report = gate_yaml15_runtime_plan(plan_path, tmp_path / "gate.json")

    assert report["status"] == "blocked"
    assert report["summary"]["runtime_blocked"] == 1
    assert not calls


def test_cli_accepts_passed_with_exclusions(monkeypatch, tmp_path):
    monkeypatch.setattr(
        gate_module,
        "gate_yaml15_runtime_plan",
        lambda *_args: {"status": "passed_with_exclusions", "summary": {}},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "gate_sock_shop_yaml15_runtime.py",
            "--runtime-plan",
            str(tmp_path / "runtime-plan.json"),
            "--report",
            str(tmp_path / "gate.json"),
        ],
    )

    assert gate_module.main() == 0
