from __future__ import annotations

from tools.feedback_protocol import build_feedback_card, classify_outcome, knowledge_projection


def result(label="availability_degraded"):
    return {
        "project_id": "p", "project_commit": "a" * 40, "canonical_signature": "s", "round_id": "r1",
        "target": "deployment:api", "target_kind": "deployment", "fault_family": "pod_kill",
        "availability_label": label, "valid_reproductions": 2,
        "evidence": {key: {"status": "pass"} for key in ("baseline", "injection", "observation", "recovery", "cleanup", "independent_oracle")},
        "abstraction": {"mechanism": "single replica lacks replacement capacity"},
    }


def test_availability_degradation_can_be_reviewed_as_weakness():
    card = build_feedback_card(result(), review_status="human_reviewed")
    assert card["classification"] == "confirmed_weakness"
    assert card["feedback_eligible"]


def test_blocked_or_contradictory_evidence_cannot_be_promoted():
    blocked = result("platform_blocked")
    blocked["environment_blocked"] = True
    assert classify_outcome(blocked) == "environment_blocked"
    assert classify_outcome({**result("contradictory_evidence"), "valid_reproductions": 3}) == "unsupported"


def test_projection_rejects_runtime_identity_and_verdict():
    card = build_feedback_card(result(), review_status="human_reviewed")
    card["abstraction"]["pod_uid"] = "uid"
    try:
        knowledge_projection(card)
    except ValueError as exc:
        assert "pod_uid" in str(exc)
    else:
        raise AssertionError("runtime identity leaked into knowledge projection")

