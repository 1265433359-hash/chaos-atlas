from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.prepare_project_gates import PROJECTS
from tools.verify_restored_sources import build_source_report, write_source_evidence


class VerifyRestoredSourcesTest(unittest.TestCase):
    def test_build_source_report_verifies_commit_tree_files_and_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            git = Path(temp) / "git"
            git.mkdir()
            assets = {
                "Dockerfile": git / "Dockerfile",
                "compose.yml": git / "compose.yml",
            }
            for path in assets.values():
                path.write_text(path.name + "\n", encoding="utf-8")

            report = build_source_report(
                project_id="PX",
                source_root=git,
                expected_commit="abc123",
                expected_tree="tree123",
                expected_file_count=2,
                deployment_assets=list(assets),
                git_commit="abc123",
                git_tree="tree123",
                git_file_count=2,
            )

        self.assertEqual(report["source_restore_status"], "complete")
        self.assertIs(report["runtime_apply_allowed"], False)
        self.assertEqual(report["blocked_reasons"], [])
        self.assertTrue(report["deployment_asset_sha256"]["Dockerfile"])
        self.assertIs(report["deployment_assets_present"]["compose.yml"], True)

    def test_build_source_report_blocks_commit_or_asset_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.mkdir()

            report = build_source_report(
                project_id="PX",
                source_root=source,
                expected_commit="expected",
                expected_tree="expected-tree",
                expected_file_count=1,
                deployment_assets=["Dockerfile"],
                git_commit="actual",
                git_tree="actual-tree",
                git_file_count=0,
            )

        self.assertEqual(report["source_restore_status"], "blocked")
        self.assertIs(report["runtime_apply_allowed"], False)
        self.assertIn("commit_mismatch", report["blocked_reasons"])
        self.assertIn("tree_mismatch", report["blocked_reasons"])
        self.assertIn("file_count_mismatch", report["blocked_reasons"])
        self.assertIn("missing_deployment_assets", report["blocked_reasons"])

    def test_write_source_evidence_writes_project_scoped_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = {
                "project_id": "PX",
                "source_root": "tmp/source",
                "source_restore_status": "complete",
                "expected_commit": "abc123",
                "actual_commit": "abc123",
                "expected_tree_sha": "tree123",
                "actual_tree_sha": "tree123",
                "expected_git_file_count": 1,
                "actual_git_file_count": 1,
                "deployment_asset_sha256": {"Dockerfile": "0" * 64},
                "blocked_reasons": [],
                "runtime_apply_allowed": False,
            }

            written = write_source_evidence(root, report)

            self.assertEqual(
                sorted(path.name for path in written),
                ["RESTORATION_MANIFEST.md", "source-restore-gate.json"],
            )
            saved = json.loads((root / "source-restore-gate.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["project_id"], "PX")

    def test_p06_manifest_asset_set_includes_blackbox_compose(self) -> None:
        self.assertIn(
            "tests/blackbox/docker-compose.yml",
            PROJECTS["P06"]["deployment_assets"],
        )


if __name__ == "__main__":
    unittest.main()
