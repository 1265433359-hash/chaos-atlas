from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from chaosatlas.orchestration.engine import RunEngine, RunRequest
from chaosatlas.workspace import default_run_output, is_within


def _safe_output_name(value: object, fallback: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip(".-")
    return normalized or fallback


def _run_capabilities(args: argparse.Namespace) -> tuple[dict, int]:
    """Run read-only capability discovery for one or more profiles."""
    from chaosatlas.capabilities.bootstrap import CapabilityBootstrapper
    from chaosatlas.capabilities.evidence import CapabilityEvidenceIndex
    from tools.kubernetes_project_adapter import KubernetesProjectAdapter

    output = Path(args.output).expanduser().resolve()
    repository_root = Path(__file__).resolve().parents[2]
    if is_within(output, repository_root):
        reason = f"capability output must be outside the repository: {output}"
        print(reason, file=sys.stderr)
        return {"status": "environment_blocked", "reason": "repository_output_forbidden"}, 2
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        reason = f"refusing non-empty capability output directory: {output}"
        print(reason, file=sys.stderr)
        return {"status": "environment_blocked", "reason": "non_empty_output"}, 2
    output.mkdir(parents=True, exist_ok=True)
    evidence_index = CapabilityEvidenceIndex.from_root(args.evidence_root)
    results: list[dict] = []
    used_names: set[str] = set()
    for index, raw_profile_path in enumerate(args.profile, start=1):
        profile_path = Path(raw_profile_path).expanduser().resolve()
        profile: dict = {}
        try:
            value = json.loads(profile_path.read_text(encoding="utf-8-sig"))
            if not isinstance(value, dict):
                raise ValueError("profile must be a JSON object")
            profile = value
            project_id = str(profile.get("project_id") or "").strip()
            if not project_id:
                raise ValueError("profile project_id is required")
            kube_context = args.kube_context or str(((profile.get("runtime_contract") or {}).get("kube_context")) or "").strip() or None
            adapter = KubernetesProjectAdapter(profile=profile, kube_context=kube_context)
            result = CapabilityBootstrapper(profile=profile, adapter=adapter, evidence_index=evidence_index).run()
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError, RuntimeError, KeyError) as exc:
            project_id = str(profile.get("project_id") or profile_path.stem or f"profile-{index}")
            result = {
                "schema_version": "chaosatlas-capability-bootstrap-v1",
                "status": "method_invalid",
                "project_id": project_id,
                "profile_path": str(profile_path),
                "errors": [f"{type(exc).__name__}: {exc}"],
                "warnings": [],
                "read_only": True,
                "injection_performed": False,
            }
        name = _safe_output_name(project_id, f"profile-{index}")
        if name in used_names:
            name = f"{name}-{index}"
        used_names.add(name)
        result_path = output / f"{name}.json"
        result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        results.append({
            "project_id": project_id,
            "status": result.get("status"),
            "result": result_path.name,
            "catalog": result.get("catalog"),
            "status_counts": result.get("status_counts", {}),
            "errors": list(result.get("errors") or []),
        })
    successes = sum(item["status"] == "verified" for item in results)
    status = "verified" if successes == len(results) else "partial" if successes else "failed"
    summary = {
        "schema_version": "chaosatlas-capability-bootstrap-summary-v1",
        "status": status,
        "project_count": len(results),
        "verified_count": successes,
        "failed_count": len(results) - successes,
        "projects": results,
        "evidence_root": str(Path(args.evidence_root).expanduser().resolve()) if args.evidence_root else None,
        "output": str(output),
        "read_only": True,
        "injection_performed": False,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return summary, 0 if status == "verified" else 2


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

    capabilities = subparsers.add_parser("capabilities", help="Discover a project's complete read-only 32+9 capability matrix.")
    capabilities.add_argument("--profile", action="append", required=True, help="project profile; repeat for multiple projects")
    capabilities.add_argument("--output", default=str(default_run_output("capability-bootstrap")), help="external, empty output directory")
    capabilities.add_argument("--kube-context")
    capabilities.add_argument("--evidence-root", help="optional external root containing verified live run evidence")
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
    if args.command == "capabilities":
        result, code = _run_capabilities(args)
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        return code
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
