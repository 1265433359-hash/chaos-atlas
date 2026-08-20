from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import math

import pytest

from tools.rca_loop import (
    EVIDENCE_POLARITIES,
    KNOWLEDGE_STATES,
    RCA_STATES,
    build_weakness_id,
    canonical_json,
    evidence_polarity_counts,
    evaluate_knowledge_promotion,
    evaluate_rca_transition,
    make_evidence,
    sha256_json,
    validate_evidence_scope,
)


def test_state_constants_define_the_supported_contract_states() -> None:
    assert RCA_STATES == {"pending", "bounded", "confirmed", "rejected"}
    assert KNOWLEDGE_STATES == {
        "none",
        "provisional",
        "local_reusable",
        "cross_project_pending",
        "cross_project_reusable",
        "contested",
    }
    assert EVIDENCE_POLARITIES == {"supports", "contradicts", "unavailable", "neutral"}


def test_build_weakness_id_normalizes_components_stably() -> None:
    assert (
        build_weakness_id("sock-shop", "front-end->catalogue", "HTTPChaos", "abort")
        == "WS-sock-shop-front-end-catalogue-httpchaos-abort"
    )


def test_make_evidence_returns_normalized_utc_evidence() -> None:
    evidence = make_evidence(
        evidence_id="EV-001",
        kind="runtime-log",
        polarity="supports",
        claim_scope="catalogue-db-availability",
        source_ref=r"reports\run-1.json",
        interpretation="The database connection failed during the injected outage.",
        sha256="a" * 64,
        window={"start": "2026-08-20T00:00:00Z", "end": "2026-08-20T00:01:00Z"},
    )

    assert evidence["evidence_id"] == "EV-001"
    assert evidence["kind"] == "runtime-log"
    assert evidence["polarity"] == "supports"
    assert evidence["claim_scope"] == "catalogue-db-availability"
    assert evidence["source_ref"] == "reports/run-1.json"
    assert evidence["sha256"] == "a" * 64
    assert evidence["window"] == {
        "start": "2026-08-20T00:00:00Z",
        "end": "2026-08-20T00:01:00Z",
    }
    assert evidence["window"]["start"].endswith("Z")
    assert evidence["interpretation"].startswith("The database")
    collected_at = datetime.fromisoformat(evidence["collected_at"].replace("Z", "+00:00"))
    assert collected_at.tzinfo is not None
    assert collected_at.utcoffset() == timezone.utc.utcoffset(collected_at)


@pytest.mark.parametrize("sha256", ["a" * 63, "g" * 64, 12345])
def test_make_evidence_rejects_invalid_sha256(sha256: object) -> None:
    with pytest.raises(ValueError, match="sha256"):
        make_evidence(
            evidence_id="EV-001E",
            kind="runtime-log",
            polarity="supports",
            claim_scope="scope",
            source_ref="reports/run.json",
            interpretation="An observation.",
            sha256=sha256,
        )


def test_make_evidence_normalizes_missing_window_to_empty_dict() -> None:
    evidence = make_evidence(
        evidence_id="EV-001A",
        kind="runtime-log",
        polarity="supports",
        claim_scope="scope",
        source_ref="reports/run.json",
        interpretation="An observation.",
    )

    assert evidence["window"] == {}


def test_make_evidence_rejects_non_dict_window() -> None:
    with pytest.raises(ValueError, match="window"):
        make_evidence(
            evidence_id="EV-001B",
            kind="runtime-log",
            polarity="supports",
            claim_scope="scope",
            source_ref="reports/run.json",
            interpretation="An observation.",
            window=["not", "a", "mapping"],
        )


@pytest.mark.parametrize(
    "window",
    [
        {"start": "2026-08-20T00:00:00+08:00"},
        {"start": "2026-08-20T00:00:00"},
        {"start": "not-a-time"},
        {"start": 123},
        {"finish": "2026-08-20T00:00:00Z"},
        {"start": "2026-08-20T01:00:00Z", "end": "2026-08-20T00:00:00Z"},
    ],
)
def test_make_evidence_rejects_invalid_window_contracts(window: object) -> None:
    with pytest.raises(ValueError, match="window"):
        make_evidence(
            evidence_id="EV-001C",
            kind="runtime-log",
            polarity="supports",
            claim_scope="scope",
            source_ref="reports/run.json",
            interpretation="An observation.",
            window=window,
        )


def test_make_evidence_copies_window_input() -> None:
    window = {"start": "2026-08-20T00:00:00Z"}
    evidence = make_evidence(
        evidence_id="EV-001D",
        kind="runtime-log",
        polarity="supports",
        claim_scope="scope",
        source_ref="reports/run.json",
        interpretation="An observation.",
        window=window,
    )

    window["start"] = "changed"
    assert evidence["window"] == {"start": "2026-08-20T00:00:00Z"}
    assert evidence["window"] is not window


