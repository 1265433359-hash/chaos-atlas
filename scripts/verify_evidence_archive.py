from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

try:
    from scripts.repository_inventory import _sha256
except ModuleNotFoundError:
    from repository_inventory import _sha256


def _exists(path: Path) -> bool:
    resolved = str(path.resolve())
    if os.name == "nt" and not resolved.startswith("\\\\?\\"):
        resolved = "\\\\?\\" + resolved
    return os.path.isfile(resolved)


def _size(path: Path) -> int:
    resolved = str(path.resolve())
    if os.name == "nt" and not resolved.startswith("\\\\?\\"):
        resolved = "\\\\?\\" + resolved
    return os.stat(resolved).st_size


def verify(manifest_path: str | Path, evidence_root: str | Path) -> list[str]:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    root = Path(evidence_root)
    errors: list[str] = []
    for entry in manifest.get("files", []):
        destination = root / entry["destination"]
        if not _exists(destination):
            errors.append(f"missing: {entry['destination']}")
            continue
        if _size(destination) != entry["size"]:
            errors.append(f"size mismatch: {entry['destination']}")
        elif _sha256(destination) != entry["sha256"]:
            errors.append(f"hash mismatch: {entry['destination']}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify evidence archive hashes.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--evidence-root", required=True)
    args = parser.parse_args(argv)
    errors = verify(args.manifest, args.evidence_root)
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
