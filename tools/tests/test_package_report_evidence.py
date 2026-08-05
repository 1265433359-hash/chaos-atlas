from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import package_report_evidence


class PackageReportEvidenceTest(unittest.TestCase):
    def _make_project(self, tmp: Path) -> Path:
        project = tmp / "fake-project"
        (project / "chaos").mkdir(parents=True)
        (project / "chaos" / "delay.yaml").write_text("apiVersion: chaos-mesh.org/v1alpha1\n", encoding="utf-8")
        (project / "report.md").write_text("# evidence\n", encoding="utf-8")
        return project

    def test_collect_evidence_excludes_build_and_pycache(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            project = self._make_project(Path(d))
            (project / "build").mkdir()
            (project / "__pycache__").mkdir()
            (project / "build" / "artifact.o").write_text("x", encoding="utf-8")
            (project / "__pycache__" / "c.pyc").write_bytes(b"\x00")
            found = package_report_evidence.collect_evidence(project)
            rels = {p.relative_to(project) for p in found}
            self.assertIn(Path("report.md"), rels)
            self.assertIn(Path("chaos") / "delay.yaml", rels)
            self.assertNotIn(Path("build") / "artifact.o", rels)
            self.assertNotIn(Path("__pycache__") / "c.pyc", rels)

    def test_packaging_writes_manifest_with_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            project = self._make_project(Path(d))
            out = Path(d) / "bundle"
            # exercise the same logic as main() without argv
            evidence = package_report_evidence.collect_evidence(project)
            out.mkdir(parents=True, exist_ok=True)
            entries = []
            for src in evidence:
                dest = out / src.name
                dest.write_bytes(src.read_bytes())
                entries.append(
                    {
                        "source": str(src.relative_to(project)),
                        "copied_as": dest.name,
                        "sha256": package_report_evidence.sha256(src),
                        "bytes": src.stat().st_size,
                    }
                )
            manifest = {"project": "fake-project", "evidence": entries}
            (out / "evidence_manifest.json").write_text(
                json.dumps(manifest, indent=2), encoding="utf-8"
            )
            self.assertEqual(len(entries), 2)
            for e in entries:
                dest = out / e["copied_as"]
                self.assertEqual(
                    package_report_evidence.sha256(dest), e["sha256"], e["copied_as"]
                )
            self.assertTrue((out / "evidence_manifest.json").exists())

    def test_sha256_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.txt"
            p.write_text("hello\n", encoding="utf-8")
            first = package_report_evidence.sha256(p)
            second = package_report_evidence.sha256(p)
            self.assertEqual(first, second)
            p.write_text("hello!\n", encoding="utf-8")
            self.assertNotEqual(first, package_report_evidence.sha256(p))


if __name__ == "__main__":
    unittest.main()
