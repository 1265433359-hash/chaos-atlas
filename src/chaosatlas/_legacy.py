from __future__ import annotations

import runpy
import sys
from pathlib import Path


def run_legacy(script: str | Path, argv: list[str] | None = None) -> int:
    script_path = Path(script).resolve()
    previous = sys.argv[:]
    try:
        sys.argv = [str(script_path), *(argv or [])]
        namespace = runpy.run_path(str(script_path), run_name="__main__")
        return int(namespace.get("exit_code", 0))
    finally:
        sys.argv = previous
