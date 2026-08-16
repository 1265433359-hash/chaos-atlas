import pytest

from tools.review_sock_shop_full_top11 import build_review, classify_pair, revalidate_evidence


def _evidence(*classifications: str) -> list[dict[str, object]]:
    return [
        {"valid": True, "classification": classification, "replicate": index}
        for index, classification in enumerate(classifications, 1)
    ]


def test_pair_classification_requires_two_replicates() -> None:
    assert classify_pair(["weakness_observed", "weakness_observed"]) == "stable_weakness"
    assert classify_pair(["weakness_observed", "no_business_impact_observed"]) == "unstable"
    assert classify_pair(["no_business_impact_observed", "no_business_impact_observed"]) == "no_impact"


def test_review_separates_blocked_denominator_and_recomputes_executable_overlap() -> None:
    plan = {
        "human_review": "pending",
        "knowledge_base_updated": False,
        "entries": [
            {
                "rank": 1,
                "hypothesis_id": "stable",
                "execution_status": "fresh_required",
                "executable_mutation_key": "kind=PodChaos|action=pod-kill|target=front-end",
                "confidence_score": 0.9,
            },
            {
                "rank": 2,
                "hypothesis_id": "unstable",
                "execution_status": "reused_historical",
                "executable_mutation_key": "kind=PodChaos|action=pod-kill|target=carts",
                "confidence_score": 0.8,
            },
            {
                "rank": 3,
                "hypothesis_id": "no-impact",
                "execution_status": "fresh_required",
                "executable_mutation_key": "kind=StressChaos|action=stress-cpu|target=session-db",
                "confidence_score": 0.7,
            },
            {
                "rank": 4,
                "hypothesis_id": "blocked",
                "execution_status": "blocked",
                "gate_errors": ["target_port_missing:80"],
                "executable_mutation_key": "kind=HTTPChaos|action=delay|target=catalogue-db",
                "confidence_score": 0.6,
            },
        ],
    }
    evidence = {
        1: _evidence("weakness_observed", "weakness_observed"),
        2: _evidence("weakness_observed", "no_business_impact_observed"),
        3: _evidence("no_business_impact_observed", "no_business_impact_observed"),
    }
    ablation = [
        {
            "hypothesis_id": "hyp-001",
            "mutation_instance_key": (
                "kind=PodChaos|action=pod-kill|target=front-end|call_chain_position=entry"
            ),
        },
        {
            "hypothesis_id": "hyp-002",
            "mutation_instance_key": (
                "kind=NetworkChaos|action=delay|target=catalogue|call_chain_position=middle"
            ),
        },
    ]

    review = build_review(plan, evidence, ablation)

    assert review["selection"]["top_k"] == 4
    assert review["selection"]["executable"] == 3
    assert review["selection"]["blocked"] == 1
    assert review["selection"]["executable_rate"] == 0.75
    assert review["results"]["denominator"] == 3
    assert review["results"]["counts"] == {
        "stable_weakness": 1,
        "unstable": 1,
        "no_impact": 1,
    }
    assert review["results"]["stable_weakness_rate"] == 1 / 3
    assert review["ablation_identity_overlap"]["executable_overlap_count"] == 1
    assert review["ablation_identity_overlap"]["pairs"] == [
        {
            "full_rank": 1,
            "full_hypothesis_id": "stable",
            "ablation_hypothesis_id": "hyp-001",
            "executable_mutation_key": "kind=PodChaos|action=pod-kill|target=front-end",
        }
    ]
    assert review["human_review"] == "pending"
    assert review["knowledge_base_updated"] is False


def test_review_rejects_duplicate_replicates_and_excludes_blocked_overlap() -> None:
    plan = {
        "human_review": "pending",
        "knowledge_base_updated": False,
        "entries": [
            {
                "rank": 1,
                "hypothesis_id": "ready",
                "execution_status": "fresh_required",
                "executable_mutation_key": "kind=PodChaos|action=pod-kill|target=front-end",
            },
            {
                "rank": 2,
                "hypothesis_id": "blocked",
                "execution_status": "blocked",
                "executable_mutation_key": "kind=PodChaos|action=pod-kill|target=carts",
            },
        ],
    }
    evidence = {1: [{"valid": True, "classification": "weakness_observed", "replicate": 1},
                    {"valid": True, "classification": "weakness_observed", "replicate": 1}]}
    ablation = [
        {"hypothesis_id": "a-ready", "mutation_instance_key": "kind=PodChaos|action=pod-kill|target=front-end|call_chain_position=entry"},
        {"hypothesis_id": "a-blocked", "mutation_instance_key": "kind=PodChaos|action=pod-kill|target=carts|call_chain_position=entry"},
    ]

    with pytest.raises(ValueError, match="replicate"):
        build_review(plan, evidence, ablation)


def test_revalidate_requires_batch_plan_provenance() -> None:
    plan = {"entries": []}
    with pytest.raises(ValueError, match="provenance"):
        revalidate_evidence(plan, {"arm": "ChaosAtlas-full-top11", "rows": []})
