from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from chaosatlas.orchestration.engine import RunEngine, RunRequest
from chaosatlas.workspace import default_run_output


def _run_live(args: argparse.Namespace) -> tuple[dict, int]:
    """Run the unified engine behind an explicit live gate."""
    if not args.approve_live:
        print("live execution requires explicit --approve-live", file=sys.stderr)
        return {"status": "environment_blocked", "reason": "approve_live_required"}, 2
    if args.resume:
        print("live execution does not support --resume; use a new output directory", file=sys.stderr)
        return {"status": "environment_blocked", "reason": "live_resume_forbidden"}, 2
    output = Path(args.output)
    if output.exists() and any(output.iterdir()):
        print(f"refusing non-empty live output directory: {output}", file=sys.stderr)
        return {"status": "environment_blocked", "reason": "non_empty_output"}, 2

    batch_requested = bool(
        args.all_candidates
        or args.max_candidates is not None
        or args.policy_mode != "legacy"
        or args.policy_state
        or args.policy_context
    )
    if batch_requested and args.advisory_provider == "deepseek":
        print("DeepSeek advisory is currently supported by single-candidate runs only", file=sys.stderr)
        return {"status": "environment_blocked", "reason": "batch_advisory_unsupported"}, 2
    policy_context = None
    if args.policy_context:
        try:
            policy_context = json.loads(Path(args.policy_context).read_text(encoding="utf-8-sig"))
            if not isinstance(policy_context, dict):
                raise ValueError("policy context must be a JSON object")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(f"invalid policy context: {exc}", file=sys.stderr)
            return {"status": "method_invalid", "reason": str(exc)}, 2

    advisory_provider = None
    if args.advisory_provider == "deepseek":
        try:
            from tools.deepseek_advisory import create_deepseek_advisory_provider

            advisory_provider = create_deepseek_advisory_provider(
                api_key_file=Path(args.api_key_file) if args.api_key_file else None,
                base_url=args.base_url,
                model=args.model,
            )
        except (OSError, ValueError, ImportError) as exc:
            print(json.dumps({"status": "blocked_missing_advisory_provider", "reason": str(exc)}, ensure_ascii=False))
            return {"status": "blocked_missing_advisory_provider", "reason": str(exc)}, 2

    result = RunEngine().run(RunRequest(
        profile_path=Path(args.profile),
        output_root=output,
        mode="live",
        seed=args.seed,
        resume=False,
        knowledge_root=Path(args.knowledge_root) if args.knowledge_root else None,
        approve_live=True,
        candidate_id=args.candidate_id,
        defense_history_root=Path(args.defense_history_root) if args.defense_history_root else None,
        knowledge_write_root=Path(args.knowledge_write_root) if args.knowledge_write_root else None,
        advisory_provider=advisory_provider,
        registry_shadow=bool(args.registry_shadow),
        kube_context=args.kube_context,
        all_candidates=bool(args.all_candidates),
        max_candidates=args.max_candidates,
        policy_mode=args.policy_mode,
        policy_state_path=Path(args.policy_state) if args.policy_state else None,
        policy_context=policy_context,
        policy_budget=args.policy_budget,
    ))
    status = str(result.get("status") or "method_invalid")
    return result, 0 if status in {"live_completed", "completed"} else 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chaosatlas", description="Evidence-constrained ChaosAtlas orchestration.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Run a project inspection.")
    run.add_argument("--profile", required=True)
    run.add_argument("--mode", choices=("dry-run", "live"), default="dry-run")
    run.add_argument(
        "--output",
        "--evidence-root",
        dest="output",
        default=str(default_run_output("cli-run")),
        help="runtime output (default: external ChaosAtlas state directory)",
    )
    run.add_argument("--seed", type=int, default=1001)
    run.add_argument("--resume", action="store_true")
    run.add_argument("--knowledge-root")
    run.add_argument("--approve-live", action="store_true")
    run.add_argument("--candidate-id")
    run.add_argument("--kube-context")
    run.add_argument("--advisory-provider", choices=("deterministic", "deepseek"), default="deterministic")
    run.add_argument("--api-key-file")
    run.add_argument("--base-url", default="https://api.deepseek.com/v1")
    run.add_argument("--model", default="deepseek-v4-flash")
    run.add_argument("--defense-history-root")
    run.add_argument("--knowledge-write-root")
    run.add_argument("--registry-shadow", action="store_true")
    run.add_argument("--all-candidates", action="store_true")
    run.add_argument("--max-candidates", type=int)
    run.add_argument("--policy-mode", choices=("legacy", "observe", "shadow", "guarded", "default"), default="legacy")
    run.add_argument("--policy-state")
    run.add_argument("--policy-context")
    run.add_argument("--policy-budget", type=int, default=20)

    inventory = subparsers.add_parser("inventory", help="Build a repository inventory.")
    inventory.add_argument("--root", default=".")
    inventory.add_argument("--output", required=True)

    migrate = subparsers.add_parser("migrate", help="Prepare a migration manifest.")
    migrate.add_argument("--root", default=".")
    migrate.add_argument("--evidence-root", default=str(default_run_output("migrated-evidence")))
    migrate.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "run":
        profile = Path(args.profile)
        if not profile.is_file():
            raise SystemExit(f"profile not found: {profile}")
        if args.mode == "live":
            result, code = _run_live(args)
            print(json.dumps({**result, "output": str(args.output)}, indent=2, ensure_ascii=False, sort_keys=True))
            return code
        result = RunEngine().run(RunRequest(
            profile_path=profile,
            output_root=Path(args.output),
            mode="dry-run",
            seed=args.seed,
            resume=args.resume,
            knowledge_root=Path(args.knowledge_root) if args.knowledge_root else None,
        ))
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("status") == "dry_run_ready" else 1
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
