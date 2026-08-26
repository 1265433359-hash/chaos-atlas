"""Run a guarded, knowledge-guided deployment improvement retest."""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.defense_promotion_stage import promote_from_history
from tools.deployment_improvement import (
    apply_patch_copy,
    build_improvement_evidence,
    classify_retest,
)
from tools.feedback_protocol import validate_improvement_evidence
from tools.fresh_deploy import FreshDeploymentAdapter


REQUIRED_RUN_ARTIFACTS = (
    "run_manifest.json",
    "classify.json",
    "observe.json",
    "cleanup_report.json",
)
OPTIONAL_RUN_ARTIFACTS = ("inventory.json",)
Runner = Callable[[list[str]], dict[str, Any]]


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _payload(root: Path, name: str) -> dict[str, Any]:
    value = _read_json(Path(root) / name)
    payload = value.get("payload")
    return payload if isinstance(payload, dict) else value


def _run_contract(root: Path) -> dict[str, Any]:
    root = Path(root)
    missing = [name for name in REQUIRED_RUN_ARTIFACTS if not (root / name).is_file()]
    if missing or not (root / "execute.json").is_file():
        raise ValueError("missing required run artifacts: " + ",".join(missing or ["execute.json"]))
    manifest = _read_json(root / "run_manifest.json")
    execute = _payload(root, "execute.json")
    phase = (execute.get("phases") or [{}])[0]
    fault = (phase.get("faults") or [{}])[0] if isinstance(phase, dict) else {}
    return {
        "scenario_id": execute.get("scenario_id") or manifest.get("run_id"),
        "scenario_hash": execute.get("scenario_hash"),
        "seed": execute.get("seed") if execute.get("seed") is not None else manifest.get("seed"),
        "oracle": copy.deepcopy(execute.get("oracle")),
        "recovery": copy.deepcopy(execute.get("recovery")),
        "cleanup": copy.deepcopy(execute.get("cleanup")),
        "fault_family": fault.get("kind"),
        "target": fault.get("target") or fault.get("target_name"),
        "classification": _payload(root, "classify.json").get("result"),
        "cleanup_status": _payload(root, "cleanup_report.json").get("status"),
        "fault_cleanup_confirmed": all(
            item.get("cleanup_confirmed") is True
            for item in (phase.get("faults") or [])
            if isinstance(item, dict)
        ),
    }


def compare_live_runs(baseline_root: Path, after_root: Path) -> dict[str, Any]:
    """Compare two complete runs while ignoring the expected patched scenario hash."""

    try:
        baseline = _run_contract(Path(baseline_root))
        after = _run_contract(Path(after_root))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        evidence = build_improvement_evidence(
            {"status": "deployment_blocked", "baseline": {}, "after": {}, "comparison": {}}
        )
        evidence["reason"] = str(exc)
        evidence["validation"] = validate_improvement_evidence(evidence)
        return {"status": "deployment_blocked", "reason": str(exc), "improvement_evidence": evidence, "validation": evidence["validation"]}

    contract_fields = ("scenario_id", "seed", "oracle", "recovery", "cleanup", "fault_family", "target")
    same_contract = all(baseline.get(field) == after.get(field) for field in contract_fields)
    cleanup_verified = (
        after.get("cleanup_status") == "verified"
        and after.get("fault_cleanup_confirmed") is True
    )
    status = classify_retest(
        "executed",
        baseline=str(baseline.get("classification") or "not_run"),
        after=str(after.get("classification") or "not_run"),
    )
    if status == "improvement_verified" and (not same_contract or not cleanup_verified):
        status = "deployment_blocked"
    comparison = {
        "same_scenario_contract": same_contract,
        "cleanup_verified": cleanup_verified,
        "scenario_id": after.get("scenario_id"),
        "seed": after.get("seed"),
        "oracle": after.get("oracle"),
        "recovery": after.get("recovery"),
        "cleanup": after.get("cleanup"),
        "fault_family": after.get("fault_family"),
        "target": after.get("target"),
        "scenario_hash_before": baseline.get("scenario_hash"),
        "scenario_hash_after": after.get("scenario_hash"),
        "scenario_hash_changed_by_patch": baseline.get("scenario_hash") != after.get("scenario_hash"),
    }
    result = {
        "status": status,
        "baseline": baseline,
        "after": after,
        "comparison": comparison,
    }
    evidence = build_improvement_evidence(result)
    evidence["validation"] = validate_improvement_evidence(evidence)
    result["improvement_evidence"] = evidence
    result["validation"] = evidence["validation"]
    return result