def test_validate_evidence_scope_rejects_mismatched_scope() -> None:
    evidence = make_evidence(
        evidence_id="EV-002",
        kind="trace",
        polarity="supports",
        claim_scope="catalogue-db-availability",
        source_ref="reports/run-2.json",
        interpretation="The trace contains the database failure.",
    )

    result = validate_evidence_scope(evidence, "orders-db-availability")

    assert result["valid"] is False
    assert any("claim_scope" in error for error in result["errors"])


def test_validate_evidence_scope_accepts_safe_relative_artifact_ref() -> None:
    evidence = {
        "evidence_id": "EV-002A",
        "kind": "trace",
        "polarity": "supports",
        "claim_scope": "scope",
        "source_ref": "artifacts/runtime/run-1.json",
        "interpretation": "The trace contains the expected failure.",
    }

    assert validate_evidence_scope(evidence, "scope") == {"valid": True, "errors": []}


@pytest.mark.parametrize(
    "window",
    [
        ["not", "a", "dict"],
        {"start": 123},
        {"start": "not-an-iso-timestamp"},
        {"finish": "2026-08-20T00:00:00Z"},
    ],
)
def test_validate_evidence_scope_rejects_invalid_window_without_raising(window: object) -> None:
    evidence = {
        "evidence_id": "EV-002B",
        "kind": "trace",
        "polarity": "supports",
        "claim_scope": "scope",
        "source_ref": "artifacts/runtime/run-1.json",
        "interpretation": "The trace contains the expected failure.",
        "window": window,
    }

    result = validate_evidence_scope(evidence, "scope")

    assert result["valid"] is False
    assert any("window" in error for error in result["errors"])


@pytest.mark.parametrize(
    "window",
    [
        {"start": "2026-08-20T00:00:00+08:00"},
        {"start": "2026-08-20T00:00:01Z", "end": "2026-08-20T00:00:00Z"},
    ],
)
def test_validate_evidence_scope_rejects_non_utc_or_reverse_window(window: dict[str, str]) -> None:
    evidence = {
        "evidence_id": "EV-002C",
        "kind": "trace",
        "polarity": "supports",
        "claim_scope": "scope",
        "source_ref": "artifacts/runtime/run-1.json",
        "interpretation": "The trace contains the expected failure.",
        "window": window,
    }

    result = validate_evidence_scope(evidence, "scope")

    assert result["valid"] is False
    assert any("window" in error for error in result["errors"])


def test_validate_evidence_scope_accepts_none_and_valid_window() -> None:
    base = {
        "evidence_id": "EV-002D",
        "kind": "trace",
        "polarity": "supports",
        "claim_scope": "scope",
        "source_ref": "artifacts/runtime/run-1.json",
        "interpretation": "The trace contains the expected failure.",
    }

    assert validate_evidence_scope({**base, "window": None}, "scope") == {"valid": True, "errors": []}
    assert validate_evidence_scope(
        {
            **base,
            "window": {
                "start": "2026-08-20T00:00:00Z",
                "end": "2026-08-20T00:00:01+00:00",
            },
        },
        "scope",
    ) == {"valid": True, "errors": []}


def test_make_evidence_rejects_unknown_polarity() -> None:
    with pytest.raises(ValueError, match="polarity"):
        make_evidence(
            evidence_id="EV-003",
            kind="trace",
            polarity="maybe",
            claim_scope="scope",
            source_ref="reports/run.json",
            interpretation="An observation.",
        )


@pytest.mark.parametrize(
    "source_ref",
    [
        "/absolute/report.json",
        "https://example.test/report.json",
        "foo:bar",
        "reports/../secret.json",
        "reports/password=secret.json",
        'reports/"client_secret":"secret".json',
    ],
)
def test_make_evidence_fails_closed_for_unsafe_source_ref(source_ref: str) -> None:
    with pytest.raises(ValueError, match="source_ref|sensitive"):
        make_evidence(
            evidence_id="EV-003A",
            kind="trace",
            polarity="supports",
            claim_scope="scope",
            source_ref=source_ref,
            interpretation="An observation.",
        )


@pytest.mark.parametrize(
    "sensitive_value",
    [
        "password=secret",
        '"access_token":"secret"',
        '{"client-secret":"secret"}',
        '{"apiKey":"secret"}',
        "authorization: Bearer-secret",
    ],
)
def test_make_evidence_fails_closed_for_sensitive_interpretation(sensitive_value: str) -> None:
    with pytest.raises(ValueError, match="sensitive"):
        make_evidence(
            evidence_id="EV-003B",
            kind="trace",
            polarity="supports",
            claim_scope="scope",
            source_ref="reports/run.json",
            interpretation=sensitive_value,
        )


