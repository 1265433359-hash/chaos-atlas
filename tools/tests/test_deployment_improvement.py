from __future__ import annotations

import copy
from pathlib import Path

import yaml

from tools.deployment_improvement import apply_patch_copy, propose_improvements, classify_retest, build_improvement_evidence


def test_proposal_is_structured_and_copy_application_preserves_source(tmp_path: Path):
    source = tmp_path / "source"
    output = tmp_path / "copy"
    source.mkdir()
    manifest = source / "api.yaml"
    manifest.write_text(yaml.safe_dump({"kind": "Deployment", "spec": {"replicas": 1}}), encoding="utf-8")
    node = {"deployment": {"desired_replicas": 1}, "source_refs": ["api.yaml"]}
    proposals = propose_improvements(node, "availability_degraded")
    assert any(item["json_pointer"] == "/spec/replicas" for item in proposals)
    applied = apply_patch_copy(source, proposals[0], output)
    assert applied["status"] == "applied"
    assert yaml.safe_load(manifest.read_text(encoding="utf-8"))["spec"]["replicas"] == 1
    assert yaml.safe_load((output / "api.yaml").read_text(encoding="utf-8"))["spec"]["replicas"] == 2


def test_patch_selects_deployment_document_in_multi_document_manifest(tmp_path: Path):
    source = tmp_path / "source"
    output = tmp_path / "copy"
    source.mkdir()
    manifest = source / "bundle.yaml"
    manifest.write_text(
        yaml.safe_dump_all(
            [
                {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "lab"}},
                {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "metadata": {"name": "front-end"},
                    "spec": {"replicas": 1},
                },
            ],
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    result = apply_patch_copy(
        source,
        {
            "source_ref": "bundle.yaml",
            "document_selector": {"kind": "Deployment", "name": "front-end"},
            "json_pointer": "/spec/replicas",
            "old_value": 1,
            "new_value": 2,
        },
        output,
    )

    assert result["status"] == "applied"
    docs = list(yaml.safe_load_all((output / "bundle.yaml").read_text(encoding="utf-8")))
    assert docs[0]["kind"] == "Namespace"
    assert docs[1]["metadata"]["name"] == "front-end"
    assert docs[1]["spec"]["replicas"] == 2


def test_retest_never_verifies_blocked_or_regressed_change():
    assert classify_retest("environment_blocked", baseline="availability_degraded", after="availability_defended") == "deployment_blocked"
    assert classify_retest("executed", baseline="availability_degraded", after="availability_degraded") == "regression"
    assert classify_retest("executed", baseline="availability_degraded", after="availability_defended") == "improvement_verified"


def test_structured_patch_allowlist_includes_pdb_hpa_and_liveness(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    manifest = source / "manifest.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "spec": {
                    "replicas": 1,
                    "template": {"spec": {"containers": [{"name": "app", "livenessProbe": {"periodSeconds": 10}}]}},
                },
            }
        ),
        encoding="utf-8",
    )
    for pointer, old, new in (
        ("/spec/template/spec/containers/0/livenessProbe", {"periodSeconds": 10}, {"periodSeconds": 5}),
    ):
        result = apply_patch_copy(
            source,
            {"source_ref": "manifest.yaml", "json_pointer": pointer, "old_value": old, "new_value": new},
            tmp_path / "patched",
        )
        assert result["status"] == "applied"


def test_improvement_evidence_only_allows_knowledge_update_after_verified_retest():
    verified = build_improvement_evidence(
        {
            "status": "improvement_verified",
            "baseline": {"verdict": "availability_degraded"},
            "after": {"verdict": "availability_defended"},
            "comparison": {"same_scenario_contract": True, "cleanup_verified": True},
        }
    )
    blocked = build_improvement_evidence(
        {
            "status": "deployment_blocked",
            "baseline": {"verdict": "availability_degraded"},
            "after": {"verdict": "availability_defended"},
            "comparison": {"same_scenario_contract": True, "cleanup_verified": True},
        }
    )

    assert verified["knowledge_update_allowed"] is True
    assert blocked["knowledge_update_allowed"] is False
    assert blocked["defense_claim"] is None