def stage_history_run(run_root: Path, history_root: Path, name: str) -> dict[str, Any]:
    """Copy only complete, immutable promotion inputs into a fresh history child."""

    run_root, history_root = Path(run_root), Path(history_root)
    missing = [name for name in REQUIRED_RUN_ARTIFACTS if not (run_root / name).is_file()]
    if missing:
        return {"status": "rejected", "reason": "missing_required_artifacts", "missing": missing}
    destination = history_root / name
    if destination.exists():
        return {"status": "rejected", "reason": "history_child_exists", "path": str(destination)}
    destination.mkdir(parents=True, exist_ok=False)
    copied = list(REQUIRED_RUN_ARTIFACTS)
    for artifact in REQUIRED_RUN_ARTIFACTS:
        shutil.copyfile(run_root / artifact, destination / artifact)
    for artifact in OPTIONAL_RUN_ARTIFACTS:
        if (run_root / artifact).is_file():
            shutil.copyfile(run_root / artifact, destination / artifact)
            copied.append(artifact)
    return {"status": "staged", "path": str(destination), "artifacts": copied}


def kubectl_runner(args: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["kubectl", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"return_code": 1, "stdout": "", "stderr": f"{type(exc).__name__}: {exc}"}
    return {"return_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}


def wait_for_available(namespace: str, runner: Runner = kubectl_runner, timeout_s: int = 300) -> dict[str, Any]:
    result = runner(["wait", "--for=condition=Available", "deployment", "--all", "-n", namespace, f"--timeout={int(timeout_s)}s"])
    return {
        "status": "ready" if int(result.get("return_code", 1)) == 0 else "deployment_blocked",
        "result": result,
    }


def ensure_namespace(namespace: str, runner: Runner = kubectl_runner) -> dict[str, Any]:
    """Create the approved namespace so server-side dry-run can validate namespaced resources."""

    result = runner(["create", "namespace", namespace])
    if int(result.get("return_code", 1)) == 0:
        return {"status": "created", "result": result}
    stderr = str(result.get("stderr") or "")
    if "AlreadyExists" in stderr or "already exists" in stderr.lower():
        return {"status": "present", "result": result}
    return {"status": "deployment_blocked", "result": result}


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_live_improvement(
    *,
    profile_path: Path,
    source_root: Path,
    baseline_root: Path,
    proposal: dict[str, Any],
    output_root: Path,
    namespace: str,
    allowed_namespaces: set[str],
    mode: str = "dry-run",
    seed: int = 1001,
    approve_live: bool = False,
    runner: Runner | None = None,
    prior_improvement_root: Path | None = None,
    knowledge_write_root: Path | None = None,
) -> dict[str, Any]:
    """Execute one guarded improvement retest and optionally promote two runs."""

    output_root = Path(output_root)
    if mode not in {"dry-run", "live"}:
        raise ValueError("mode must be dry-run or live")
    if output_root.exists() and any(output_root.iterdir()):
        return {"status": "deployment_blocked", "reason": "output_root_must_be_fresh"}
    output_root.mkdir(parents=True, exist_ok=True)
    patched_root = output_root / "patched-source"
    patch = apply_patch_copy(Path(source_root), proposal, patched_root)
    _write(output_root / "patch.json", patch)
    if patch.get("status") != "applied":
        summary = {"status": "deployment_blocked", "reason": patch.get("error", "patch_not_applied"), "patch": patch}
        _write(output_root / "summary.json", summary)
        return summary

    adapter = FreshDeploymentAdapter(
        namespace=namespace,
        allowed_namespaces=set(allowed_namespaces),
        runner=runner or kubectl_runner,
        allow_live=approve_live,
    )
    namespace_prepare: dict[str, Any] | None = None
    if mode == "live" and approve_live:
        namespace_prepare = ensure_namespace(namespace, runner or kubectl_runner)
        _write(output_root / "namespace_prepare.json", namespace_prepare)
        if namespace_prepare.get("status") not in {"created", "present"}:
            summary = {"status": "deployment_blocked", "reason": "namespace_prepare_failed", "namespace_prepare": namespace_prepare}
            _write(output_root / "summary.json", summary)
            return summary
    deploy = adapter.deploy(patched_root)
    _write(output_root / "deploy_dry_run.json", deploy)
    if deploy.get("status") != "dry_run_ready":
        cleanup_after_preflight = adapter.cleanup(patched_root) if mode == "live" and approve_live else None
        if cleanup_after_preflight is not None:
            _write(output_root / "cleanup_report.json", cleanup_after_preflight)
        summary = {"status": "deployment_blocked", "reason": deploy.get("reason", "server_side_dry_run_failed"), "deploy": deploy}
        _write(output_root / "summary.json", summary)
        return summary
    if mode == "dry-run":
        summary = {"status": "dry_run_ready", "patch": patch, "deploy": deploy}
        _write(output_root / "summary.json", summary)
        return summary
    if not approve_live:
        summary = {"status": "deployment_blocked", "reason": "explicit live approval is required", "deploy": deploy}
        _write(output_root / "summary.json", summary)
        return summary

    applied = adapter.apply_live(patched_root)
    _write(output_root / "deploy_apply.json", applied)
    if applied.get("status") != "deployed":
        cleanup_after_apply = adapter.cleanup(patched_root)
        _write(output_root / "cleanup_report.json", cleanup_after_apply)
        summary = {"status": "deployment_blocked", "reason": applied.get("reason", "live_apply_failed"), "deploy": applied}
        _write(output_root / "summary.json", summary)
        return summary

    runtime_root = output_root / "runtime"
    cleanup: dict[str, Any] = {"status": "not_run"}
    try:
        readiness = wait_for_available(namespace, runner or kubectl_runner)
        _write(output_root / "readiness.json", readiness)
        if readiness.get("status") != "ready":
            summary = {"status": "deployment_blocked", "reason": "patched deployment did not become available", "readiness": readiness}
            _write(output_root / "summary.json", summary)
            return summary
        from tools.chaosatlas import run_closed_loop

        try:
            runtime = run_closed_loop(
                profile_path=Path(profile_path),
                output_root=runtime_root,
                mode="live",
                seed=seed,
                approve_live=True,
            )
        except Exception as exc:
            runtime = {"status": "method_invalid", "error": f"live_retest_exception:{type(exc).__name__}: {exc}"}
        _write(output_root / "runtime_result.json", runtime)
        if runtime.get("status") != "live_completed":
            summary = {"status": "deployment_blocked", "reason": runtime.get("error", "live_retest_failed"), "runtime": runtime}
            _write(output_root / "summary.json", summary)
            return summary
    finally:
        cleanup = adapter.cleanup(patched_root)
        _write(output_root / "cleanup_report.json", cleanup)

    comparison = compare_live_runs(Path(baseline_root), runtime_root)
    if cleanup.get("status") != "cleanup_verified":
        comparison["status"] = "deployment_blocked"
        comparison["reason"] = "fresh_namespace_cleanup_failed"
        evidence = build_improvement_evidence(
            {
                "status": "deployment_blocked",
                "baseline": comparison.get("baseline", {}),
                "after": comparison.get("after", {}),
                "comparison": {**comparison.get("comparison", {}), "cleanup_verified": False},
            }
        )
        evidence["validation"] = validate_improvement_evidence(evidence)
        comparison["improvement_evidence"] = evidence
        comparison["validation"] = evidence["validation"]
    _write(output_root / "improvement_evidence.json", comparison.get("improvement_evidence", {}))
    promotion: dict[str, Any] = {"status": "not_run", "reason": "prior_improvement_root_not_supplied"}
    if prior_improvement_root is not None and comparison.get("status") == "improvement_verified":
        history = output_root / "defense-history"
        staged_prior = stage_history_run(Path(prior_improvement_root), history, "r1")
        staged_after = stage_history_run(runtime_root, history, "r2")
        if staged_prior.get("status") == "staged" and staged_after.get("status") == "staged":
            promotion = promote_from_history(
                history_root=history,
                output_root=output_root / "promotion",
                knowledge_write_root=knowledge_write_root,
            )
        else:
            promotion = {"status": "contested", "reason": "promotion_history_staging_failed", "prior": staged_prior, "after": staged_after}
    summary = {
        "status": comparison.get("status", "deployment_blocked"),
        "patch": patch,
        "deploy": applied,
        "cleanup": cleanup,
        "comparison": comparison,
        "promotion": promotion,
    }
    _write(output_root / "summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--allowed-namespace", action="append")
    parser.add_argument("--mode", choices=("dry-run", "live"), default="dry-run")
    parser.add_argument("--seed", type=int, default=1001)
    parser.add_argument("--approve-live", action="store_true")
    parser.add_argument("--prior-improvement-root", type=Path)
    parser.add_argument("--knowledge-write-root", type=Path)
    args = parser.parse_args(argv)
    proposal = _read_json(args.proposal)
    result = run_live_improvement(
        profile_path=args.profile,
        source_root=args.source_root,
        baseline_root=args.baseline_root,
        proposal=proposal,
        output_root=args.output,
        namespace=args.namespace,
        allowed_namespaces=set(args.allowed_namespace or [args.namespace]),
        mode=args.mode,
        seed=args.seed,
        approve_live=args.approve_live,
        prior_improvement_root=args.prior_improvement_root,
        knowledge_write_root=args.knowledge_write_root,
    )
    print(json.dumps({"status": result.get("status"), "output": str(args.output)}, ensure_ascii=False))
    return 0 if result.get("status") in {"dry_run_ready", "improvement_verified", "promoted"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