@pytest.mark.parametrize(
    "interpretation",
    [
        "token: is a field",
        "password: is documented",
        "access_token: is configured",
        "client_secret: is expected",
        "token: explanation",
        "password: label",
        "token: unknown",
        "password: none",
        "token: null",
        "token: redacted",
        "password: redaction",
        "token: not set",
        "password: not configured",
    ],
)
def test_make_evidence_allows_safe_plain_placeholder_descriptions(interpretation: str) -> None:
    evidence = make_evidence(
        evidence_id="EV-003C",
        kind="trace",
        polarity="neutral",
        claim_scope="scope",
        source_ref="reports/token-explanation.json",
        interpretation=interpretation,
    )

    assert evidence["interpretation"] == interpretation


@pytest.mark.parametrize(
    "interpretation",
    [
        '{"password":"secret"}',
        '{"token":"secret"}',
        '{"access_token":"secret"}',
        '{"client_secret":"secret"}',
        '{"apiKey":"secret"}',
        '{"authorization":"Bearer secret"}',
    ],
)
def test_make_evidence_rejects_real_sensitive_json_values(interpretation: str) -> None:
    with pytest.raises(ValueError, match="sensitive"):
        make_evidence(
            evidence_id="EV-003D",
            kind="trace",
            polarity="supports",
            claim_scope="scope",
            source_ref="reports/run.json",
            interpretation=interpretation,
        )


@pytest.mark.parametrize("field", ["evidence_id", "kind", "claim_scope", "source_ref", "interpretation"])
def test_make_evidence_rejects_empty_required_fields(field: str) -> None:
    values = {
        "evidence_id": "EV-004",
        "kind": "trace",
        "polarity": "neutral",
        "claim_scope": "scope",
        "source_ref": "reports/run.json",
        "interpretation": "An observation.",
    }
    values[field] = "   "

    with pytest.raises(ValueError, match=field):
        make_evidence(**values)


@pytest.mark.parametrize(
    "source_ref",
    [
        "/absolute/report.json",
        r"\absolute\report.json",
        r"C:\reports\report.json",
        r"\\server\share\report.json",
        "reports/../secret.json",
        "reports/password=secret.json",
        " /absolute/report.json ",
        " \tC:\\reports\\report.json ",
        " \t\\\\server\\share\\report.json ",
        "https://example.test/report.json",
        "foo:bar",
    ],
)
def test_validate_evidence_scope_rejects_unsafe_source_refs(source_ref: str) -> None:
    evidence = {
        "evidence_id": "EV-005",
        "kind": "trace",
        "polarity": "supports",
        "claim_scope": "scope",
        "source_ref": source_ref,
        "interpretation": "An observation.",
    }

    result = validate_evidence_scope(evidence, "scope")

    assert result["valid"] is False
    assert result["errors"]


@pytest.mark.parametrize(
    "sensitive_value",
    [
        "password=secret",
        "password: secret",
        '"password":"secret"',
        '{"token":"secret"}',
    ],
)
@pytest.mark.parametrize("field", ["source_ref", "interpretation"])
def test_validate_evidence_scope_rejects_sensitive_values_in_plain_and_json_forms(
    sensitive_value: str, field: str
) -> None:
    evidence = {
        "evidence_id": "EV-006",
        "kind": "trace",
        "polarity": "supports",
        "claim_scope": "scope",
        "source_ref": "reports/run.json",
        "interpretation": "An observation.",
    }
    evidence[field] = sensitive_value

    result = validate_evidence_scope(evidence, "scope")

    assert result["valid"] is False
    assert any("sensitive" in error for error in result["errors"])


def test_validate_evidence_scope_does_not_reject_plain_security_explanations() -> None:
    evidence = {
        "evidence_id": "EV-007",
        "kind": "trace",
        "polarity": "neutral",
        "claim_scope": "scope",
        "source_ref": "reports/secrets-overview.json",
        "interpretation": "The report explains how secrets are handled.",
    }

    assert validate_evidence_scope(evidence, "scope")["valid"] is True


def test_validate_evidence_scope_allows_redaction_placeholder_json() -> None:
    evidence = {
        "evidence_id": "EV-007B",
        "kind": "trace",
        "polarity": "neutral",
        "claim_scope": "scope",
        "source_ref": "reports/run.json",
        "interpretation": '{"token":"REDACTED"}',
    }

    assert validate_evidence_scope(evidence, "scope")["valid"] is True


@pytest.mark.parametrize("sha256", ["a" * 63, "g" * 64, 12345])
def test_validate_evidence_scope_rejects_invalid_sha256(sha256: object) -> None:
    evidence = {
        "evidence_id": "EV-007A",
        "kind": "trace",
        "polarity": "supports",
        "claim_scope": "scope",
        "source_ref": "reports/run.json",
        "interpretation": "An observation.",
        "sha256": sha256,
    }

    result = validate_evidence_scope(evidence, "scope")

    assert result["valid"] is False
    assert any("sha256" in error for error in result["errors"])


