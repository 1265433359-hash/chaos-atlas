from pathlib import Path

from tools.yaml_confidence_categories import (
    YAML_CATEGORY_CONFIG,
    bucket_duration,
    classify_kind,
    extract_yaml_features,
    load_yaml_feature_rows,
    selector_shape,
    summarize_feature_rows,
)


def test_five_category_config_is_fixed():
    assert set(YAML_CATEGORY_CONFIG) == {
        "Pod disruption",
        "Network degradation",
        "Resource pressure",
        "Protocol/HTTP fault",
        "Composite/scheduled fault",
    }
    assert YAML_CATEGORY_CONFIG["Pod disruption"]["kinds"] == ["PodChaos"]
    assert YAML_CATEGORY_CONFIG["Network degradation"]["kinds"] == ["NetworkChaos"]
    assert YAML_CATEGORY_CONFIG["Resource pressure"]["kinds"] == ["StressChaos"]
    assert YAML_CATEGORY_CONFIG["Protocol/HTTP fault"]["kinds"] == ["HTTPChaos", "DNSChaos"]
    assert YAML_CATEGORY_CONFIG["Composite/scheduled fault"]["kinds"] == ["Workflow", "Schedule"]


def test_kind_mapping_keeps_low_frequency_types_out_of_runtime_scope():
    assert classify_kind("PodChaos") == "Pod disruption"
    assert classify_kind("NetworkChaos") == "Network degradation"
    assert classify_kind("StressChaos") == "Resource pressure"
    assert classify_kind("HTTPChaos") == "Protocol/HTTP fault"
    assert classify_kind("DNSChaos") == "Protocol/HTTP fault"
    assert classify_kind("Workflow") == "Composite/scheduled fault"
    assert classify_kind("Schedule") == "Composite/scheduled fault"
    assert classify_kind("IOChaos") is None
    assert classify_kind("TimeChaos") is None


def test_selector_shape_and_duration_buckets():
    assert selector_shape({"selector": {"labelSelectors": {"app": "catalogue"}}}) == "app-label"
    assert selector_shape({"selector": {"labelSelectors": {"app": "catalogue", "tier": "backend"}}}) == "app-label"
    assert selector_shape({"selector": {"labelSelectors": {"tier": "backend", "role": "api"}}}) == "multi-label"
    assert selector_shape({"selector": {"namespaces": ["sock-shop"]}}) == "namespace-only"
    assert selector_shape({}) == "empty-or-high-risk"
    assert bucket_duration("10s") == "short"
    assert bucket_duration("5m") == "medium"
    assert bucket_duration("1h") == "long"
    assert bucket_duration(None) == "unknown"


def test_extract_network_delay_features():
    doc = {
        "kind": "NetworkChaos",
        "spec": {
            "action": "delay",
            "mode": "one",
            "duration": "5m",
            "selector": {"labelSelectors": {"app": "catalogue"}},
            "delay": {"latency": "100ms"},
        },
    }
    features = extract_yaml_features("raw_yaml/NetworkChaos/example.yaml", doc)
    assert features["category"] == "Network degradation"
    assert features["kind"] == "NetworkChaos"
    assert features["action_or_target"] == "delay"
    assert features["mode"] == "one"
    assert features["selector_shape"] == "app-label"
    assert features["duration_bucket"] == "medium"
    assert features["intensity_bucket"] == "low"
    assert features["included_in_runtime_scope"] is True


def test_real_yaml_inventory_counts_match_protocol():
    rows = load_yaml_feature_rows(Path("raw_yaml"))
    summary = summarize_feature_rows(rows)
    assert summary["total_yaml"] == 1935
    assert summary["included_runtime_scope"] == 1506
    assert summary["categories"]["Pod disruption"]["count"] == 341
    assert summary["categories"]["Network degradation"]["count"] == 428
    assert summary["categories"]["Resource pressure"]["count"] == 352
    assert summary["categories"]["Protocol/HTTP fault"]["count"] == 263
    assert summary["categories"]["Composite/scheduled fault"]["count"] == 122
    assert summary["excluded_from_runtime_scope"] == 429


def test_summary_includes_feature_motifs_and_thresholds():
    rows = [
        {
            "category": "Network degradation",
            "kind": "NetworkChaos",
            "action_or_target": "delay",
            "mode": "one",
            "selector_shape": "app-label",
            "duration_bucket": "medium",
            "intensity_bucket": "low",
            "included_in_runtime_scope": True,
        },
        {
            "category": "Network degradation",
            "kind": "NetworkChaos",
            "action_or_target": "delay",
            "mode": "one",
            "selector_shape": "app-label",
            "duration_bucket": "medium",
            "intensity_bucket": "medium",
            "included_in_runtime_scope": True,
        },
    ]
    summary = summarize_feature_rows(rows)
    network = summary["categories"]["Network degradation"]
    assert network["min_hypotheses"] >= 4
    assert network["max_hypotheses"] > network["min_hypotheses"]
    assert 0.12 <= network["tau"] <= 0.25
    assert 0.60 <= network["coverage_target"] <= 0.90
    assert network["confidence_policy"]["runtime_outcomes_used"] is False
    assert network["confidence_policy"]["novelty_slack"] == 4
    assert network["feature_entropy"]["action_or_target"] == 0.0
    assert any("action_or_target=delay" == motif["motif"] for motif in network["top_motifs"])


def test_confidence_policy_changes_with_category_feature_complexity():
    low_complexity = [
        {
            "category": "Network degradation",
            "kind": "NetworkChaos",
            "action_or_target": "delay",
            "mode": "one",
            "selector_shape": "app-label",
            "duration_bucket": "medium",
            "intensity_bucket": "low",
            "included_in_runtime_scope": True,
        }
        for _ in range(8)
    ]
    high_complexity = [
        {
            "category": "Network degradation",
            "kind": "NetworkChaos",
            "action_or_target": action,
            "mode": mode,
            "selector_shape": selector,
            "duration_bucket": duration,
            "intensity_bucket": intensity,
            "included_in_runtime_scope": True,
        }
        for action, mode, selector, duration, intensity in [
            ("delay", "one", "app-label", "short", "low"),
            ("loss", "fixed", "multi-label", "medium", "medium"),
            ("partition", "all", "namespace-only", "long", "high"),
            ("bandwidth", "fixed-percent", "app-label", "unknown", "medium"),
            ("duplicate", "one", "multi-label", "short", "high"),
            ("corrupt", "all", "namespace-only", "medium", "low"),
            ("delay", "fixed", "app-label", "long", "high"),
            ("loss", "one", "multi-label", "unknown", "medium"),
        ]
    ]

    low = summarize_feature_rows(low_complexity)["categories"]["Network degradation"]
    high = summarize_feature_rows(high_complexity)["categories"]["Network degradation"]

    assert high["feature_complexity"] > low["feature_complexity"]
    assert high["tau"] > low["tau"]
    assert high["coverage_target"] > low["coverage_target"]
