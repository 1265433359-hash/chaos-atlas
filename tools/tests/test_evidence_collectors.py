from __future__ import annotations

from pathlib import Path

import pytest

from tools.evidence_collectors import (
    EvidenceCollectorError,
    collect_file_evidence,
    collect_unavailable_evidence,
    validate_collected_evidence,
)


def test_collect_file_evidence_hashes_a_safe_artifact(tmp_path: Path) -> None:
    source = tmp_path / "logs" / "catalogue.log"
    source.parent.mkdir()
    source.write_text("database connection failed\n", encoding="utf-8")

    evidence = collect_file_evidence(
        root=tmp_path,
        source_ref="logs/catalogue.log",
        evidence_id="EV-LOG-001",
        kind="runtime_log",
        claim_scope="catalogue-db",
        interpretation="catalogue logged a database connection failure",
        satisfies=["scoped_catalogue_logs"],
    )

    assert evidence["polarity"] == "supports"
    assert evidence["source_ref"] == "logs/catalogue.log"
    assert evidence["sha256"]
    assert evidence["satisfies"] == ["scoped_catalogue_logs"]
    assert validate_collected_evidence(evidence, "catalogue-db") == {
        "valid": True,
        "errors": [],
    }


def test_missing_file_becomes_unavailable_evidence(tmp_path: Path) -> None:
    evidence = collect_file_evidence(
        root=tmp_path,
        source_ref="logs/missing.log",
        evidence_id="EV-LOG-002",
        kind="runtime_log",
        claim_scope="catalogue-db",
        interpretation="catalogue log capture was unavailable",
        satisfies=["scoped_catalogue_logs"],
    )

    assert evidence["polarity"] == "unavailable"
    assert evidence["unavailable_reason"] == "source_not_found"
    assert evidence["satisfies"] == []


def test_explicit_unavailable_evidence_preserves_attempted_source(tmp_path: Path) -> None:
    evidence = collect_unavailable_evidence(
        root=tmp_path,
        source_ref="traces/catalogue.json",
        evidence_id="EV-TRACE-001",
        kind="trace",
        claim_scope="catalogue-db",
        reason="collector_not_configured",
    )

    assert evidence["polarity"] == "unavailable"
    assert evidence["source_ref"] == "traces/catalogue.json"
    assert evidence["unavailable_reason"] == "collector_not_configured"
    assert evidence["sha256"] is None


@pytest.mark.parametrize(
    "source_ref",
    ["C:/secrets/catalogue.log", "../outside.log", "/absolute.log", "https://example.test/log"],
)
def test_collectors_reject_unsafe_source_refs(tmp_path: Path, source_ref: str) -> None:
    with pytest.raises(EvidenceCollectorError):
        collect_file_evidence(
            root=tmp_path,
            source_ref=source_ref,
            evidence_id="EV-UNSAFE-001",
            kind="runtime_log",
            claim_scope="catalogue-db",
            interpretation="unsafe input",
        )


def test_collectors_reject_sensitive_artifact_content(tmp_path: Path) -> None:
    source = tmp_path / "config.json"
    source.write_text('{"password":"secret"}', encoding="utf-8")

    with pytest.raises(EvidenceCollectorError, match="sensitive"):
        collect_file_evidence(
            root=tmp_path,
            source_ref="config.json",
            evidence_id="EV-CONFIG-001",
            kind="config",
            claim_scope="catalogue-db",
            interpretation="configuration was collected",
        )


def test_collected_evidence_scope_mismatch_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "events.json"
    source.write_text("{}", encoding="utf-8")
    evidence = collect_file_evidence(
        root=tmp_path,
        source_ref="events.json",
        evidence_id="EV-EVENT-001",
        kind="kubernetes_event",
        claim_scope="catalogue-db",
        interpretation="event was collected",
    )

    result = validate_collected_evidence(evidence, "orders-db")

    assert result["valid"] is False
    assert any("claim_scope" in error for error in result["errors"])