def test_unavailable_evidence_is_scope_valid_but_not_supporting_or_contradicting() -> None:
    evidence = {
        "evidence_id": "EV-008",
        "kind": "trace",
        "polarity": "unavailable",
        "claim_scope": "scope",
        "source_ref": "reports/run.json",
        "interpretation": "The trace was unavailable.",
    }

    assert validate_evidence_scope(evidence, "scope") == {"valid": True, "errors": []}
    assert evidence_polarity_counts([evidence]) == {
        "supports": 0,
        "contradicts": 0,
        "unavailable": 1,
        "neutral": 0,
    }


def test_evidence_polarity_counts_keep_unavailable_and_neutral_separate() -> None:
    evidence = [
        {"polarity": "supports"},
        {"polarity": "supports"},
        {"polarity": "contradicts"},
        {"polarity": "unavailable"},
        {"polarity": "neutral"},
    ]

    assert evidence_polarity_counts(evidence) == {
        "supports": 2,
        "contradicts": 1,
        "unavailable": 1,
        "neutral": 1,
    }


def test_canonical_json_and_sha256_json_are_order_and_unicode_stable() -> None:
    first = {"b": "中", "a": [2, 1]}
    second = {"a": [2, 1], "b": "中"}

    assert canonical_json(first) == '{"a":[2,1],"b":"\\u4e2d"}'
    assert canonical_json(first) == canonical_json(second)
    assert sha256_json(first) == sha256_json(second)
    assert sha256_json(first) == hashlib.sha256(canonical_json(first).encode("utf-8")).hexdigest()


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_canonical_json_rejects_non_finite_numbers(value: float) -> None:
    with pytest.raises(ValueError):
        canonical_json({"value": value})


def test_pending_to_bounded_requires_and_accepts_boundary_support() -> None:
    result = evaluate_rca_transition(
        current="pending",
        target="bounded",
        boundary_confirmed=True,
        supporting_evidence=1,
        required_evidence_complete=False,
        discriminating_action=False,
        high_severity_contradiction=False,
    )

    assert result == {
        "allowed": True,
        "next_status": "bounded",
        "reason": "stable_boundary_with_supporting_evidence",
    }


def test_confirmed_requires_complete_mechanism_evidence() -> None:
    result = evaluate_rca_transition(
        current="bounded",
        target="confirmed",
        boundary_confirmed=True,
        supporting_evidence=2,
        required_evidence_complete=False,
        discriminating_action=True,
        high_severity_contradiction=False,
    )

    assert result == {"allowed": False, "reason": "required_evidence_incomplete"}


def test_high_severity_contradiction_blocks_confirmed() -> None:
    result = evaluate_rca_transition(
        current="bounded",
        target="confirmed",
        boundary_confirmed=True,
        supporting_evidence=2,
        required_evidence_complete=True,
        discriminating_action=True,
        high_severity_contradiction=True,
    )

    assert result == {"allowed": False, "reason": "high_severity_contradiction"}


def test_bounded_to_confirmed_requires_discriminating_action() -> None:
    result = evaluate_rca_transition(
        current="bounded",
        target="confirmed",
        boundary_confirmed=True,
        supporting_evidence=2,
        required_evidence_complete=True,
        discriminating_action=False,
        high_severity_contradiction=False,
    )

    assert result == {"allowed": False, "reason": "discriminating_action_required"}


def test_confirmed_to_pending_is_an_illegal_regression() -> None:
    result = evaluate_rca_transition(
        current="confirmed",
        target="pending",
        boundary_confirmed=False,
        supporting_evidence=0,
        required_evidence_complete=False,
        discriminating_action=False,
        high_severity_contradiction=False,
    )

    assert result == {"allowed": False, "reason": "illegal_rca_transition"}


def test_rejected_requires_a_falsifier() -> None:
    result = evaluate_rca_transition(
        current="pending",
        target="rejected",
        boundary_confirmed=False,
        supporting_evidence=1,
        required_evidence_complete=False,
        discriminating_action=False,
        high_severity_contradiction=False,
    )

    assert result == {"allowed": False, "reason": "rejection_requires_falsifier"}


def test_rejected_with_reproducible_contradiction_is_allowed() -> None:
    result = evaluate_rca_transition(
        current="bounded",
        target="rejected",
        boundary_confirmed=True,
        supporting_evidence=1,
        required_evidence_complete=False,
        discriminating_action=False,
        high_severity_contradiction=True,
    )

    assert result == {
        "allowed": True,
        "next_status": "rejected",
        "reason": "falsifier_or_reproducible_contradiction",
    }


