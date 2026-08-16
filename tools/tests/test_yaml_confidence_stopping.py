from tools.yaml_confidence_stopping import ConfidenceState, beta_upper95, judge_novelty


def test_beta_upper95_stays_inside_probability_range():
    assert 0.0 <= beta_upper95(1, 1) <= 1.0
    assert beta_upper95(1, 20) < beta_upper95(20, 1)


def test_confidence_state_stops_when_saturated_after_minimum_and_coverage():
    state = ConfidenceState(
        category="Protocol/HTTP fault",
        min_hypotheses=1,
        max_hypotheses=4,
        tau=0.95,
        coverage_target=0.50,
    )
    decision = state.observe(
        novel=False,
        covered_motifs={"mode=one"},
        required_motifs={"mode=one"},
    )
    assert decision.stop is True
    assert decision.reason == "confidence_saturated"
    assert decision.generated == 1
    assert decision.duplicate_count == 1


def test_confidence_state_forces_stop_at_max_even_when_novel():
    state = ConfidenceState(
        category="Network degradation",
        min_hypotheses=4,
        max_hypotheses=4,
        tau=0.05,
        coverage_target=0.80,
    )
    decision = None
    for _ in range(4):
        decision = state.observe(
            novel=True,
            covered_motifs={"action_or_target=delay"},
            required_motifs={"action_or_target=delay"},
        )
    assert decision is not None
    assert decision.stop is True
    assert decision.reason == "max_hypotheses"
    assert decision.novel_count == 4


def test_confidence_state_continues_before_minimum():
    state = ConfidenceState(
        category="Pod disruption",
        min_hypotheses=3,
        max_hypotheses=6,
        tau=0.99,
        coverage_target=0.0,
    )
    decision = state.observe(novel=False, covered_motifs=set(), required_motifs=set())
    assert decision.stop is False
    assert decision.reason == "continue"


def test_judge_novelty_detects_new_target_action_position_and_motif():
    seen = [
        {
            "target_service": "catalogue",
            "action_or_target": "delay",
            "call_chain_position": "business-service",
            "motifs": ["action_or_target=delay"],
        }
    ]
    hypothesis = {
        "target_service": "user",
        "action_or_target": "loss",
        "call_chain_position": "entry",
        "motifs": ["mode=one"],
    }
    novelty = judge_novelty(hypothesis, seen, required_motifs={"mode=one"})
    assert novelty.novel is True
    assert "new_target_service" in novelty.reasons
    assert "new_action_or_target" in novelty.reasons
    assert "new_call_chain_position" in novelty.reasons
    assert "new_required_motif" in novelty.reasons


def test_judge_novelty_marks_duplicate_when_no_new_information():
    seen = [
        {
            "target_service": "catalogue",
            "action_or_target": "delay",
            "call_chain_position": "business-service",
            "motifs": ["action_or_target=delay", "mode=one"],
        }
    ]
    hypothesis = {
        "target_service": "catalogue",
        "action_or_target": "delay",
        "call_chain_position": "business-service",
        "motifs": ["action_or_target=delay", "mode=one"],
    }
    novelty = judge_novelty(hypothesis, seen, required_motifs={"mode=one"})
    assert novelty.novel is False
    assert novelty.reasons == []
