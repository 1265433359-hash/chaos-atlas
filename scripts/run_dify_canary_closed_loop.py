"""Materialize and aggregate RCA artifacts for standalone Dify canary runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.dify_canary_closed_loop import (
    aggregate_canary_trials,
    record_canary_trial,
    repetition_from_name,
)


DEFAULT_PROFILE = REPO_ROOT / "projects" / "dify-kubernetes" / "profile.json"
DEFAULT_KNOWLEDGE_ROOT = REPO_ROOT / "artifacts" / "dify-kubernetes" / "knowledge_base"


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _service_target(name: str) -> str:
    return {
        "plugin-daemon": "dify-k8s-plugin-daemon",
        "sandbox": "dify-k8s-sandbox",
        "redis": "dify-k8s-redis-master",
        "postgresql": "dify-k8s-postgresql",
        "weaviate": "weaviate",
    }.get(name, name)


def _rows_for_root(root: Path, profile: dict[str, Any]) -> list[dict[str, Any]]:
    summary = _read(root / "summary.json")
    schema = str(summary.get("schema_version") or "")
    rows: list[dict[str, Any]] = []
    if schema == "chaosatlas-dify-dependency-canary-v1":
        candidate = summary.get("candidate")
        result = summary.get("result")
        if isinstance(candidate, dict) and isinstance(result, dict):
            rows.append(record_canary_trial(
                root=root,
                profile=profile,
                candidate=candidate,
                result=result,
                project_inventory={"namespace": summary.get("namespace")},
                repetition=repetition_from_name(root.name),
            ))
        return rows
    if schema != "chaosatlas-dify-k8s-service-canaries-v1":
        raise ValueError(f"unsupported canary summary schema: {schema or '<missing>'}")
    for item in summary.get("targets") or []:
        if not isinstance(item, dict):
            continue
        target = str(item.get("target") or "")
        result_file = Path(str(item.get("result_file") or ""))
        if not result_file.is_file():
            result_file = root / target / "runtime"
            files = sorted(result_file.glob("*.json"))
            result_file = files[0] if files else Path()
        result = _read(result_file) if result_file.is_file() else {
            "action_id": item.get("action_id"),
            "status": item.get("status"),
            "outcome_status": item.get("outcome_status"),
            "attestation": item.get("attestation"),
            "errors": item.get("errors") or [],
        }
        target_root = root / target
        candidate = {
            "candidate_id": f"service:{_service_target(target)}:{summary.get('fault_family') or 'pod_kill'}",
            "target": _service_target(target),
            "target_kind": "statefulset" if target in {"redis", "postgresql", "weaviate"} else "deployment",
            "fault_family": summary.get("fault_family") or "pod_kill",
            "parameters": {"mode": "one", "duration": "30s"},
            "parameter_level": "baseline",
        }
        rows.append(record_canary_trial(
            root=target_root,
            profile=profile,
            candidate=candidate,
            result=result,
            project_inventory={"namespace": summary.get("namespace")},
            repetition=repetition_from_name(root.name),
        ))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--root", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--knowledge-root", type=Path, default=DEFAULT_KNOWLEDGE_ROOT)
    args = parser.parse_args(argv)
    profile = _read(args.profile)
    rows: list[dict[str, Any]] = []
    for root in args.root:
        rows.extend(_rows_for_root(root.resolve(), profile))
    report = aggregate_canary_trials(
        rows=rows,
        output_root=args.output.resolve(),
        knowledge_root=args.knowledge_root.resolve(),
    )
    print(json.dumps({
        "status": report["status"],
        "trial_count": report["trial_count"],
        "candidate_count": report["candidate_count"],
        "promoted": report["promotion"].get("promoted_card_ids", []),
        "output": str(args.output.resolve()),
    }, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
