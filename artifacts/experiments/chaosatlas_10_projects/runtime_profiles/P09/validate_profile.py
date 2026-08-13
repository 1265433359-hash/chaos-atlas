"""Compatibility entry point for the P09 profile validator."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))

from tools.p09_profile_validator import main


if __name__ == "__main__":
    raise SystemExit(main())
