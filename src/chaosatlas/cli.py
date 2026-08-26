from __future__ import annotations

import argparse
import json
from pathlib import Path


def _legacy_tool_path() -> Path:
    """Find the compatibility entry point within the current repository tree."""
    module_path = Path(__file__).resolve()
    for parent in module_path.parents:
        legacy_candidate = parent / "tools" / "_legacy_chaosatlas.py"
        if legacy_candidate.is_file():
            return legacy_candidate
        candidate = parent / "tools" / "chaosatlas.py"
        if candidate.is_file() and "from chaosatlas.cli import main" not in candidate.read_text(encoding="utf-8"):
            return candidate
    raise FileNotFoundError("tools/chaosatlas.py was not found in the product repository")


def _run_legacy(argv: list[str]) -> int:
    """Delegate live execution to the maintained legacy CLI during migration."""
    import subprocess
    import sys

    tool = _legacy_tool_path()
    return subprocess.call([sys.executable, str(tool), *argv])


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chaosatlas", description="Evidence-constrained ChaosAtlas orchestration.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Run a project inspection.")
    run.add_argument("--profile", required=True)
    run.add_argument("--mode", choices=("dry-run", "live"), default="dry-run")
    run.add_argument("--evidence-root", default="ChaosAtlas-evidence")

    inventory = subparsers.add_parser("inventory", help="Build a repository inventory.")
    inventory.add_argument("--root", default=".")
    inventory.add_argument("--output", required=True)

    migrate = subparsers.add_parser("migrate", help="Prepare a migration manifest.")
    migrate.add_argument("--root", default=".")
    migrate.add_argument("--evidence-root", default="ChaosAtlas-evidence")
    migrate.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "run":
        profile = Path(args.profile)
        if not profile.is_file():
            raise SystemExit(f"profile not found: {profile}")
        payload = json.loads(profile.read_text(encoding="utf-8"))
        if args.mode == "dry-run":
            print(
                json.dumps(
                    {
                        "status": "dry-run",
                        "project_id": payload.get("project_id", profile.stem),
                        "profile": str(profile),
                        "evidence_root": args.evidence_root,
                        "mutations": False,
                        "llm_calls": False,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0
        return _run_legacy(
            [
                "run",
                "--profile",
                str(profile),
                "--mode",
                "live",
                "--output",
                args.evidence_root,
            ]
        )
    if args.command == "inventory":
        from scripts.repository_inventory import build_inventory

        build_inventory(args.root, args.output)
        print(args.output)
        return 0
    if args.command == "migrate":
        from scripts.repository_inventory import build_inventory
        from scripts.migration_manifest import build_manifest

        inventory = build_inventory(args.root)
        manifest = build_manifest(inventory, args.evidence_root)
        print(json.dumps({"dry_run": args.dry_run, "files": len(manifest["files"])}, ensure_ascii=False))
        return 0
    return 2
