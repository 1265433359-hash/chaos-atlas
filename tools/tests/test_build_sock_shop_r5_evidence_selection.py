import hashlib
import json
from pathlib import Path

import yaml

from tools.build_sock_shop_r5_evidence_selection import (
    load_full_evidence,
    validate_runtime_report,
)


def _mutation(path: Path):
    path.write_text(
        yaml.safe_dump(
            {
                "apiVersion": "chaos-mesh.org/v1alpha1",
                "kind": "PodChaos",
                "metadata": {"name": "m", "namespace": "chaosatlas-sock-shop"},
                "spec": {
                    "action": "pod-kill",
                    "mode": "one",
                    "selector": {
                        "namespaces": ["chaosatlas-sock-shop"],
                        "labelSelectors": {"name": "catalogue-db"},
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _report(path: Path, mutation: Path, replicate: int):
    diagnostics = path.with_suffix(".diagnostics")
    diagnostics.mkdir(parents=True)
    log = diagnostics / "target.log"
    log.write_text("ok\n", encoding="utf-8")
    value = {
        "status": "completed",
        "mutation_id": "full-h-1",
        "replicate": replicate,
        "mutation": {"path": str(mutation), "sha256": hashlib.sha256(mutation.read_bytes()).hexdigest()},
        "baseline": {"pass": True},
        "injection": {"applied": True, "injected": True},
        "recovery": {"recovered": True},
        "cleanup": {"absent_confirmed": True, "residual_resources": [], "global_scan_errors": []},
        "washout": {"stable": True},
        "observation": {"classification": "weakness_observed"},
        "diagnostics": {
            "status": "captured",
            "files": [{"path": str(log), "sha256": hashlib.sha256(log.read_bytes()).hexdigest()}],
        },
        "human_review": "pending",
        "knowledge_base_updated": False,
    }
    path.write_text(json.dumps(value), encoding="utf-8")


def test_runtime_report_validator_checks_lifecycle_and_file_hashes(tmp_path):
    mutation = tmp_path / "mutation.yaml"
    _mutation(mutation)
    report = tmp_path / "full-h-1-rep-1.json"
    _report(report, mutation, 1)

    result = validate_runtime_report(report)

    assert result["valid"] is True
    assert result["classification"] == "weakness_observed"
    assert result["report_sha256"] == hashlib.sha256(report.read_bytes()).hexdigest()


def test_full_evidence_requires_two_valid_reports_with_same_instance(tmp_path):
    mutation = tmp_path / "mutation.yaml"
    _mutation(mutation)
    discovery = tmp_path / "discovery.json"
    discovery.write_text(
        json.dumps(
            {
                "hypotheses": [
                    {
                        "id": "full-h-1",
                        "target_service": "catalogue-db",
                        "action_or_target": "pod-kill",
                        "call_chain_position": "data-dependency",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    reports = tmp_path / "reports"
    reports.mkdir()
    _report(reports / "full-h-1-rep-1.json", mutation, 1)
    _report(reports / "full-h-1-rep-2.json", mutation, 2)

    evidence = load_full_evidence(discovery, reports)

    assert len(evidence["eligible_by_instance"]) == 1
    item = next(iter(evidence["eligible_by_instance"].values()))
    assert item["hypothesis_id"] == "full-h-1"
    assert len(item["reports"]) == 2
