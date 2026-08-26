"""Build a read-only final acceptance report for the ChaosAtlas closed loop."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from tools.validate_knowledge_base import validate


def _check(status: str, *, details: dict[str, Any] | None = None, errors: Sequence[str] = ()) -> dict[str, Any]:
    return {"status": status, "errors": list(errors), **(details or {})}


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _payload(root: Path, name: str) -> dict[str, Any]:
    value = _read_json(root / name)
    payload = value.get("payload")
    return payload if isinstance(payload, dict) else value


def _validate_projects(projects: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    project_results: list[dict[str, Any]] = []
    accepted_projects = 0
    for project, raw in projects.items():
        if isinstance(raw, Mapping):
            root = Path(str(raw.get("root") or ""))
            commit = str(raw.get("commit") or "")
        else:
            root = Path(str(raw))
            commit = ""
        report = validate(root, expected_project=str(project), expected_commit=commit or None)
        card_ids = [str(item.get("id")) for item in report.get("card_checks", []) if item.get("valid") and item.get("id")]
        local_reusable = [
            item.get("id")
            for item in report.get("card_checks", [])
            if item.get("valid") and item.get("status") == "local_reusable"
        ]
        project_ok = bool(report.get("valid")) and bool(local_reusable)
        if project_ok:
            accepted_projects += 1
        else:
            errors.append(f"{project}: knowledge root did not validate as local reusable")
        project_results.append({
            "project": str(project),
            "root": str(root).replace("\\", "/"),
            "expected_commit": commit or None,
            "valid": bool(report.get("valid")),
            "card_count": int(report.get("card_count") or 0),
            "card_ids": card_ids,
            "local_reusable_card_ids": local_reusable,
            "errors": report.get("errors", []),
        })
    if accepted_projects < 3:
        errors.append(f"at least three project-local knowledge roots are required; got {accepted_projects}")
    return _check(
        "passed" if not errors else "blocked",
        details={"project_count": len(projects), "accepted_project_count": accepted_projects, "projects": project_results},
        errors=errors,
    )


def _validate_improvement(roots: Sequence[Path]) -> dict[str, Any]:
    errors: list[str] = []
    records: list[dict[str, Any]] = []
    for raw_root in roots:
        root = Path(raw_root)
        path = root if root.is_file() else root / "improvement_evidence.json"
        try:
            value = _read_json(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{path}: {exc}")
            continue
        valid = (
            value.get("schema_version") == "chaosatlas-improvement-evidence-v1"
            and value.get("status") == "improvement_verified"
            and value.get("same_scenario_contract") is True
            and value.get("cleanup_verified") is True
            and value.get("knowledge_update_allowed") is True
            and (value.get("validation") or {}).get("valid") is True
        )
        if not valid:
            errors.append(f"{path}: improvement_verified contract failed")
        records.append({"path": str(path).replace("\\", "/"), "status": value.get("status"), "valid": valid})
    if not records:
        errors.append("at least one improvement evidence record is required")
    return _check("passed" if not errors else "blocked", details={"records": records, "verified_count": sum(1 for item in records if item["valid"])}, errors=errors)


def _validate_dry_runs(roots: Sequence[Path]) -> dict[str, Any]:
    errors: list[str] = []
    records: list[dict[str, Any]] = []
    for raw_root in roots:
        root = Path(raw_root)
        try:
            summary = _read_json(root / "summary.json")
            finding = _payload(root, "finding_report.json")
            rca = _payload(root, "rca_report.json")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{root}: {exc}")
            continue
        valid = summary.get("status") == "dry_run_ready" and finding.get("result") == "not_run" and rca.get("rca_status") == "not_run"
        if not valid:
            errors.append(f"{root}: dry-run must remain synthetic with finding=not_run and rca=not_run")
        records.append({"root": str(root).replace("\\", "/"), "status": summary.get("status"), "finding": finding.get("result"), "rca": rca.get("rca_status"), "valid": valid})
    if len(records) < 3:
        errors.append(f"at least three dry-run project records are required; got {len(records)}")
    return _check("passed" if not errors else "blocked", details={"run_count": len(records), "runs": records}, errors=errors)


def build_final_acceptance(
    *,
    projects: Mapping[str, Any],
    improvement_roots: Sequence[Path],
    dry_run_roots: Sequence[Path],
    policy_mode: str = "legacy",
    explicit_guarded_gate: bool = False,
) -> dict[str, Any]:
    """Evaluate final product gates without accessing Kubernetes or an LLM."""
    if policy_mode not in {"legacy", "observe", "shadow", "guarded", "default"}:
        raise ValueError("invalid policy_mode")
    checks = {
        "local_project_knowledge": _validate_projects(projects),
        "improvement_retest": _validate_improvement(improvement_roots),
        "dry_run_boundaries": _validate_dry_runs(dry_run_roots),
    }
    policy_ok = policy_mode == "legacy" or (explicit_guarded_gate and all(item["status"] == "passed" for item in checks.values()))
    checks["policy_default"] = _check(
        "passed" if policy_ok else "blocked",
        details={"mode": policy_mode, "explicit_guarded_gate": explicit_guarded_gate},
        errors=[] if policy_ok else ["guarded/default policy requires an explicit acceptance gate; legacy remains the default"],
    )
    status = "passed" if all(item["status"] == "passed" for item in checks.values()) else "blocked"
    return {
        "schema_version": "chaosatlas-final-acceptance-v1",
        "status": status,
        "checks": checks,
        "default_policy_decision": "retain_legacy",
        "runtime_side_effects": {"kubernetes_mutation": False, "llm_called": False, "formal_knowledge_written": False},
        "claim_boundary": "closed-loop orchestration and knowledge feedback are accepted; guarded default rollout remains a separate explicit decision",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", action="append", nargs=3, metavar=("PROJECT", "ROOT", "COMMIT"), required=True)
    parser.add_argument("--improvement-root", action="append", type=Path, default=[])
    parser.add_argument("--dry-run-root", action="append", type=Path, default=[])
    parser.add_argument("--policy-mode", choices=("legacy", "observe", "shadow", "guarded", "default"), default="legacy")
    parser.add_argument("--explicit-guarded-gate", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    projects = {project: {"root": Path(root), "commit": commit} for project, root, commit in args.project}
    report = build_final_acceptance(
        projects=projects,
        improvement_roots=args.improvement_root,
        dry_run_roots=args.dry_run_root,
        policy_mode=args.policy_mode,
        explicit_guarded_gate=args.explicit_guarded_gate,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(args.output)}, ensure_ascii=True))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
