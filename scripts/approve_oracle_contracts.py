"""Record an explicit human approval and freeze validated Oracle contracts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chaosatlas.oracles.transaction_contracts import (
    freeze_approved_contract,
    record_human_approval,
    validate_transaction_contract,
)


APPS = ("immich", "medusa", "rocketchat", "erpnext")


def approve(root: Path, reviewer: str, reviewed_at: str, decision_reference: str) -> list[Path]:
    paths: list[Path] = []
    for app in APPS:
        drafts = sorted((root / "projects" / "chaosatlas-apps" / app / "oracle-drafts").glob("*.json"))
        if len(drafts) != 1:
            raise ValueError(f"expected exactly one {app} Oracle draft, found {len(drafts)}")
        contract = json.loads(drafts[0].read_text(encoding="utf-8"))
        errors = validate_transaction_contract(contract)
        if errors or contract.get("status") != "validated":
            raise ValueError(f"{app} draft is not valid and reviewable: {errors}")
        approved = record_human_approval(
            contract,
            {
                "decision": "approved",
                "reviewer": reviewer,
                "reviewed_at": reviewed_at,
                "decision_reference": decision_reference,
            },
        )
        frozen = freeze_approved_contract(approved)
        output = drafts[0].parent.parent / "oracle-contracts" / drafts[0].name
        output.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(frozen, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        if output.exists() and output.read_text(encoding="utf-8") != serialized:
            raise FileExistsError(f"refusing to replace a different frozen contract: {output}")
        output.write_text(serialized, encoding="utf-8")
        paths.append(output)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--reviewed-at", required=True, help="ISO-8601 timestamp including timezone")
    parser.add_argument("--decision-reference", required=True)
    args = parser.parse_args()
    for path in approve(Path(args.root).resolve(), args.reviewer, args.reviewed_at, args.decision_reference):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
