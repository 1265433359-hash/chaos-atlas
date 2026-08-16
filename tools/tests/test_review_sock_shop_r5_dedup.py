import math

import pytest

from tools.review_sock_shop_r5_dedup import (
    build_review,
    classify_pair,
    executable_mutation_key,
    executable_overlap_pairs,
    fisher_exact_two_sided,
    render_markdown,
    summarize_method,
    wilson_interval,
)


def _entry(hypothesis_id, first, second):
    return {
        "record": {"hypothesis_id": hypothesis_id},
        "evidence": {
            "valid": True,
            "reports": [
                {"classification": first, "valid": True},
                {"classification": second, "valid": True},
            ],
        },
    }


@pytest.mark.parametrize(
    ("classifications", "expected"),
    [
        (["weakness_observed", "weakness_observed"], "stable_weakness"),
        (["weakness_observed", "no_business_impact_observed"], "unstable"),
        (["no_business_impact_observed", "weakness_observed"], "unstable"),
        (["no_business_impact_observed", "no_business_impact_observed"], "no_impact"),
    ],
)
def test_classify_pair_requires_two_reproductions_for_stable_weakness(classifications, expected):
    assert classify_pair(classifications) == expected


def test_classify_pair_rejects_incomplete_or_unknown_results():
    with pytest.raises(ValueError, match="exactly two"):
        classify_pair(["weakness_observed"])
    with pytest.raises(ValueError, match="unsupported classification"):
        classify_pair(["weakness_observed", "baseline_failed"])


def test_executable_key_ignores_call_chain_wording_but_keeps_fault_parameters():
    full = "kind=PodChaos|action=pod-kill|target=catalogue-db|call_chain_position=data-dependency|parameters=spec.action=pod-kill|spec.mode=one"
    ablation = "kind=PodChaos|action=pod-kill|target=catalogue-db|call_chain_position=database-for-catalogue-browse|parameters=spec.action=pod-kill|spec.mode=one"

    assert executable_mutation_key(full) == executable_mutation_key(ablation)


def test_executable_overlap_reports_reworded_call_chain_collision():
    full = _entry("full", "weakness_observed", "weakness_observed")
    ablation = _entry("ablation", "weakness_observed", "weakness_observed")
    full["record"]["mutation_instance_key"] = "kind=PodChaos|action=pod-kill|target=catalogue-db|call_chain_position=data-dependency|parameters=spec.action=pod-kill"
    ablation["record"]["mutation_instance_key"] = "kind=PodChaos|action=pod-kill|target=catalogue-db|call_chain_position=database-for-catalogue-browse|parameters=spec.action=pod-kill"

    pairs = executable_overlap_pairs([full], [ablation])

    assert pairs == [{"full_hypothesis_id": "full", "ablation_hypothesis_id": "ablation", "strict_instance_match": False, "executable_mutation_key": "kind=PodChaos|action=pod-kill|target=catalogue-db|parameters=spec.action=pod-kill"}]


def test_fisher_two_sided_equal_arms_returns_no_difference():
    result = fisher_exact_two_sided(2, 9, 2, 9)

    assert result["odds_ratio"] == pytest.approx(1.0)
    assert result["p_value"] == pytest.approx(1.0)


def test_wilson_interval_matches_two_of_eleven():
    low, high = wilson_interval(2, 11)

    assert low == pytest.approx(0.051, abs=0.001)
    assert high == pytest.approx(0.477, abs=0.001)


def test_summarize_method_keeps_unstable_out_of_stable_rate():
    entries = [
        _entry("stable", "weakness_observed", "weakness_observed"),
        _entry("unstable", "weakness_observed", "no_business_impact_observed"),
        _entry("none", "no_business_impact_observed", "no_business_impact_observed"),
    ]

    result = summarize_method(entries)

    assert result["denominator"] == 3
    assert result["counts"] == {"stable_weakness": 1, "unstable": 1, "no_impact": 1}
    assert result["stable_weakness_rate"] == pytest.approx(1 / 3)
    assert result["items"][1]["classification"] == "unstable"
    assert all(math.isfinite(value) for value in result["wilson_95_interval"])


def test_build_review_uses_only_frozen_main_denominator_and_keeps_pending():
    stable = _entry("stable", "weakness_observed", "weakness_observed")
    none = _entry("none", "no_business_impact_observed", "no_business_impact_observed")
    selection = {
        "selection_basis": {"sample_seed": 20260815},
        "groups": {
            "strict_overlap_high_confidence": [{"full": none, "ablation": none}],
            "full_only_high_confidence": [stable],
            "ablation_only_random": [stable],
        },
        "excluded": {"ablation_runtime_extra_not_in_main_denominator": ["hyp-003"]},
        "human_review": "pending",
        "knowledge_base_updated": False,
    }

    review = build_review(selection)

    assert review["methods"]["native-full"]["denominator"] == 2
    assert review["methods"]["chaosatlas-ablation"]["denominator"] == 2
    assert review["statistics"]["fisher_exact_two_sided"]["p_value"] == pytest.approx(1.0)
    assert review["excluded_from_main_denominator"] == ["hyp-003"]
    assert review["human_review"] == "pending"
    assert review["knowledge_base_updated"] is False


def test_markdown_states_small_sample_boundary_without_superiority_claim():
    review = {
        "methods": {
            "native-full": {"denominator": 11, "counts": {"stable_weakness": 2, "unstable": 1, "no_impact": 8}, "stable_weakness_rate": 2 / 11, "wilson_95_interval": [0.051, 0.477]},
            "chaosatlas-ablation": {"denominator": 11, "counts": {"stable_weakness": 2, "unstable": 0, "no_impact": 9}, "stable_weakness_rate": 2 / 11, "wilson_95_interval": [0.051, 0.477]},
        },
        "statistics": {"fisher_exact_two_sided": {"odds_ratio": 1.0, "p_value": 1.0}},
        "excluded_from_main_denominator": ["hyp-003"],
        "human_review": "pending",
        "knowledge_base_updated": False,
    }

    markdown = render_markdown(review)

    assert "18.18%" in markdown
    assert "小样本" in markdown
    assert "不能据此宣称" in markdown
    assert "hyp-003" in markdown
    assert "pending" in markdown
