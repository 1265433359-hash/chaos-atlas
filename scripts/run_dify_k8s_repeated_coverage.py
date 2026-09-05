"""Run repeated Dify Kubernetes fault coverage for stable reproduction evidence.

The budget is a hypothesis budget, not a trial budget. One hypothesis is one
unique ChaosAtlas candidate (workload plus fault family). Every selected
hypothesis is expanded into the configured number of isolated, sequential
trials so the reproduction gate can consume actual repeated runtime results.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from chaosatlas.orchestration.engine import RunEngine, RunRequest
from chaosatlas.orchestration.batch import build_live_batch_plan
from tools.chaosatlas_runtime_preflight import KubernetesPreflight
from tools.kubernetes_project_adapter import KubernetesProjectAdapter
from tools.fault_executor import validate_attestation
from tools.reproduction_policy import MIN_STABLE_REPRODUCTIONS
from tools.run_chaos_experiment import run_kubectl


DEFAULT_PROFILE = REPO_ROOT / "projects" / "dify-kubernetes" / "profile.json"
DEFAULT_CONTEXT = "chaosatlas-dify"
DEFAULT_TARGET = "all"
DEFAULT_BUDGET = 60


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_name(value: str) -> str:
    result = "".join(char if char.isalnum() or char in "._-" else "-" for char in str(value))
    return result.strip("-") or "trial"


def _candidate_list(profile: dict[str, Any], context: str, target: str) -> list[dict[str, Any]]:
    plan = build_live_batch_plan(
        profile=profile,
        adapter=KubernetesProjectAdapter(profile=profile, kube_context=context),
    )
    supported = [
        str(item)
        for item in (profile.get("runtime_contract") or {}).get("supported_fault_families") or []
    ]
    allowed_families = set(supported)
    target_filter = None if str(target).lower() in {"all", "*"} else str(target)
    candidates_by_family: dict[str, list[dict[str, Any]]] = {family: [] for family in supported}
    seen: set[str] = set()
    for item in plan.get("candidates") or []:
        if not isinstance(item, dict):
            continue
        candidate_id = str(item.get("candidate_id") or "")
        family = str(item.get("fault_family") or "")
        if not candidate_id or candidate_id in seen or family not in allowed_families:
            continue
        if target_filter is not None and str(item.get("target") or "") != target_filter:
            continue
        # StatefulSets have a dedicated service-canary executor. Do not send
        # them through the Deployment-oriented closed-loop runner.
        if str(item.get("target_kind") or "").lower() == "statefulset":
            continue
        # Disposable extension agents have their own extension canary runner;
        # they are not part of the ordinary Dify business-path matrix.
        if item.get("disposable_target") is True:
            continue
        seen.add(candidate_id)
        candidates_by_family.setdefault(family, []).append(item)

    # Keep selection balanced across fault families. The adapter currently
    # emits workload-major order, which would otherwise spend the budget on
    # only a few workloads before covering the remaining fault families.
    balanced: list[dict[str, Any]] = []
    for index in range(max((len(items) for items in candidates_by_family.values()), default=0)):
        balanced.extend(
            candidates_by_family[family][index]
            for family in supported
            if index < len(candidates_by_family[family])
        )
    return balanced


def _select_candidates(candidates: list[dict[str, Any]], budget: int) -> list[dict[str, Any]]:
    """Select at most ``budget`` unique hypotheses in deterministic order."""
    if budget < 1:
        raise ValueError("hypothesis budget must be positive")
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id") or "")
        if not candidate_id or candidate_id in seen:
            continue
        seen.add(candidate_id)
        selected.append(candidate)
        if len(selected) == budget:
            break
    return selected


def _wait_for_environment(
    profile: dict[str, Any],
    context: str,
    *,
    timeout_s: float,
    poll_interval_s: float,
) -> dict[str, Any]:
    """Wait for transient post-recovery readiness before starting a trial."""
    preflight = KubernetesPreflight(
        profile=profile,
        runner=run_kubectl,
        kube_context=context,
    )
    deadline = time.monotonic() + max(0.0, timeout_s)
    latest: dict[str, Any] = {}
    while True:
        latest = preflight.run()
        if latest.get("status") == "ready_for_injection":
            return latest
        if time.monotonic() >= deadline:
            return latest
        time.sleep(max(0.1, poll_interval_s))


def _is_retryable_environment_block(result: dict[str, Any], root: Path) -> bool:
    """Identify a no-injection outcome that is safe to retry."""
    status = str(result.get("status") or "")
    retryable_statuses = {
        "environment_blocked",
        "injection_not_confirmed",
        "business_not_reachable",
    }
    if status not in retryable_statuses:
        return False
    execute_path = root / "execute.json"
    if execute_path.is_file():
        try:
            document = json.loads(execute_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        payload = document.get("payload") if isinstance(document, dict) else {}
        phases = payload.get("phases") if isinstance(payload, dict) else []
        faults = phases[0].get("faults") if phases and isinstance(phases[0], dict) else []
        if faults and isinstance(faults[0], dict):
            return faults[0].get("injection_confirmed") is not True
    preflight = root / "preflight.json"
    if preflight.is_file():
        try:
            document = json.loads(preflight.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return document.get("injection_performed") is not True
    return status in {"environment_blocked", "business_not_reachable"}


def _load_completed_trial(
    trial_root: Path,
    *,
    hypothesis_index: int,
    family: str,
    target: str,
    repetition: int,
    candidate_id: str,
) -> dict[str, Any] | None:
    """Reuse a trial only when its complete runtime lifecycle is attested."""
    if not trial_root.is_dir():
        return None
    for attempt_root in sorted(trial_root.glob("attempt-*")):
        if not attempt_root.is_dir():
            continue
        summary_path = attempt_root / "summary.json"
        cleanup_path = attempt_root / "cleanup_report.json"
        if not summary_path.is_file() or not cleanup_path.is_file():
            continue
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            cleanup = json.loads(cleanup_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if summary.get("status") != "live_completed" or cleanup.get("status") != "verified":
            continue
        if not _trial_evidence_complete(attempt_root):
            continue
        try:
            attempt = int(attempt_root.name.rsplit("-", 1)[1])
        except (ValueError, IndexError):
            attempt = 0
        return {
            "hypothesis_index": hypothesis_index,
            "fault_family": family,
            "target": target,
            "repetition": repetition,
            "attempt": attempt,
            "candidate_id": candidate_id,
            "status": "live_completed",
            "output": str(attempt_root),
            "cleanup_status": "verified",
            "resumed": True,
        }
    return None


def _trial_evidence_complete(attempt_root: Path) -> bool:
    """Require all lifecycle gates in the selected attempt's runtime evidence."""
    execute_path = attempt_root / "execute.json"
    cleanup_path = attempt_root / "cleanup_report.json"
    if not execute_path.is_file() or not cleanup_path.is_file():
        return False
    try:
        execute = json.loads(execute_path.read_text(encoding="utf-8"))
        cleanup = json.loads(cleanup_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    payload = execute.get("payload") if isinstance(execute, dict) else None
    phases = payload.get("phases") if isinstance(payload, dict) else None
    faults = phases[0].get("faults") if phases and isinstance(phases[0], dict) else None
    fault = faults[0] if isinstance(faults, list) and faults else None
    attestation = fault.get("attestation") if isinstance(fault, dict) else None
    return (
        execute.get("status") == "completed"
        and cleanup.get("status") == "verified"
        and isinstance(attestation, dict)
        and validate_attestation(attestation).valid
    )


def _result_is_complete(item: dict[str, Any]) -> bool:
    """Check the actual attempt evidence represented by a summary row."""
    return (
        item.get("status") == "live_completed"
        and item.get("cleanup_status") == "verified"
        and _trial_evidence_complete(Path(str(item.get("output") or "")))
    )


def _next_attempt_number(trial_root: Path) -> int:
    numbers: list[int] = []
    for path in trial_root.glob("attempt-*"):
        if not path.is_dir():
            continue
        try:
            numbers.append(int(path.name.rsplit("-", 1)[1]))
        except (ValueError, IndexError):
            continue
    return max(numbers, default=0) + 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--kube-context", default=DEFAULT_CONTEXT)
    parser.add_argument(
        "--target",
        default=DEFAULT_TARGET,
        help="workload target to test, or 'all' for the complete candidate space",
    )
    parser.add_argument("--repetitions", type=int, default=MIN_STABLE_REPRODUCTIONS)
    parser.add_argument(
        "--budget",
        "--hypothesis-budget",
        dest="budget",
        type=int,
        default=DEFAULT_BUDGET,
        help="maximum number of unique hypotheses; each is repeated separately",
    )
    parser.add_argument("--approve-live", action="store_true")
    parser.add_argument("--preflight-timeout", type=float, default=180.0)
    parser.add_argument("--preflight-interval", type=float, default=3.0)
    parser.add_argument("--max-trial-attempts", type=int, default=4)
    args = parser.parse_args(argv)

    if not args.approve_live:
        parser.error("--approve-live is required for live coverage")
    if args.repetitions < MIN_STABLE_REPRODUCTIONS:
        parser.error(f"--repetitions must be at least {MIN_STABLE_REPRODUCTIONS}")
    if args.budget < 1:
        parser.error("--budget must be positive")
    if args.preflight_timeout < 0 or args.preflight_interval <= 0:
        parser.error("preflight timeout must be non-negative and interval must be positive")
    if args.max_trial_attempts < 1:
        parser.error("--max-trial-attempts must be positive")

    profile = json.loads(args.profile.read_text(encoding="utf-8-sig"))
    candidates = _candidate_list(profile, args.kube_context, args.target)
    selected = _select_candidates(candidates, args.budget)
    if not selected:
        raise SystemExit("no supported candidates are available for the selected target")

    planned_hypotheses = len(selected)
    planned_trials = planned_hypotheses * args.repetitions
    selected_ids = [str(item["candidate_id"]) for item in selected]

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    plan = {
        "schema_version": "chaosatlas-dify-repeated-coverage-plan-v1",
        "created_at": _now(),
        "profile": str(args.profile.resolve()),
        "context": args.kube_context,
        "target": args.target,
        "budget": args.budget,
        "hypothesis_budget": args.budget,
        "repetitions": args.repetitions,
        "minimum_stable_reproductions": MIN_STABLE_REPRODUCTIONS,
        "available_hypotheses": len(candidates),
        "selected_hypotheses": selected,
        "selected_candidate_ids": selected_ids,
        "planned_hypotheses": planned_hypotheses,
        "planned_trials": planned_trials,
        "trial_budget": args.budget * args.repetitions,
        "reserved_hypotheses": args.budget - planned_hypotheses,
        "preflight_retry_policy": {
            "timeout_s": args.preflight_timeout,
            "poll_interval_s": args.preflight_interval,
            "max_trial_attempts": args.max_trial_attempts,
        },
    }
    (output / "repeat_plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    results: list[dict[str, Any]] = []
    for hypothesis_index, candidate in enumerate(selected, start=1):
        family = str(candidate.get("fault_family") or "unknown")
        candidate_id = str(candidate["candidate_id"])
        target = str(candidate.get("target") or args.target)
        for repetition in range(1, args.repetitions + 1):
            trial_name = f"{hypothesis_index:03d}-{_safe_name(family)}-{_safe_name(target)}-r{repetition:02d}"
            trial_root = output / "trials" / trial_name
            resumed_item = _load_completed_trial(
                trial_root,
                hypothesis_index=hypothesis_index,
                family=family,
                target=target,
                repetition=repetition,
                candidate_id=candidate_id,
            )
            if resumed_item is not None:
                results.append(resumed_item)
                print(json.dumps({"status": "resumed", **resumed_item}, ensure_ascii=True), flush=True)
                continue
            print(f"[start] {trial_name} candidate={candidate_id}", flush=True)
            trial_root.mkdir(parents=True, exist_ok=True)
            item: dict[str, Any] = {}
            first_attempt = _next_attempt_number(trial_root)
            for attempt in range(first_attempt, first_attempt + args.max_trial_attempts):
                attempt_root = trial_root / f"attempt-{attempt:02d}"
                preflight = _wait_for_environment(
                    profile,
                    args.kube_context,
                    timeout_s=args.preflight_timeout,
                    poll_interval_s=args.preflight_interval,
                )
                if preflight.get("status") != "ready_for_injection":
                    (attempt_root).mkdir(parents=True, exist_ok=True)
                    (attempt_root / "preflight.json").write_text(
                        json.dumps(preflight, indent=2, ensure_ascii=True) + "\n",
                        encoding="utf-8",
                    )
                    result = {
                        "status": "environment_blocked",
                        "error": "; ".join(str(value) for value in preflight.get("errors") or []),
                    }
                else:
                    try:
                        result = RunEngine().run_candidate(RunRequest(
                            profile_path=args.profile,
                            output_root=attempt_root,
                            mode="live",
                            approve_live=True,
                            candidate_id=candidate_id,
                            kube_context=args.kube_context,
                            seed=1001 + ((hypothesis_index - 1) * args.repetitions) + repetition - 1,
                        ))
                    except Exception as exc:
                        result = {
                            "status": "runner_error",
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                if not _is_retryable_environment_block(result, attempt_root):
                    cleanup_status = result.get("cleanup_status")
                    cleanup_report = attempt_root / "cleanup_report.json"
                    if not cleanup_status and cleanup_report.is_file():
                        try:
                            cleanup_status = json.loads(
                                cleanup_report.read_text(encoding="utf-8")
                            ).get("status")
                        except (OSError, json.JSONDecodeError):
                            cleanup_status = "failed"
                    item = {
                        "hypothesis_index": hypothesis_index,
                        "fault_family": family,
                        "target": target,
                        "repetition": repetition,
                        "attempt": attempt,
                        "candidate_id": candidate_id,
                        "status": result.get("status"),
                        "output": str(attempt_root),
                        "cleanup_status": cleanup_status or "unknown",
                    }
                    if result.get("error"):
                        item["error"] = result["error"]
                    break
                print(f"[retry] {trial_name} transient readiness block; attempt={attempt}", flush=True)
            else:
                item = {
                    "hypothesis_index": hypothesis_index,
                    "fault_family": family,
                    "target": target,
                    "repetition": repetition,
                    "attempt": args.max_trial_attempts,
                    "candidate_id": candidate_id,
                    "status": "environment_blocked",
                    "output": str(trial_root),
                    "cleanup_status": "unknown",
                    "error": "transient readiness did not recover within max trial attempts",
                }
            results.append(item)
            print(json.dumps(item, ensure_ascii=True), flush=True)

    completed = sum(1 for item in results if _result_is_complete(item))
    completed_hypotheses = sum(
        1
        for hypothesis_index in range(1, planned_hypotheses + 1)
        if sum(
            1
            for item in results
            if item.get("hypothesis_index") == hypothesis_index
            and _result_is_complete(item)
        ) == args.repetitions
    )
    summary = {
        "schema_version": "chaosatlas-dify-repeated-coverage-summary-v1",
        "status": "passed" if completed == planned_trials else "failed",
        "completed_at": _now(),
        "context": args.kube_context,
        "target": args.target,
        "budget": args.budget,
        "hypothesis_budget": args.budget,
        "repetitions": args.repetitions,
        "available_hypotheses": len(candidates),
        "planned_hypotheses": planned_hypotheses,
        "completed_hypotheses": completed_hypotheses,
        "planned_trials": planned_trials,
        "completed_trials": completed,
        "trial_budget": args.budget * args.repetitions,
        "reserved_hypotheses": args.budget - planned_hypotheses,
        "results": results,
    }
    (output / "repeat_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": summary["status"],
                "completed_hypotheses": completed_hypotheses,
                "planned_hypotheses": planned_hypotheses,
                "completed_trials": completed,
                "planned_trials": planned_trials,
            },
            ensure_ascii=True,
        ),
        flush=True,
    )
    return 0 if summary["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
