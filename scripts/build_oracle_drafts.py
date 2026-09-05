"""Build the four review-only transaction Oracle drafts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chaosatlas.oracles.builder import OracleBuilder


APPS = ("immich", "medusa", "rocketchat", "erpnext")


def build(root: Path) -> list[Path]:
    builder = OracleBuilder()
    paths = []
    for app in APPS:
        profile_path = root / "projects" / "chaosatlas-apps" / app / "profile.json"
        profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
        contract = builder.build(project_id=app, project_revision=str(profile["project_commit"]))
        output = profile_path.parent / "oracle-drafts" / f"{contract['oracle_id']}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(contract, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        paths.append(output)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    for path in build(Path(args.root).resolve()):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
