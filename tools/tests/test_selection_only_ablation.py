from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "artifacts/experiments/knowledge_ablation_selection_only/selection_only_manifest.json"


def test_selection_only_build_and_leakage_audit_pass():
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/build_selection_only_ablation.py")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    summary = json.loads(result.stdout)
    assert summary == {"files": 48, "audits": 12, "failed": []}


def test_selection_only_prompts_have_seed_specific_order_and_no_forbidden_fields():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert all(entry["pass"] for entry in manifest["leakage_audit"])
    for entry in manifest["leakage_audit"]:
        hashes = list(entry["prompt_sha256"].values())
        order_hashes = list(entry["candidate_order_sha256"].values())
        assert len(set(hashes)) == 3
        assert len(set(order_hashes)) == 3


def test_selection_only_runner_fails_closed_without_credentials():
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/run_selection_only_ablation.py"),
            "--api-key-file",
            str(ROOT / "missing-selection-only-key.txt"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={"PATH": str(Path(sys.executable).parent)},
    )
    assert result.returncode == 3
    assert "blocked_missing_api_key" in result.stderr
