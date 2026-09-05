"""Run adaptive Dify coverage, aggregate evidence, and promote RCA cards.

Offline planning is the default. Live execution is explicit and requires
``--mode live --approve-live``. Historical rows are inputs to the selector and
are never re-injected.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_dify_k8s_repeated_coverage import _candidate_list
from scripts.run_dify_k8s_repeated_coverage import _is_retryable_environment_block, _next_attempt_number, _wait_for_environment
from chaosatlas.orchestration.engine import RunEngine, RunRequest
from chaosatlas.workspace import runs_root
from tools.chaosatlas_adapters import KnowledgeProvider
from tools.kubernetes_project_adapter import _commit
from tools.dify_adaptive_coverage import build_coverage_report, select_next_action
from tools.dify_experience_promotion import promote_confirmed_experiences


DEFAULT_PROFILE = REPO_ROOT / "projects" / "dify-kubernetes" / "profile.json"
DEFAULT_HISTORY = runs_root() / "dify-k8s-repeated-coverage-60hypotheses-verified-20260901" / "repeat_summary.json"
DEFAULT_KNOWLEDGE_ROOT = REPO_ROOT / "artifacts" / "dify-kubernetes" / "knowledge_base"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if not Path(path).is_file():
        return []
    value = _read(path)
    rows = value.get("results")
    if not isinstance(rows, list):
        rows = value.get("current_results")
    return [dict(item) for item in rows if isinstance(item, dict)] if isinstance(rows, list) else []


def _candidate_identity(candidate: dict[str, Any]) -> tuple[str, str, str]:
    """Match history across rollout-generated node IDs."""

    return (
        str(candidate.get("target") or candidate.get("service_target") or ""),
        str(candidate.get("fault_family") or ""),
        str(candidate.get("parameter_level") or "baseline"),
    )


def _align_history_rows(
    rows: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Translate historical candidate IDs to the current deployment identity."""

    by_identity: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    current_ids = {str(item.get("candidate_id") or "") for item in candidates}
    for candidate in candidates:
        by_identity.setdefault(_candidate_identity(candidate), []).append(candidate)
    aligned: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        old_id = str(item.get("candidate_id") or "")
        if old_id not in current_ids:
            matches = by_identity.get(_candidate_identity(item), [])
            if len(matches) == 1:
                item["candidate_id"] = matches[0].get("candidate_id")
                item["target"] = matches[0].get("target")
                item["fault_family"] = matches[0].get("fault_family")
                item["parameter_level"] = matches[0].get("parameter_level", "baseline")
                item["historical_candidate_id"] = old_id
        aligned.append(item)
    return aligned


