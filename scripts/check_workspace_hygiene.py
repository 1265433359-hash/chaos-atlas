"""Fail when generated local state has leaked into the repository tree."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


FORBIDDEN_ROOT_NAMES = {
    ".email-notify-outbox",
    ".pytest_cache",
    ".runs",
    "ChaosAtlas-evidence",
    "ChaosAtlas-evidence-v2",
    "environment-reports",
    "runtime",
}


def find_workspace_leaks(root: str | Path) -> list[str]:
    root_path = Path(root).resolve()
    leaks: list[str] = []
    for entry in root_path.iterdir():
        if entry.name in FORBIDDEN_ROOT_NAMES or entry.name.startswith(".tmp-"):
            leaks.append(entry.name)

    pruned = {".git", ".planning", ".secrets", ".venv"}
    for current, directories, _files in os.walk(root_path):
        directories[:] = [name for name in directories if name not in pruned]
        current_path = Path(current)
        for name in list(directories):
            if name == "__pycache__" or name.endswith(".egg-info"):
                leaks.append((current_path / name).relative_to(root_path).as_posix())
                directories.remove(name)
    return sorted(set(leaks))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    leaks = find_workspace_leaks(args.root)
    print(json.dumps({"status": "clean" if not leaks else "failed", "leaks": leaks}, indent=2))
    return 0 if not leaks else 1


if __name__ == "__main__":
    raise SystemExit(main())
