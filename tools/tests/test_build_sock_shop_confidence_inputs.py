from pathlib import Path
import subprocess
import sys

from tools.build_sock_shop_confidence_inputs import build_confidence_input_manifest


def test_manifest_separates_native_and_ablation_boundaries(tmp_path):
    out = tmp_path / "exp"

    manifest = build_confidence_input_manifest(
        raw_yaml_root=Path("raw_yaml"),
        output_dir=out,
        sock_shop_profile={
            "namespace": "chaosatlas-sock-shop",
            "services": ["front-end", "catalogue", "user"],
            "oracles": ["authenticated-orders-journey"],
        },
        dry_run=True,
    )

    assert manifest["human_review"] == "pending"
    assert manifest["knowledge_base_updated"] is False
    assert manifest["methods"]["native-full"]["knowledge_allowed"] is True
    assert manifest["methods"]["chaosatlas-ablation"]["knowledge_allowed"] is False
    assert manifest["methods"]["chaosatlas-ablation"]["forbidden_inputs"] == [
        "knowledge_base",
        "historical_weakness_evidence",
        "call_chain_projection",
        "full_projection",
    ]
    assert (out / "yaml_inventory.json").exists()
    assert (out / "category_summary.json").exists()
    assert (out / "yaml-category-summary.json").exists()
    assert (out / "confidence_protocol.json").exists()
    assert (out / "classification_report.md").exists()
    assert (out / "method-inputs" / "native-full.json").exists()
    assert (out / "method-inputs" / "chaosatlas-ablation.json").exists()

    native = __import__("json").loads(
        (out / "method-inputs" / "native-full.json").read_text(encoding="utf-8")
    )
    ablation = __import__("json").loads(
        (out / "method-inputs" / "chaosatlas-ablation.json").read_text(encoding="utf-8")
    )
    assert native["complete_project_knowledge"]["source_sha256"]
    assert native["knowledge_projection"]["contract"]
    assert native["knowledge_base_view"]["selection_experience"]
    assert native["historical_experience"]["judgment_experience"]
    assert native["call_chain_projection"]["edges"]
    for forbidden in ("complete_project_knowledge", "knowledge_projection", "knowledge_base_view", "historical_experience", "call_chain_projection"):
        assert forbidden not in ablation

    protocol = __import__("json").loads((out / "confidence_protocol.json").read_text(encoding="utf-8"))
    assert protocol["runtime_outcomes_used"] is False
    assert set(protocol["categories"]) == {
        "Pod disruption",
        "Network degradation",
        "Resource pressure",
        "Protocol/HTTP fault",
        "Composite/scheduled fault",
    }
    assert manifest["timing"]["total_wall_clock_seconds"] >= manifest["timing"]["yaml_statistics_seconds"]


def test_manifest_refuses_non_empty_output_directory(tmp_path):
    out = tmp_path / "exp"
    out.mkdir()
    (out / "existing.txt").write_text("keep", encoding="utf-8")

    try:
        build_confidence_input_manifest(
            raw_yaml_root=Path("raw_yaml"),
            output_dir=out,
            sock_shop_profile={"services": ["front-end"]},
        )
    except FileExistsError as exc:
        assert "non-empty" in str(exc)
    else:
        raise AssertionError("expected non-empty output directory to be refused")


def test_direct_script_invocation_bootstraps_repo_imports(tmp_path):
    out = tmp_path / "direct"
    completed = subprocess.run(
        [
            sys.executable,
            "tools/build_sock_shop_confidence_inputs.py",
            "--raw-yaml",
            "raw_yaml",
            "--output",
            str(out),
            "--dry-run",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert completed.returncode == 0, completed.stderr
    assert (out / "manifest.json").exists()