def _write_json(path: Path, value: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _cleanup_status(root: Path, result: dict[str, Any]) -> str:
    status = str(result.get("cleanup_status") or "")
    if status:
        return status
    path = Path(root) / "cleanup_report.json"
    if path.is_file():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return str(value.get("status") or "unknown") if isinstance(value, dict) else "unknown"
        except (OSError, json.JSONDecodeError):
            return "failed"
    return "unknown"


def _policy_knowledge(profile: dict[str, Any], candidates: list[dict[str, Any]], knowledge_root: Path) -> list[dict[str, Any]]:
    """Refresh the reusable experience view before every policy round."""

    try:
        retrieval = KnowledgeProvider().retrieve(
            project_id=str(profile.get("project_id") or ""),
            # Inventory and RCA use the adapter's canonical commit identity.
            # Keep retrieval aligned when profiles use a human-readable digest.
            project_commit=_commit(profile.get("project_commit")) if profile.get("project_commit") else None,
            candidate_space={"candidate_count": len(candidates)},
            root=knowledge_root,
        )
    except (OSError, ValueError, TypeError):
        return []
    return [dict(card) for card in retrieval.get("cards") or [] if isinstance(card, dict)]


def _live_trial(
    *,
    profile: Path,
    candidate: dict[str, Any],
    output_root: Path,
    action: str,
    repetition: int,
    seed: int,
    kube_context: str,
    preflight_timeout: float,
    preflight_interval: float,
    max_trial_attempts: int,
    knowledge_root: Path,
    policy_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute one isolated trial and return only the summary-row contract."""

    candidate_id = str(candidate.get("candidate_id") or "")
    family = str(candidate.get("fault_family") or "unknown")
    target = str(candidate.get("target") or "unknown")
    trial_root = Path(output_root) / "trials" / f"{len(list((Path(output_root) / 'trials').glob('*'))) + 1:04d}-{_safe_name(candidate_id)}-r{repetition:02d}"
    trial_root.mkdir(parents=True, exist_ok=True)
    first_attempt = _next_attempt_number(trial_root)
    result: dict[str, Any] = {}
    attempt_number = first_attempt
    for attempt in range(first_attempt, first_attempt + max_trial_attempts):
        attempt_number = attempt
        attempt_root = trial_root / f"attempt-{attempt:02d}"
        preflight = _wait_for_environment(
            json.loads(Path(profile).read_text(encoding="utf-8-sig")),
            kube_context,
            timeout_s=preflight_timeout,
            poll_interval_s=preflight_interval,
        )
        if preflight.get("status") != "ready_for_injection":
            attempt_root.mkdir(parents=True, exist_ok=True)
            _write_json(attempt_root / "preflight.json", preflight)
            result = {"status": "environment_blocked", "error": "; ".join(str(item) for item in preflight.get("errors") or [])}
        else:
            try:
                attempt_root.mkdir(parents=True, exist_ok=True)
                llm_decision = policy_decision.get("llm_decision") if isinstance(policy_decision, dict) else None
                policy_hypothesis = (
                    llm_decision.get("hypothesis")
                    if isinstance(llm_decision, dict)
                    and policy_decision.get("decision_source") == "llm"
                    and str(llm_decision.get("candidate_id") or "") == candidate_id
                    else None
                )
                result = RunEngine().run_candidate(RunRequest(
                    profile_path=profile,
                    output_root=attempt_root,
                    mode="live",
                    approve_live=True,
                    candidate_id=candidate_id,
                    kube_context=kube_context,
                    seed=seed,
                    knowledge_root=knowledge_root,
                    policy_hypothesis=policy_hypothesis,
                ))
            except Exception as exc:  # preserve the action record for resume/audit
                result = {"status": "runner_error", "error": f"{type(exc).__name__}: {exc}"}
            if policy_decision is not None:
                _write_json(attempt_root / "policy_decision.json", policy_decision)
        if not _is_retryable_environment_block(result, attempt_root):
            break
        time.sleep(max(0.1, preflight_interval))
    row = {
        "action": action,
        "fault_family": family,
        "target": target,
        "repetition": repetition,
        "attempt": attempt_number,
        "candidate_id": candidate_id,
        "parameter_level": str(candidate.get("parameter_level") or "baseline"),
        "status": str(result.get("status") or "failed"),
        "output": str((Path(output_root) / "trials" / trial_root.name / f"attempt-{attempt_number:02d}").resolve()),
        "cleanup_status": _cleanup_status(Path(output_root) / "trials" / trial_root.name / f"attempt-{attempt_number:02d}", result),
        "retry_exhausted": str(result.get("status") or "") in {
            "environment_blocked",
            "injection_not_confirmed",
            "business_not_reachable",
            "apply_failed",
            "runner_error",
            "method_invalid",
        },
    }
    if result.get("error"):
        row["error"] = str(result["error"])
    return row


def _run_adaptive_live(
    *,
    profile_path: Path,
    history_rows: list[dict[str, Any]],
    output_root: Path,
    knowledge_root: Path,
    kube_context: str,
    target: str,
    max_unique_hypotheses: int | None,
    max_actions: int,
    approve_live: bool,
    preflight_timeout: float,
    preflight_interval: float,
    max_trial_attempts: int,
    policy_provider: Any | None = None,
    policy_mode: str = "shadow",
) -> dict[str, Any]:
    """Execute the selector one action at a time and persist resumable state."""

    profile = _read(profile_path)
    candidates = _candidate_list(profile, kube_context, target)
    history_rows = _align_history_rows(history_rows, candidates)
    output_root = Path(output_root)
    if output_root.exists() and any(output_root.iterdir()):
        state_path = output_root / "adaptive_state.json"
        if not state_path.is_file():
            raise FileExistsError(f"refusing non-empty adaptive output without state: {output_root}")
        existing = _read(state_path)
        prior_current_rows = [dict(item) for item in existing.get("current_results") or [] if isinstance(item, dict)]
        prior_current_rows = _align_history_rows(prior_current_rows, candidates)
        prior_decisions = [dict(item) for item in existing.get("decisions") or [] if isinstance(item, dict)]
        prior_action_count = int(existing.get("action_count") or len(prior_decisions))
        history_rows = list(history_rows) + prior_current_rows
    else:
        prior_current_rows = []
        prior_decisions = []
        prior_action_count = 0
    output_root.mkdir(parents=True, exist_ok=True)
    current_rows: list[dict[str, Any]] = prior_current_rows
    decisions: list[dict[str, Any]] = prior_decisions
    action_count = prior_action_count
    while action_count < max_actions:
        knowledge_cards = _policy_knowledge(profile, candidates, knowledge_root)
        decision = select_next_action(
            candidates,
            history_rows,
            max_unique_hypotheses=max_unique_hypotheses,
            policy_provider=policy_provider,
            policy_mode=policy_mode,
            knowledge_cards=knowledge_cards,
            policy_config=profile.get("adaptive_policy"),
            project_context={
                "project_id": profile.get("project_id"),
                "project_commit": profile.get("project_commit"),
                "runtime_backend": (profile.get("runtime_contract") or {}).get("backend"),
                "supported_fault_families": (profile.get("runtime_contract") or {}).get("supported_fault_families") or [],
            },
        )
        decisions.append({"round": action_count + 1, **decision})
        if decision.get("candidate") is None:
            break
        candidate = dict(decision["candidate"])
        candidate_id = str(candidate.get("candidate_id") or "")
        prior = [
            row for row in history_rows
            if str(row.get("candidate_id") or "") == candidate_id
            and row.get("status") == "live_completed"
            and row.get("cleanup_status") == "verified"
        ]
        repetition = max((int(row.get("repetition") or 0) for row in prior), default=0) + 1
        unique_used = {
            str(row.get("candidate_id") or "") for row in history_rows
            if row.get("candidate_id")
            and row.get("status") == "live_completed"
            and row.get("cleanup_status") == "verified"
        }
        row = _live_trial(
            profile=profile_path,
            candidate=candidate,
            output_root=output_root,
            action=str(decision.get("action") or "screen"),
            repetition=repetition,
            seed=1001 + action_count,
            kube_context=kube_context,
            preflight_timeout=preflight_timeout,
            preflight_interval=preflight_interval,
            max_trial_attempts=max_trial_attempts,
            knowledge_root=knowledge_root,
            policy_decision=decision,
        )
        row["unique_hypothesis_number"] = len(unique_used) + (0 if candidate_id in unique_used else 1)
        history_rows.append(row)
        current_rows.append(row)
        action_count += 1
        promotion = promote_confirmed_experiences(rows=history_rows, output_root=output_root, knowledge_root=knowledge_root)
        report = build_coverage_report(
            candidates,
            history_rows,
            _policy_knowledge(profile, candidates, knowledge_root),
            profile.get("adaptive_policy"),
        )
        _write_json(output_root / "coverage_report.json", report)
        _write_json(output_root / "experience_promotion.json", promotion)
        _write_json(output_root / "adaptive_state.json", {
            "schema_version": "chaosatlas-dify-adaptive-state-v1",
            "profile": str(profile_path.resolve()),
            "history_rows": len(history_rows) - len(current_rows),
            "current_results": current_rows,
            "decisions": decisions,
            "action_count": action_count,
            "max_actions": max_actions,
            "max_unique_hypotheses": max_unique_hypotheses,
            "policy_mode": policy_mode,
            "policy_provider": "llm" if policy_provider is not None else "deterministic",
            "unique_hypotheses_used": len({str(item.get("candidate_id") or "") for item in history_rows if item.get("candidate_id")}),
        })
        print(json.dumps({"status": "live_action_completed", "action": row["action"], "candidate_id": candidate_id, "repetition": repetition}, ensure_ascii=True), flush=True)
    promotion = promote_confirmed_experiences(rows=history_rows, output_root=output_root, knowledge_root=knowledge_root)
    report = build_coverage_report(
        candidates,
        history_rows,
        _policy_knowledge(profile, candidates, knowledge_root),
        profile.get("adaptive_policy"),
    )
    _write_json(output_root / "coverage_report.json", report)
    _write_json(output_root / "experience_promotion.json", promotion)
    _write_json(output_root / "adaptive_decisions.json", {"decisions": decisions, "action_count": action_count})
    return {
        "status": "live_completed",
        "action_count": action_count,
        "stop_reason": decisions[-1].get("stop_reason") if decisions else "no_action",
        "coverage": report,
        "promotion": promotion,
    }


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "-" for char in str(value)).strip("-") or "trial"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("plan", "live"), default="plan")
    parser.add_argument(
        "--budget-policy",
        choices=("auto", "fixed"),
        default="auto",
        help="auto derives remaining work from project state; fixed requires an explicit unique-hypothesis cap",
    )
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--history-summary", type=Path, default=DEFAULT_HISTORY)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--knowledge-root", type=Path, default=DEFAULT_KNOWLEDGE_ROOT)
    parser.add_argument("--kube-context", default="chaosatlas-dify")
    parser.add_argument("--target", default="all")
    parser.add_argument(
        "--max-unique-hypotheses",
        type=int,
        help="optional fixed hard ceiling; an explicit value overrides auto mode",
    )
    parser.add_argument("--max-actions", type=int)
    parser.add_argument("--approve-live", action="store_true")
    parser.add_argument("--preflight-timeout", type=float, default=180.0)
    parser.add_argument("--preflight-interval", type=float, default=3.0)
    parser.add_argument("--max-trial-attempts", type=int, default=4)
    parser.add_argument("--policy-provider", choices=("deterministic", "deepseek"), default="deterministic")
    parser.add_argument("--policy-mode", choices=("shadow", "guarded"), default="shadow")
    parser.add_argument("--policy-api-key-file", type=Path)
    parser.add_argument("--policy-base-url", default="https://api.deepseek.com/v1")
    parser.add_argument("--policy-model", default="deepseek-v4-flash")
    args = parser.parse_args(argv)
    if args.max_unique_hypotheses is not None and args.max_unique_hypotheses < 1:
        parser.error("--max-unique-hypotheses must be positive")
    if args.max_actions is not None and args.max_actions < 1:
        parser.error("--max-actions must be positive")
    if args.mode == "live" and not args.approve_live:
        parser.error("--approve-live is required with --mode live")
    if args.preflight_timeout < 0 or args.preflight_interval <= 0 or args.max_trial_attempts < 1:
        parser.error("invalid live retry/preflight settings")

    profile = _read(args.profile)
    rows = _read_rows(args.history_summary)
    candidates = _candidate_list(profile, args.kube_context, args.target)
    rows = _align_history_rows(rows, candidates)
    if args.budget_policy == "fixed" and args.max_unique_hypotheses is None:
        parser.error("--max-unique-hypotheses is required with --budget-policy fixed")
    # An explicit integer remains a fixed safety ceiling for compatibility;
    # without it, the selector derives the moving ceiling from project state.
    max_unique = args.max_unique_hypotheses
    policy_provider = None
    if args.policy_provider == "deepseek":
        try:
            from tools.deepseek_advisory import create_deepseek_policy_provider

            policy_provider = create_deepseek_policy_provider(
                api_key_file=args.policy_api_key_file,
                base_url=args.policy_base_url,
                model=args.policy_model,
            )
        except (OSError, ValueError, ImportError) as exc:
            print(json.dumps({"status": "blocked_missing_policy_provider", "reason": str(exc)}, ensure_ascii=True))
            return 2
    if args.mode == "live":
        max_actions = args.max_actions or max(1, len(candidates) * 3)
        result = _run_adaptive_live(
            profile_path=args.profile,
            history_rows=rows,
            output_root=args.output,
            knowledge_root=args.knowledge_root,
            kube_context=args.kube_context,
            target=args.target,
            max_unique_hypotheses=max_unique,
            max_actions=max_actions,
            approve_live=args.approve_live,
            preflight_timeout=args.preflight_timeout,
            preflight_interval=args.preflight_interval,
            max_trial_attempts=args.max_trial_attempts,
            policy_provider=policy_provider,
            policy_mode=args.policy_mode,
        )
        print(json.dumps({
            "status": result["status"],
            "action_count": result["action_count"],
            "stop_reason": result["stop_reason"],
            "policy_provider": args.policy_provider,
            "policy_mode": args.policy_mode,
            "budget_policy": "fixed" if max_unique is not None else "auto",
            "promoted": result["promotion"].get("promoted_card_ids", []),
            "coverage": {
                "basic": result["coverage"]["basic_coverage"],
                "parameter": result["coverage"]["parameter_coverage"],
                "stable_reproduction": result["coverage"]["stable_reproduction_coverage"],
            },
        }, ensure_ascii=True))
        return 0

    knowledge_cards = _policy_knowledge(profile, candidates, args.knowledge_root)
    report = build_coverage_report(candidates, rows, knowledge_cards, profile.get("adaptive_policy"))
    action = select_next_action(
        candidates,
        rows,
        max_unique_hypotheses=max_unique,
        policy_provider=policy_provider,
        policy_mode=args.policy_mode,
        knowledge_cards=knowledge_cards,
        policy_config=profile.get("adaptive_policy"),
        project_context={
            "project_id": profile.get("project_id"),
            "project_commit": profile.get("project_commit"),
            "runtime_backend": (profile.get("runtime_contract") or {}).get("backend"),
            "supported_fault_families": (profile.get("runtime_contract") or {}).get("supported_fault_families") or [],
        },
    )
    promotion = promote_confirmed_experiences(
        rows=rows,
        output_root=args.output,
        knowledge_root=args.knowledge_root,
    )
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    plan = {
        "schema_version": "chaosatlas-dify-adaptive-plan-v1",
        "mode": "offline_plan",
        "profile": str(args.profile.resolve()),
        "history_summary": str(args.history_summary.resolve()),
        "target": args.target,
        "candidate_total": len(candidates),
        "causal_cluster_total": report["causal_cluster_total"],
        "max_unique_hypotheses": max_unique,
        "budget_policy": "fixed" if max_unique is not None else "auto",
        "policy_provider": args.policy_provider,
        "policy_mode": args.policy_mode,
        "next_action": action,
        "no_live_mutation_performed": True,
        "historical_unique_hypotheses": len({str(row.get("candidate_id") or "") for row in rows if row.get("candidate_id")}),
        "remaining_unique_hypothesis_budget": (
            max(0, max_unique - len({str(row.get("candidate_id") or "") for row in rows if row.get("candidate_id")}))
            if max_unique is not None
            else report["budget_plan"]["remaining_unique_work"]
        ),
    }
    (output / "adaptive_plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    (output / "coverage_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "offline_plan_completed", "next_action": action["action"], "stop_reason": action["stop_reason"], "promoted": promotion["promoted_card_ids"], "candidate_total": len(candidates)}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