def test_same_rca_state_is_an_auditable_noop() -> None:
    result = evaluate_rca_transition(
        current="pending",
        target="pending",
        boundary_confirmed=False,
        supporting_evidence=0,
        required_evidence_complete=False,
        discriminating_action=False,
        high_severity_contradiction=False,
    )

    assert result == {"allowed": True, "next_status": "pending", "reason": "state_unchanged"}


@pytest.mark.parametrize(
    ("current", "target", "reason"),
    [
        ("not-a-state", "bounded", "unknown_rca_state"),
        ("pending", "not-a-state", "unknown_rca_state"),
    ],
)
def test_rca_unknown_states_fail_closed(current: str, target: str, reason: str) -> None:
    result = evaluate_rca_transition(
        current=current,
        target=target,
        boundary_confirmed=True,
        supporting_evidence=2,
        required_evidence_complete=True,
        discriminating_action=True,
        high_severity_contradiction=True,
    )

    assert result == {"allowed": False, "reason": reason}


def _valid_transition_evidence(target: str) -> dict[str, object]:
    return {
        "boundary_confirmed": target in {"bounded", "confirmed", "rejected"},
        "supporting_evidence": 1 if target in {"bounded", "confirmed", "rejected"} else 0,
        "required_evidence_complete": target == "confirmed",
        "discriminating_action": target == "confirmed",
        "high_severity_contradiction": target == "rejected",
    }


EXPECTED_LEGAL_RCA_TRANSITIONS = {
    ("pending", "pending"),
    ("pending", "bounded"),
    ("pending", "confirmed"),
    ("pending", "rejected"),
    ("bounded", "pending"),
    ("bounded", "bounded"),
    ("bounded", "confirmed"),
    ("bounded", "rejected"),
    ("confirmed", "bounded"),
    ("confirmed", "confirmed"),
    ("confirmed", "rejected"),
    ("rejected", "rejected"),
    ("rejected", "pending"),
}


EXPECTED_ILLEGAL_RCA_TRANSITIONS = {
    ("confirmed", "pending"),
    ("rejected", "bounded"),
    ("rejected", "confirmed"),
}


LEGAL_RCA_TRANSITIONS = sorted(EXPECTED_LEGAL_RCA_TRANSITIONS)


ILLEGAL_RCA_TRANSITIONS = sorted(EXPECTED_ILLEGAL_RCA_TRANSITIONS)


def test_rca_transition_matrix_declares_exactly_thirteen_legal_and_three_illegal_edges() -> None:
    assert len(EXPECTED_LEGAL_RCA_TRANSITIONS) == 13
    assert len(EXPECTED_ILLEGAL_RCA_TRANSITIONS) == 3
    assert set(LEGAL_RCA_TRANSITIONS) == EXPECTED_LEGAL_RCA_TRANSITIONS
    assert set(ILLEGAL_RCA_TRANSITIONS) == EXPECTED_ILLEGAL_RCA_TRANSITIONS


@pytest.mark.parametrize(("current", "target"), LEGAL_RCA_TRANSITIONS)
def test_rca_transition_matrix_allows_every_legal_transition(current: str, target: str) -> None:
    result = evaluate_rca_transition(
        current=current,
        target=target,
        **_valid_transition_evidence(target),
    )

    assert result["allowed"] is True
    assert result["next_status"] == target


@pytest.mark.parametrize(("current", "target"), ILLEGAL_RCA_TRANSITIONS)
def test_rca_transition_matrix_rejects_every_illegal_transition(current: str, target: str) -> None:
    result = evaluate_rca_transition(
        current=current,
        target=target,
        **_valid_transition_evidence(target),
    )

    assert result == {"allowed": False, "reason": "illegal_rca_transition"}


@pytest.mark.parametrize(
    ("boundary_confirmed", "supporting_evidence"),
    [(False, 1), (True, 0)],
)
def test_bounded_transition_rejects_missing_boundary_or_support(
    boundary_confirmed: bool, supporting_evidence: int
) -> None:
    result = evaluate_rca_transition(
        current="pending",
        target="bounded",
        boundary_confirmed=boundary_confirmed,
        supporting_evidence=supporting_evidence,
        required_evidence_complete=False,
        discriminating_action=False,
        high_severity_contradiction=False,
    )

    assert result == {"allowed": False, "reason": "bounded_requires_boundary_and_support"}


@pytest.mark.parametrize("weakness_status", ["candidate", "confirmed", "protected"])
def test_none_promotes_an_eligible_case_to_provisional(weakness_status: str) -> None:
    result = evaluate_knowledge_promotion(
        current="none",
        weakness_status=weakness_status,
        rca_status="pending",
        valid_reproductions=0,
        valid_counterfactuals=0,
        lifecycle_complete=False,
        direct_evidence=False,
        applicability_complete=False,
        regression_complete=False,
        contradiction=False,
    )

    assert result == {
        "allowed": True,
        "next_status": "provisional",
        "reason": "provisional_case_created",
    }


