"""Build the four validated, never auto-approved v3 transaction drafts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chaosatlas.oracles.builder import OracleBuilder


APPS = ("immich", "medusa", "rocketchat", "erpnext")


def build(root: Path) -> list[Path]:
    builder = OracleBuilder()
    paths: list[Path] = []
    for app in APPS:
        project = root / "projects" / "chaosatlas-apps" / app
        profile = json.loads((project / "profile.json").read_text(encoding="utf-8-sig"))
        contract = builder.build_project_v3(
            project_id=app, project_revision=str(profile["project_commit"]),
        )
        output = project / "oracle-drafts" / f"{contract['oracle_id']}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(contract, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
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
