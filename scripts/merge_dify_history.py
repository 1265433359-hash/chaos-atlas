"""Merge Dify repeat-summary and adaptive-state rows into one history input."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _rows(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        return []
    rows = value.get("results")
    if not isinstance(rows, list):
        rows = value.get("current_results")
    return [dict(item) for item in rows if isinstance(item, dict)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows: list[dict[str, Any]] = []
    for path in args.input:
        rows.extend(_rows(path))
    payload = {
        "schema_version": "chaosatlas-dify-merged-history-v1",
        "source_files": [str(path.resolve()) for path in args.input],
        "results": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "rows": len(rows), "output": str(args.output.resolve())}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
