from pathlib import Path

from tools.repository_inventory import build_inventory, classify_path


def test_classification_covers_mainline_and_local_boundaries():
    assert classify_path("tools/chaosatlas.py") == "mainline_source"
    assert classify_path("docs/REPOSITORY_MAP.md") == "reviewed_documentation"
    assert classify_path("artifacts/sock-shop/run/report.json") == "generated_evidence"
    assert classify_path("artifacts/experiments/x/sources/upstream/app.py") == "external_source"
    assert classify_path("artifacts/experiments/x/sources_restored_r2/upstream/app.py") == "external_source"
    assert classify_path("tools/bin/helm.exe") == "external_source"
    assert classify_path(".pytest-tmp-run/report.json") == "local_generated"
    assert classify_path(".venv/Lib/site-packages/pkg.py") == "local_generated"
    assert classify_path("analysis_outputs/status.json") == "generated_evidence"
    assert classify_path("README.md") == "reviewed_documentation"
    assert classify_path(".pytest-cache-disabled/README.md") == "local_state"
    assert classify_path("secrets.kubeconfig") == "never_commit"


def test_inventory_is_stable_and_reports_counts(tmp_path: Path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "a.py").write_text("x", encoding="utf-8")
    (tmp_path / ".tmp-run").mkdir()
    (tmp_path / ".tmp-run" / "out.json").write_text("{}", encoding="utf-8")
    first = build_inventory(tmp_path)
    second = build_inventory(tmp_path)
    assert first == second
    assert first["file_count"] == 2
    assert first["category_counts"] == {"local_generated": 1, "mainline_source": 1}
    assert first["records"][0]["path"] == ".tmp-run/out.json"
