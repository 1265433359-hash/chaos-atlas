from pathlib import Path

from tools.review_sock_shop_confidence_experiment import review_confidence_experiment


def _report(path: Path, method: str, mutation_id: str, replicate: int, classification: str, status: str = "completed") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """{
  "status": "%s",
  "arm": "%s",
  "mutation_id": "%s",
  "replicate": %d,
  "observation": {"classification": "%s"},
  "mutation": {"sha256": "%s"},
  "category": "Network degradation"
}
"""
        % (status, method, mutation_id, replicate, classification, ("a" * 64)),
        encoding="utf-8",
    )


def test_review_classifies_stable_weaknesses_and_efficiency(tmp_path):
    native = tmp_path / "native"
    ablation = tmp_path / "ablation"
    _report(native / "runtime_reports" / "h1-r1.json", "native-full", "h1", 1, "weakness_observed")
    _report(native / "runtime_reports" / "h1-r2.json", "native-full", "h1", 2, "weakness_observed")
    _report(native / "runtime_reports" / "h2-r1.json", "native-full", "h2", 1, "weakness_observed")
    _report(native / "runtime_reports" / "h2-r2.json", "native-full", "h2", 2, "weakness_observed")
    _report(ablation / "runtime_reports" / "h1-r1.json", "chaosatlas-ablation", "h1", 1, "weakness_observed")
    _report(ablation / "runtime_reports" / "h1-r2.json", "chaosatlas-ablation", "h1", 2, "weakness_observed")
    _report(ablation / "runtime_reports" / "h2-r1.json", "chaosatlas-ablation", "h2", 1, "weakness_observed")
    _report(ablation / "runtime_reports" / "h2-r2.json", "chaosatlas-ablation", "h2", 2, "no_business_impact_observed")

    summary = review_confidence_experiment(
        {"native-full": native, "chaosatlas-ablation": ablation},
        timing={
            "native-full": {"total_wall_clock_seconds": 4800},
            "chaosatlas-ablation": {"total_wall_clock_seconds": 3600},
        },
        output_markdown=tmp_path / "review.md",
    )

    assert summary["methods"]["native-full"]["stable_weaknesses"] == 2
    assert summary["methods"]["chaosatlas-ablation"]["stable_weaknesses"] == 1
    assert summary["methods"]["native-full"]["unstable_or_nonrepeatable"] == 0
    assert summary["methods"]["chaosatlas-ablation"]["unstable_or_nonrepeatable"] == 1
    assert summary["methods"]["native-full"]["stable_weaknesses_per_hour"] == 1.5
    assert summary["human_review"] == "pending"
    assert summary["knowledge_base_updated"] is False
    assert (tmp_path / "review.md").exists()


def test_review_ignores_nested_diagnostics_json_files(tmp_path):
    method_root = tmp_path / "method"
    _report(method_root / "runtime_reports" / "h1-r1.json", "native-full", "h1", 1, "weakness_observed")
    nested = method_root / "runtime_reports" / "h1-r1.diagnostics"
    nested.mkdir(parents=True)
    (nested / "zipkin-unavailable.json").write_text(
        """{
  "status": "unavailable",
  "reason": "no trace backend"
}
""",
        encoding="utf-8",
    )

    summary = review_confidence_experiment({"native-full": method_root})

    assert summary["methods"]["native-full"]["reports"] == 1
    assert summary["methods"]["native-full"]["completed_replicates"] == 1


def test_review_infers_category_from_mutation_id_when_missing(tmp_path):
    method_root = tmp_path / "method"
    path = method_root / "runtime_reports" / "net-delay-user-r1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """{
  "status": "completed",
  "arm": "native-full",
  "mutation_id": "net-delay-user",
  "replicate": 1,
  "observation": {"classification": "weakness_observed"},
  "mutation": {"sha256": "%s"}
}
"""
        % ("a" * 64),
        encoding="utf-8",
    )

    summary = review_confidence_experiment({"native-full": method_root})

    assert summary["methods"]["native-full"]["categories"]["Network degradation"]["stable_weakness"] == 0


def test_review_derives_method_wall_clock_from_reports_when_timing_missing(tmp_path):
    method_root = tmp_path / "method"
    path = method_root / "runtime_reports" / "h1-r1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """{
  "status": "completed",
  "arm": "native-full",
  "mutation_id": "pod-kill-front-end",
  "replicate": 1,
  "started_at": "2026-08-14T00:00:00+00:00",
  "finished_at": "2026-08-14T00:01:30+00:00",
  "observation": {"classification": "no_business_impact_observed"},
  "mutation": {"sha256": "%s"}
}
"""
        % ("a" * 64),
        encoding="utf-8",
    )

    summary = review_confidence_experiment({"native-full": method_root})

    assert summary["methods"]["native-full"]["total_wall_clock_seconds"] == 90.0
