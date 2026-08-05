"""Package experiment evidence into an issue/report attachment bundle.

Inputs:
- project artifact dir (artifacts/<project>/)
- finding IDs to include (optional; default: all .md/.yaml evidence files)

Outputs:
- <out_dir>/evidence_manifest.json  (index of included evidence, hashes)
- <out_dir>/<basename>.md          (copied evidence files)

The manifest records SHA-256 of every bundled file so the recipient can verify
the evidence is unchanged, and a "disclosure note" fields the reporter fills in.

Usage:
    python tools/package_report_evidence.py --project online-boutique --out artifacts/report_bundles/online-boutique-r1
    python tools/package_report_evidence.py --project train-ticket --out artifacts/report_bundles/train-ticket-r1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EVIDENCE_SUFFIXES = {".md", ".json", ".yaml", ".yml", ".txt", ".py"}
SKIP_DIRS = {"build", "__pycache__"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_evidence(project_dir: Path) -> list[Path]:
    found: list[Path] = []
    for path in sorted(project_dir.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(project_dir).parts):
            continue
        if path.suffix.lower() in EVIDENCE_SUFFIXES:
            found.append(path)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="artifact dir name, e.g. online-boutique")
    parser.add_argument("--out", required=True, help="output bundle directory")
    parser.add_argument(
        "--only",
        nargs="*",
        default=None,
        help="restrict to these relative paths (e.g. experiment_results.md chaos/payment-delay-r1.yaml)",
    )
    args = parser.parse_args()

    project_dir = ROOT / "artifacts" / args.project
    if not project_dir.is_dir():
        print(f"error: artifacts/{args.project} not found")
        return 1

    evidence = collect_evidence(project_dir)
    if args.only:
        wanted = {Path(p) for p in args.only}
        evidence = [p for p in evidence if p.relative_to(project_dir) in wanted]

    if not evidence:
        print(f"error: no evidence files found under {project_dir}")
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_entries = []
    for src in evidence:
        rel = src.relative_to(project_dir)
        dest = out_dir / rel.name
        shutil.copy2(src, dest)
        manifest_entries.append(
            {
                "source": str(rel),
                "copied_as": dest.name,
                "sha256": sha256(src),
                "bytes": src.stat().st_size,
            }
        )

    manifest = {
        "project": args.project,
        "bundled_at": __import__("datetime").date.today().isoformat(),
        "evidence": manifest_entries,
        "disclosure_note": {
            "environment": "isolated lab cluster; no production system was touched",
            "credentials": "no secret values included; references only",
            "reproducibility": "see project experiment report for pinned commit and steps",
        },
    }
    manifest_path = out_dir / "evidence_manifest.json"
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)

    total = sum(e["bytes"] for e in manifest_entries)
    print(f"bundled {len(manifest_entries)} files ({total} bytes) -> {out_dir}")
    print(f"manifest: {manifest_path}")
    for entry in manifest_entries:
        print(f"  {entry['copied_as']:48s} {entry['sha256'][:12]}  {entry['bytes']}B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