@pytest.mark.parametrize("weakness_status", ["unsupported", "environment_blocked", "rejected"])
def test_local_reusable_does_not_promote_blocked_weakness(
    weakness_status: str,
) -> None:
    result = evaluate_knowledge_promotion(
        current="local_reusable",
        weakness_status=weakness_status,
        rca_status="confirmed",
        valid_reproductions=2,
        valid_counterfactuals=0,
        lifecycle_complete=True,
        direct_evidence=True,
        applicability_complete=True,
        regression_complete=True,
        contradiction=False,
    )

    assert result == {"allowed": False, "reason": "weakness_status_not_eligible"}


def test_local_reusable_does_not_promote_rejected_rca() -> None:
    result = evaluate_knowledge_promotion(
        current="local_reusable",
        weakness_status="confirmed",
        rca_status="rejected",
        valid_reproductions=2,
        valid_counterfactuals=0,
        lifecycle_complete=True,
        direct_evidence=True,
        applicability_complete=True,
        regression_complete=True,
        contradiction=False,
    )

    assert result == {"allowed": False, "reason": "rca_status_not_reusable"}


def _complete_cross_project_gates() -> dict[str, object]:
    return {
        "weakness_status": "confirmed",
        "rca_status": "confirmed",
        "valid_reproductions": 2,
        "valid_counterfactuals": 0,
        "lifecycle_complete": True,
        "direct_evidence": True,
        "applicability_complete": True,
        "regression_complete": True,
        "contradiction": False,
    }


def test_cross_project_pending_promotes_to_reusable_when_all_gates_pass() -> None:
    result = evaluate_knowledge_promotion(
        current="cross_project_pending",
        **_complete_cross_project_gates(),
    )

    assert result == {
        "allowed": True,
        "next_status": "cross_project_reusable",
        "reason": "cross_project_reuse_gates_passed",
    }


def test_cross_project_pending_accepts_one_reproduction_and_one_counterfactual() -> None:
    values = _complete_cross_project_gates()
    values.update(valid_reproductions=1, valid_counterfactuals=1)

    result = evaluate_knowledge_promotion(current="cross_project_pending", **values)

    assert result["allowed"] is True
    assert result["next_status"] == "cross_project_reusable"


@pytest.mark.parametrize(
    ("field", "expected_reason"),
    [
        ("weakness_status", "weakness_status_not_eligible"),
        ("rca_status", "rca_status_not_reusable"),
        ("valid_reproductions", "reproduction_gate_incomplete"),
        ("direct_evidence", "evidence_gate_incomplete"),
        ("lifecycle_complete", "operational_card_fields_incomplete"),
        ("contradiction", "high_severity_contradiction"),
    ],
)
def test_cross_project_pending_reports_each_failed_gate(field: str, expected_reason: str) -> None:
    values = _complete_cross_project_gates()
    values[field] = {
        "weakness_status": "unsupported",
        "rca_status": "rejected",
        "valid_reproductions": 1,
        "direct_evidence": False,
        "lifecycle_complete": False,
        "contradiction": True,
    }[field]

    result = evaluate_knowledge_promotion(current="cross_project_pending", **values)

    assert result == {"allowed": False, "reason": expected_reason}


def test_cross_project_reusable_remains_reusable_without_contradiction() -> None:
    result = evaluate_knowledge_promotion(
        current="cross_project_reusable",
        **_complete_cross_project_gates(),
    )

    assert result == {
        "allowed": True,
        "next_status": "cross_project_reusable",
        "reason": "already_cross_project_reusable",
    }


def test_cross_project_reusable_is_contested_by_a_counterexample() -> None:
    values = _complete_cross_project_gates()
    values["contradiction"] = True

    result = evaluate_knowledge_promotion(current="cross_project_reusable", **values)

    assert result == {
        "allowed": True,
        "next_status": "contested",
        "reason": "meaningful_counterexample",
    }


def test_environment_blocked_weakness_cannot_promote_knowledge() -> None:
    result = evaluate_knowledge_promotion(
        current="provisional",
        weakness_status="environment_blocked",
        rca_status="confirmed",
        valid_reproductions=2,
        valid_counterfactuals=0,
        lifecycle_complete=True,
        direct_evidence=True,
        applicability_complete=True,
        regression_complete=True,
        contradiction=False,
    )

    assert result == {"allowed": False, "reason": "weakness_status_not_eligible"}


def test_unsupported_weakness_cannot_promote_knowledge() -> None:
    result = evaluate_knowledge_promotion(
        current="provisional",
        weakness_status="unsupported",
        rca_status="bounded",
        valid_reproductions=2,
        valid_counterfactuals=0,
        lifecycle_complete=True,
        direct_evidence=True,
        applicability_complete=True,
        regression_complete=True,
        contradiction=False,
    )

    assert result == {"allowed": False, "reason": "weakness_status_not_eligible"}


