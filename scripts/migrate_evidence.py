from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

try:
    from scripts.repository_inventory import _sha256
except ModuleNotFoundError:
    from repository_inventory import _sha256

from chaosatlas.workspace import default_run_output

SELECTED_ROOTS = {
    "artifacts": "runs",
    "raw_yaml": "inputs",
    "analysis_outputs": "reports",
    "reporting": "reports",
}
EXCLUDED_PARTS = {".git", ".venv", ".pytest_cache", ".migration", ".worktrees", "ChaosAtlas-evidence"}


def selected_files(root: Path) -> list[tuple[Path, Path]]:
    selected: list[tuple[Path, Path]] = []
    for source_root, destination_root in SELECTED_ROOTS.items():
        base = root / source_root
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or any(part in EXCLUDED_PARTS or part.startswith(".tmp-") for part in path.parts):
                continue
            relative = path.relative_to(base)
            selected.append((path, Path(destination_root) / relative))
    return selected


def _filesystem_path(path: Path) -> str:
    resolved = str(path.resolve())
    if os.name == "nt" and not resolved.startswith("\\\\?\\"):
        return "\\\\?\\" + resolved
    return resolved


def migrate(root: str | Path, evidence_root: str | Path, manifest_path: str | Path, dry_run: bool = False) -> dict:
    root_path = Path(root).resolve()
    evidence_path = Path(evidence_root).resolve()
    entries = []
    for source, relative_destination in selected_files(root_path):
        destination = evidence_path / relative_destination
        entry = {
            "source": source.relative_to(root_path).as_posix(),
            "destination": relative_destination.as_posix(),
            "size": source.stat().st_size,
            "sha256": _sha256(source),
        }
        entries.append(entry)
        if not dry_run:
            os.makedirs(_filesystem_path(destination.parent), exist_ok=True)
            shutil.copy2(_filesystem_path(source), _filesystem_path(destination))
            if _sha256(destination) != entry["sha256"]:
                raise RuntimeError(f"hash mismatch after copy: {source}")
    manifest = {
        "schema_version": 1,
        "source_root": str(root_path),
        "evidence_root": str(evidence_path),
        "dry_run": dry_run,
        "files": entries,
        "counts": {"files": len(entries), "bytes": sum(entry["size"] for entry in entries)},
    }
    manifest_file = Path(manifest_path)
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    manifest_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Copy evidence into the independent archive.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--evidence-root", default=str(default_run_output("migrated-evidence")))
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    manifest = migrate(args.root, args.evidence_root, args.manifest, args.dry_run)
    print(json.dumps(manifest["counts"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
