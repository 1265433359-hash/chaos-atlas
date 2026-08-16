import hashlib
import json
from pathlib import Path

import pytest

from tools.build_sock_shop_full_top11 import build_full_top11_manifest


def _record(tmp_path: Path, index: int, confidence: float, source_order: int):
    mutation = tmp_path / f"m-{index}.yaml"
    mutation.write_text(
        "apiVersion: chaos-mesh.org/v1alpha1\nkind: PodChaos\n"
        f"metadata:\n  name: m-{index}\n  namespace: chaosatlas-sock-shop\n"
        "spec:\n  action: pod-kill\n  mode: one\n  selector:\n"
        "    namespaces: [chaosatlas-sock-shop]\n"
        f"    labelSelectors: {{name: service-{index}}}\n",
        encoding="utf-8",
    )
    return {
        "hypothesis_id": f"h-{index}",
        "confidence_score": confidence,
        "source_order": source_order,
        "mutation_instance_key": f"instance-{index}",
        "fault_family_key": f"family-{index}",
        "source_path": str(mutation),
        "mutation_sha256": hashlib.sha256(mutation.read_bytes()).hexdigest(),
        "historical_evidence_available": index % 2 == 0,
        "gate_decision": "blocked" if index == 0 else "ready_for_injection",
    }


def test_top11_selection_uses_confidence_not_evidence_or_gate(tmp_path):
    records = [_record(tmp_path, index, 0.50 + index / 100, index) for index in range(13)]
    records[12]["gate_decision"] = "blocked"
    records[12]["historical_evidence_available"] = False
    audit = tmp_path / "overlap.json"
    audit.write_text(
        json.dumps(
            {
                "normalization_config_sha256": "a" * 64,
                "full_only": records[:12],
                "family_overlap": [{"full": records[12], "ablation": {"hypothesis_id": "a"}}],
            }
        ),
        encoding="utf-8",
    )

    result = build_full_top11_manifest(audit, tmp_path / "out")

    assert [item["hypothesis_id"] for item in result["top11"]] == [f"h-{i}" for i in range(12, 1, -1)]
    assert result["top11"][0]["gate_decision"] == records[12]["gate_decision"]
    assert result["selection_policy"]["runtime_outcomes_used"] is False
    assert result["selection_policy"]["evidence_availability_used"] is False
    assert result["human_review"] == "pending"
    assert result["knowledge_base_updated"] is False


def test_top11_tie_breaks_by_source_order_then_instance_key(tmp_path):
    first = _record(tmp_path, 1, 0.9, 10)
    second = _record(tmp_path, 2, 0.9, 9)
    third = _record(tmp_path, 3, 0.9, 9)
    second["mutation_instance_key"] = "z"
    third["mutation_instance_key"] = "a"
    audit = tmp_path / "overlap.json"
    audit.write_text(
        json.dumps({"normalization_config_sha256": "b" * 64, "full_only": [first, second, third], "family_overlap": []}),
        encoding="utf-8",
    )

    result = build_full_top11_manifest(audit, tmp_path / "out", limit=3)

    assert [item["hypothesis_id"] for item in result["top11"]] == ["h-3", "h-2", "h-1"]


def test_top11_refuses_nonempty_output_and_detects_mutation_hash_change(tmp_path):
    record = _record(tmp_path, 1, 0.9, 1)
    audit = tmp_path / "overlap.json"
    audit.write_text(
        json.dumps({"normalization_config_sha256": "c" * 64, "full_only": [record], "family_overlap": []}),
        encoding="utf-8",
    )
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "keep.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError):
        build_full_top11_manifest(audit, occupied, limit=1)

    Path(record["source_path"]).write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        build_full_top11_manifest(audit, tmp_path / "new", limit=1)


def test_top11_requires_normalization_config_hash(tmp_path):
    record = _record(tmp_path, 1, 0.9, 1)
    audit = tmp_path / "overlap.json"
    audit.write_text(
        json.dumps({"full_only": [record], "family_overlap": []}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="normalization_config_sha256"):
        build_full_top11_manifest(audit, tmp_path / "out", limit=1)
