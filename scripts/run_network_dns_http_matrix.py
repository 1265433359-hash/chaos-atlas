"""Run or audit the first network, DNS and HTTP fault matrix.

The default ``static`` mode is side-effect free: it records all 32 catalog
intents for each profile without treating planned or unsupported intents as
executed.  ``live`` mode is an explicit wrapper around the existing batch
runner and requires ``--approve-live``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from tools.fault_matrix import build_fault_matrix


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cleanup_status(item: dict[str, Any]) -> str:
    value = item.get("cleanup_status", item.get("cleanup"))
    if isinstance(value, dict):
        value = value.get("status")
    return str(value or "")


def build_summary(results: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Reduce child results using fail-closed execution and cleanup gates.

    A result is eligible for policy feedback only when it crossed the live
    boundary and cleanup was explicitly verified.  Blocked, invalid and dirty
    runs remain visible in the report but can never inflate execution counts.
    """

    rows = [dict(item) for item in results if isinstance(item, dict)]
    executed = [item for item in rows if str(item.get("status") or "") == "live_completed"]
    cleanup_verified = [item for item in executed if _cleanup_status(item) == "verified"]
    status_counts: dict[str, int] = {}
    for item in rows:
        status = str(item.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "schema_version": "chaosatlas-network-dns-http-batch-summary-v1",
        "planned": sum(1 for item in rows if str(item.get("status") or "") == "planned"),
        "executed": len(executed),
        "cleanup_verified": len(cleanup_verified),
        "policy_feedback_eligible": len(cleanup_verified),
        "status_counts": status_counts,
        "results": rows,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _static_rows(profile_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    matrix = build_fault_matrix(profile)
    project_id = str(profile.get("project_id") or matrix.get("project_id") or profile_path.stem)
    rows = []
    for fault in matrix.get("faults") or []:
        support_status = str(fault.get("status") or "planned")
        rows.append(
            {
                "project_id": project_id,
                "profile": str(profile_path),
                "fault_family": str(fault.get("fault_id") or ""),
                "support_status": support_status,
                "status": "planned" if support_status == "planned" else "not_executed",
                "cleanup": "not_run",
                "policy_feedback_eligible": False,
                "reason": str(fault.get("reason") or "static matrix audit"),
            }
        )
    return profile, rows


def _manifest(profile_paths: list[Path], *, mode: str, kube_context: str | None, approve_live: bool, seed: int) -> dict[str, Any]:
    profiles = []
    for path in profile_paths:
        profile = json.loads(path.read_text(encoding="utf-8-sig"))
        profiles.append(
            {
                "project_id": str(profile.get("project_id") or path.stem),
                "profile": str(path),
                "profile_sha256": _sha256_file(path),
            }
        )
    return {
        "schema_version": "chaosatlas-network-dns-http-batch-manifest-v1",
        "mode": mode,
        "kube_context": kube_context,
        "approve_live": bool(approve_live),
        "seed": int(seed),
        "profiles": profiles,
    }


def run_matrix(
    profile_paths: Iterable[Path],
    *,
    output: Path,
    mode: str = "static",
    kube_context: str | None = None,
    approve_live: bool = False,
    max_candidates: int | None = None,
    policy_mode: str = "legacy",
    policy_budget: int = 20,
    seed: int = 1001,
) -> dict[str, Any]:
    paths = [Path(path).resolve() for path in profile_paths]
    if not paths:
        raise ValueError("at least one profile is required")
    if any(not path.is_file() for path in paths):
        missing = next(path for path in paths if not path.is_file())
        raise FileNotFoundError(missing)
    if mode not in {"static", "live"}:
        raise ValueError("mode must be static or live")
    output = Path(output).resolve()
    if mode == "live" and not approve_live:
        rows = [
            {"profile": str(path), "status": "environment_blocked", "reason": "approve_live_required"}
            for path in paths
        ]
    elif mode == "static":
        rows = []
        for path in paths:
            _, profile_rows = _static_rows(path)
            rows.extend(profile_rows)
    else:
        from chaosatlas.orchestration.batch import run_live_batch

        rows = []
        for path in paths:
            profile = json.loads(path.read_text(encoding="utf-8-sig"))
            project_id = str(profile.get("project_id") or path.stem)
            child_output = output / "projects" / project_id
            result = run_live_batch(
                profile_path=path,
                output_root=child_output,
                max_candidates=max_candidates,
                approve_live=True,
                kube_context=kube_context,
                policy_mode=policy_mode,
                policy_budget=policy_budget,
                seed=seed,
            )
            for item in result.get("results") or []:
                row = dict(item)
                row.setdefault("project_id", project_id)
                rows.append(row)
            if not result.get("results"):
                rows.append({"project_id": project_id, "status": result.get("status", "failed"), "reason": result.get("error")})

    manifest = _manifest(paths, mode=mode, kube_context=kube_context, approve_live=approve_live, seed=seed)
    summary = build_summary(rows)
    summary.update({"mode": mode, "project_count": len(paths), "manifest": "batch_manifest.json"})
    _write_json(output / "batch_manifest.json", manifest)
    _write_jsonl(output / "runtime_results.jsonl", rows)
    _write_json(
        output / "rca_summary.json",
        {
            "schema_version": "chaosatlas-network-dns-http-rca-summary-v1",
            "confirmed": sum(1 for row in rows if str(row.get("rca_status") or "") == "confirmed"),
            "results": [{"project_id": row.get("project_id"), "fault_family": row.get("fault_family"), "rca_status": row.get("rca_status")} for row in rows],
        },
    )
    _write_json(
        output / "cleanup_audit.json",
        {
            "schema_version": "chaosatlas-network-dns-http-cleanup-audit-v1",
            "verified": summary["cleanup_verified"],
            "results": [{"project_id": row.get("project_id"), "fault_family": row.get("fault_family"), "status": _cleanup_status(row)} for row in rows],
        },
    )
    _write_json(output / "batch_summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", nargs="+", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("static", "live"), default="static")
    parser.add_argument("--kube-context")
    parser.add_argument("--approve-live", action="store_true")
    parser.add_argument("--max-candidates", type=int)
    parser.add_argument("--policy-mode", choices=("legacy", "observe", "shadow", "guarded", "default"), default="legacy")
    parser.add_argument("--policy-budget", type=int, default=20)
    parser.add_argument("--seed", type=int, default=1001)
    args = parser.parse_args(argv)
    summary = run_matrix(
        args.profiles,
        output=args.output,
        mode=args.mode,
        kube_context=args.kube_context,
        approve_live=args.approve_live,
        max_candidates=args.max_candidates,
        policy_mode=args.policy_mode,
        policy_budget=args.policy_budget,
        seed=args.seed,
    )
    print(json.dumps({"status": "verified", "output": str(args.output), "executed": summary["executed"]}, ensure_ascii=False))
    return 2 if args.mode == "live" and not args.approve_live else 0


if __name__ == "__main__":
    raise SystemExit(main())