def test_candidate_weakness_cannot_promote_knowledge() -> None:
    result = evaluate_knowledge_promotion(
        current="provisional",
        weakness_status="candidate",
        rca_status="pending",
        valid_reproductions=2,
        valid_counterfactuals=0,
        lifecycle_complete=True,
        direct_evidence=True,
        applicability_complete=True,
        regression_complete=True,
        contradiction=False,
    )

    assert result == {"allowed": False, "reason": "weakness_status_not_eligible"}


def test_provisional_promotes_to_local_reusable_when_all_gates_pass() -> None:
    result = evaluate_knowledge_promotion(
        current="provisional",
        weakness_status="confirmed",
        rca_status="bounded",
        valid_reproductions=1,
        valid_counterfactuals=1,
        lifecycle_complete=True,
        direct_evidence=True,
        applicability_complete=True,
        regression_complete=True,
        contradiction=False,
    )

    assert result == {
        "allowed": True,
        "next_status": "local_reusable",
        "reason": "local_reuse_gates_passed",
    }


def test_two_reproductions_also_satisfy_local_reuse_gate() -> None:
    result = evaluate_knowledge_promotion(
        current="provisional",
        weakness_status="protected",
        rca_status="confirmed",
        valid_reproductions=2,
        valid_counterfactuals=0,
        lifecycle_complete=True,
        direct_evidence=True,
        applicability_complete=True,
        regression_complete=True,
        contradiction=False,
    )

    assert result["allowed"] is True
    assert result["next_status"] == "local_reusable"


def test_local_reusable_requires_cross_project_review_before_promotion() -> None:
    result = evaluate_knowledge_promotion(
        current="local_reusable",
        weakness_status="confirmed",
        rca_status="confirmed",
        valid_reproductions=2,
        valid_counterfactuals=0,
        lifecycle_complete=True,
        direct_evidence=True,
        applicability_complete=True,
        regression_complete=True,
        contradiction=False,
    )

    assert result == {
        "allowed": True,
        "next_status": "cross_project_pending",
        "reason": "requires_cross_project_review_or_replication",
    }


def test_meaningful_counterexample_contests_reusable_knowledge_without_mutating_refs() -> None:
    evidence_refs = ["reports/run-1.json", "reports/run-2.json"]
    result = evaluate_knowledge_promotion(
        current="local_reusable",
        weakness_status="confirmed",
        rca_status="confirmed",
        valid_reproductions=2,
        valid_counterfactuals=0,
        lifecycle_complete=True,
        direct_evidence=True,
        applicability_complete=True,
        regression_complete=True,
        contradiction=True,
    )

    assert result == {
        "allowed": True,
        "next_status": "contested",
        "reason": "meaningful_counterexample",
    }
    assert evidence_refs == ["reports/run-1.json", "reports/run-2.json"]


@pytest.mark.parametrize("current", ["none", "contested"])
def test_counterexample_makes_non_reusable_knowledge_provisional(current: str) -> None:
    result = evaluate_knowledge_promotion(
        current=current,
        weakness_status="confirmed",
        rca_status="bounded",
        valid_reproductions=0,
        valid_counterfactuals=0,
        lifecycle_complete=False,
        direct_evidence=False,
        applicability_complete=False,
        regression_complete=False,
        contradiction=True,
    )

    assert result == {
        "allowed": True,
        "next_status": "provisional",
        "reason": "meaningful_counterexample",
    }


@pytest.mark.parametrize(
    ("field", "expected_reason"),
    [
        ("weakness_status", "weakness_status_not_eligible"),
        ("valid_reproductions", "reproduction_gate_incomplete"),
        ("direct_evidence", "evidence_gate_incomplete"),
        ("lifecycle_complete", "operational_card_fields_incomplete"),
        ("rca_status", "rca_status_not_reusable"),
    ],
)
def test_local_reuse_reports_the_first_failed_gate(field: str, expected_reason: str) -> None:
    values: dict[str, object] = {
        "current": "provisional",
        "weakness_status": "confirmed",
        "rca_status": "confirmed",
        "valid_reproductions": 2,
        "valid_counterfactuals": 0,
        "lifecycle_complete": True,
        "direct_evidence": True,
        "applicability_complete": True,
        "regression_complete": True,
        "contradiction": False,
    }
    values[field] = {
        "weakness_status": "unsupported",
        "valid_reproductions": 0,
        "direct_evidence": False,
        "lifecycle_complete": False,
        "rca_status": "pending",
    }[field]

    result = evaluate_knowledge_promotion(**values)  # type: ignore[arg-type]

    assert result == {"allowed": False, "reason": expected_reason}


