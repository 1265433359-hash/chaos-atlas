from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from chaosatlas.workspace import default_run_output


def build_manifest(inventory: dict, evidence_root: str | Path | None = None) -> dict:
    if evidence_root is None:
        evidence_root = default_run_output("migrated-evidence")
    files = inventory.get("files", [])
    sensitive = [entry["path"] for entry in files if entry.get("sensitive")]
    unknown = [entry["path"] for entry in files if entry.get("category") == "unknown"]
    if sensitive:
        raise ValueError(f"sensitive files cannot be selected: {sensitive[:5]}")
    if unknown:
        raise ValueError(f"unclassified files cannot be selected: {unknown[:5]}")
    categories = {}
    for entry in files:
        categories.setdefault(entry["category"], []).append(entry["path"])
    return {
        "schema_version": 1,
        "source_root": inventory.get("root"),
        "evidence_root": str(evidence_root),
        "files": files,
        "counts": {name: len(paths) for name, paths in categories.items()},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a fail-closed migration manifest.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--evidence-root", default=str(default_run_output("migrated-evidence")))
    args = parser.parse_args(argv)
    del args.root
    inventory = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
    manifest = build_manifest(inventory, args.evidence_root)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
