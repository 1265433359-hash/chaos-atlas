"""Environment helpers for invoking ChaosAtlas child processes on Windows."""

from __future__ import annotations

import os
from pathlib import Path


def runtime_env() -> dict[str, str]:
    """Prefer the user-local package cache over archived, possibly read-only paths."""
    env = os.environ.copy()
    local_appdata = str(env.get("LOCALAPPDATA") or "").strip()
    if local_appdata:
        packages = Path(local_appdata) / "ChaosAtlas" / "python-packages"
        if (packages / "yaml").is_dir():
            entries = [str(packages)]
            existing = env.get("PYTHONPATH")
            if existing:
                entries.extend(item for item in existing.split(os.pathsep) if item and item != str(packages))
            env["PYTHONPATH"] = os.pathsep.join(entries)
    return env
