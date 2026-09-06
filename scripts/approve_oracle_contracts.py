"""Record an explicit human approval and freeze validated Oracle contracts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chaosatlas.oracles.approval_batch import publish_approval


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--reviewed-at", required=True, help="Known actual human decision time with timezone; do not invent")
    parser.add_argument("--decision-reference", required=True)
    parser.add_argument("--manifest", required=True, help="Exact reviewed paths, file hashes and contract hashes (v1/v2/v3)")
    args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    print(publish_approval(Path(args.root), manifest, reviewer=args.reviewer,
                          reviewed_at=args.reviewed_at, decision_reference=args.decision_reference))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