@pytest.mark.parametrize(
    ("argument", "value", "reason"),
    [
        ("current", "future", "unknown_knowledge_state"),
        ("weakness_status", "mystery", "unknown_weakness_status"),
        ("rca_status", "mystery", "unknown_rca_status"),
    ],
)
def test_knowledge_unknown_states_fail_closed(argument: str, value: str, reason: str) -> None:
    values: dict[str, object] = {
        "current": "provisional",
        "weakness_status": "confirmed",
        "rca_status": "confirmed",
        "valid_reproductions": 2,
        "valid_counterfactuals": 0,
        "lifecycle_complete": True,
        "direct_evidence": True,
        "applicability_complete": True,
        "regression_complete": True,
        "contradiction": False,
    }
    values[argument] = value

    result = evaluate_knowledge_promotion(**values)  # type: ignore[arg-type]

    assert result == {"allowed": False, "reason": reason}


# ---------------------------------------------------------------------------
# Task 3: deterministic evidence action planner
# ---------------------------------------------------------------------------

from tools.rca_loop import plan_next_action, score_action  # noqa: E402


def _valid_action(**overrides: object) -> dict[str, object]:
    action: dict[str, object] = {
        "action_id": "A-x",
        "kind": "log_lookup",
        "hypotheses_separated": 1,
        "evidence_gain": 2,
        "cost": 1,
        "risk": 0,
        "environment_uncertainty": 0,
        "preconditions": ["captured_window"],
        "cleanup": ["none"],
        "output_schema": "runtime_log",
    }
    action.update(overrides)
    return action


def test_score_action_combines_gain_and_cost_deterministically() -> None:
    scored = score_action(_valid_action())
    assert scored["information_gain"] == 3
    assert scored["total_cost"] == 1
    assert scored["priority"] == 2
    assert scored["errors"] == []


def test_planner_prefers_safe_high_information_action() -> None:
    actions = [
        {"action_id": "A-runtime", "kind": "business_replay", "hypotheses_separated": 2,
         "evidence_gain": 3, "cost": 2, "risk": 1, "environment_uncertainty": 0,
         "preconditions": ["baseline_pass"], "cleanup": ["washout"], "output_schema": "runtime"},
        {"action_id": "A-source", "kind": "source_lookup", "hypotheses_separated": 2,
         "evidence_gain": 3, "cost": 1, "risk": 0, "environment_uncertainty": 0,
         "preconditions": ["source_snapshot"], "cleanup": ["none"], "output_schema": "source"},
    ]
    selected = plan_next_action(actions, available_preconditions={"baseline_pass", "source_snapshot"})
    assert selected["status"] == "planned"
    assert selected["selected"]["action_id"] == "A-source"


def test_planner_rejects_action_without_cleanup_contract() -> None:
    action = {"action_id": "A-bad", "kind": "pod_kill", "hypotheses_separated": 3,
              "evidence_gain": 5, "cost": 0, "risk": 0, "environment_uncertainty": 0,
              "preconditions": [], "output_schema": "runtime"}
    result = plan_next_action([action], available_preconditions=set())
    assert result["status"] == "pending"
    assert result["reason"] == "no_safe_applicable_action"
    assert "cleanup_contract_required" in result["rejected"][0]["errors"]


def test_planner_rejects_action_with_missing_preconditions() -> None:
    result = plan_next_action([_valid_action()], available_preconditions=set())
    assert result["status"] == "pending"
    assert result["rejected"][0]["missing_preconditions"] == ["captured_window"]


def test_planner_rejects_action_without_output_schema() -> None:
    action = _valid_action(output_schema="")
    result = plan_next_action([action], available_preconditions={"captured_window"})
    assert result["status"] == "pending"
    assert "output_schema_required" in result["rejected"][0]["errors"]


def test_planner_prefers_read_only_kinds_on_equal_priority() -> None:
    actions = [
        _valid_action(action_id="A-replay", kind="business_replay"),
        _valid_action(action_id="A-source", kind="source_lookup"),
        _valid_action(action_id="A-log", kind="log_lookup"),
    ]
    result = plan_next_action(actions, available_preconditions={"captured_window"})
    assert result["selected"]["action_id"] == "A-source"


def test_planner_breaks_remaining_ties_by_action_id_for_reproducibility() -> None:
    actions = [
        _valid_action(action_id="A-b"),
        _valid_action(action_id="A-a"),
    ]
    result = plan_next_action(actions, available_preconditions={"captured_window"})
    assert result["selected"]["action_id"] == "A-a"


def test_planner_discriminating_action_outranks_single_hypothesis_support() -> None:
    actions = [
        _valid_action(action_id="A-single", hypotheses_separated=1, evidence_gain=3),
        _valid_action(action_id="A-sep", hypotheses_separated=2, evidence_gain=2),
    ]
    result = plan_next_action(actions, available_preconditions={"captured_window"})
    assert result["selected"]["action_id"] == "A-sep"
