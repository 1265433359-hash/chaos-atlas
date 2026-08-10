#!/usr/bin/env python3
"""Common v1.2 runner boundary with a safe, read-only dry-run mode.

The dry-run validates frozen inputs and emits the same lifecycle plan that an
adapter-backed execution must follow. Actual cluster execution is deliberately
opt-in and currently refuses to run until a project adapter is supplied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "artifacts/experiments/heldout/heldout_v12_candidate_registry.json"
DEFAULT_ADAPTERS = ROOT / "artifacts/experiments/heldout/heldout_v12_adapter_freeze.json"
DEFAULT_OUTPUT = ROOT / "artifacts/experiments/heldout/runtime_plans"
PROJECTS = {"HOTEL", "SOCIALNET", "TEASTORE"}
METHODS = {"Ours-full-pre", "Ours-generic", "ChaosEater-official", "ChaosEater-adapter", "Random"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_registry(path: Path) -> Dict[str, Any]:
    registry = json.loads(path.read_text(encoding="utf-8"))
    if registry.get("status") != "frozen":
        raise ValueError("candidate registry is not frozen")
    if registry.get("protocol") != "heldout_protocol_v1_2":
        raise ValueError("candidate registry protocol mismatch")
    candidates = registry.get("candidates")
    if not isinstance(candidates, list) or not registry.get("candidate_ids_unique"):
        raise ValueError("candidate registry uniqueness/schema check failed")
    return registry


def load_adapters(path: Path) -> Dict[str, Any]:
    adapters = json.loads(path.read_text(encoding="utf-8"))
    if adapters.get("protocol") != "heldout_protocol_v1_2":
        raise ValueError("adapter protocol mismatch")
    projects = adapters.get("projects")
    if not isinstance(projects, dict) or set(projects) != PROJECTS:
        raise ValueError("adapter project set must exactly match frozen projects")
    for project, adapter in projects.items():
        required = {"namespace", "entry_service", "entry_port", "port_forward", "baseline", "health_probe", "business_oracle", "observation", "cleanup", "static_adapter_validated", "execution_ready"}
        missing = required - set(adapter)
        if missing:
            raise ValueError(f"adapter {project} missing fields: {sorted(missing)}")
        if not adapter["static_adapter_validated"]:
            raise ValueError(f"adapter {project} is not statically validated")
        if adapter["execution_ready"] and adapter.get("runtime_validation") != "passed":
            raise ValueError(f"adapter {project} cannot be execution_ready without runtime validation")
        port_forward = adapter["port_forward"]
        if port_forward.get("service") != adapter["entry_service"] or port_forward.get("remote_port") != adapter["entry_port"]:
            raise ValueError(f"adapter {project} port-forward does not match entry service")
        for section in ("baseline", "observation", "cleanup"):
            if not isinstance(adapter[section].get("argv"), list) or not adapter[section]["argv"]:
                raise ValueError(f"adapter {project} {section} argv is required")
        if adapter["cleanup"].get("expected_stdout") != "":
            raise ValueError(f"adapter {project} cleanup must assert empty active-chaos output")
        oracle = adapter["business_oracle"]
        if oracle.get("kind") != "http_contract" or oracle.get("method") not in {"GET", "POST"} or not oracle.get("path", "/").startswith("/"):
            raise ValueError(f"adapter {project} business oracle is not an HTTP contract")
        if not isinstance(oracle.get("expected_status"), int):
            raise ValueError(f"adapter {project} oracle expected_status is required")
        evidence = oracle.get("evidence")
        if not isinstance(evidence, dict) or not evidence.get("repo") or not evidence.get("commit") or not evidence.get("path"):
            raise ValueError(f"adapter {project} oracle evidence is incomplete")
    return adapters


def validate_adapter_for_plan(adapters: Dict[str, Any], project: str) -> Dict[str, Any]:
    adapter = adapters["projects"][project]
    oracle = adapter["business_oracle"]
    return {
        "status": "static_configured_runtime_validation_pending" if not adapter["execution_ready"] else "runtime_validated",
        "namespace": adapter["namespace"],
        "entry_service": adapter["entry_service"],
        "entry_port": adapter["entry_port"],
        "port_forward": adapter["port_forward"],
        "baseline_argv": adapter["baseline"]["argv"],
        "health_probe": adapter["health_probe"],
        "business_oracle": {
            "kind": oracle["kind"],
            "method": oracle["method"],
            "path": oracle["path"],
            "expected_status": oracle["expected_status"],
            "fixture_required": oracle.get("fixture_required", False),
            "evidence": oracle["evidence"],
        },
        "observation_argv": adapter["observation"]["argv"],
        "cleanup_argv": adapter["cleanup"]["argv"],
        "cleanup_expected_stdout": adapter["cleanup"]["expected_stdout"],
        "execution_ready": adapter["execution_ready"],
    }


def resolve_repo_path(relative_path: str) -> Path:
    path = (ROOT / relative_path).resolve()
    if path != ROOT and not str(path).startswith(str(ROOT) + "\\"):
        raise ValueError(f"path escapes repository root: {relative_path}")
    return path


def validate_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    required = {"candidate_id", "project_id", "fault_family", "protection_class", "yaml_path", "yaml_sha256"}
    missing = required - set(candidate)
    if missing:
        raise ValueError(f"candidate missing fields: {sorted(missing)}")
    project = str(candidate["project_id"])
    if project not in PROJECTS:
        raise ValueError(f"unsupported project: {project}")
    yaml_path = resolve_repo_path(str(candidate["yaml_path"]))
    if not yaml_path.is_file():
        raise ValueError(f"candidate YAML missing: {yaml_path}")
    actual_hash = sha256_file(yaml_path)
    if actual_hash != candidate["yaml_sha256"]:
        raise ValueError(f"candidate YAML SHA mismatch: {candidate['candidate_id']}")
    document = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("kind") not in {"NetworkChaos", "PodChaos"}:
        raise ValueError(f"unsupported chaos document: {candidate['candidate_id']}")
    spec = document.get("spec") or {}
    if spec.get("mode") != "one":
        raise ValueError(f"candidate mode is not one: {candidate['candidate_id']}")
    fault_family = candidate["fault_family"]
    expected_kind = "PodChaos" if fault_family == "kill" else "NetworkChaos"
    if document["kind"] != expected_kind:
        raise ValueError(f"fault kind mismatch: {candidate['candidate_id']}")
    if document.get("metadata", {}).get("labels", {}).get("chaos.heldout.candidate-id") != candidate["candidate_id"]:
        raise ValueError(f"candidate label mismatch: {candidate['candidate_id']}")
    return {
        "candidate_id": candidate["candidate_id"],
        "project_id": project,
        "fault_family": fault_family,
        "protection_class": candidate["protection_class"],
        "yaml_path": candidate["yaml_path"],
        "yaml_sha256": actual_hash,
        "chaos_kind": document["kind"],
        "chaos_name": document.get("metadata", {}).get("name"),
        "namespace": document.get("metadata", {}).get("namespace"),
    }


def build_plan(registry: Dict[str, Any], adapters: Dict[str, Any], project: str, method: str, phase: str, seed: int, candidate_id: str) -> Dict[str, Any]:
    if project not in PROJECTS:
        raise ValueError(f"unsupported project: {project}")
    if method not in METHODS:
        raise ValueError(f"unsupported method: {method}")
    if phase not in {"pilot", "formal"}:
        raise ValueError(f"unsupported phase: {phase}")
    candidate = next((item for item in registry["candidates"] if item.get("candidate_id") == candidate_id), None)
    if candidate is None:
        raise ValueError(f"candidate not present in frozen registry: {candidate_id}")
    if candidate.get("project_id") != project:
        raise ValueError(f"candidate/project mismatch: {candidate_id}")
    validated = validate_candidate(candidate)
    validated_adapter = validate_adapter_for_plan(adapters, project)
    return {
        "schema_version": 1,
        "protocol": "heldout_protocol_v1_2",
        "status": "planned_no_execute",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_id": project,
        "method_id": method,
        "phase": phase,
        "seed": seed,
        "candidate": validated,
        "lifecycle": [
            "preflight",
            "baseline",
            "apply_one_fault",
            "observe",
            "recover",
            "delete_fault",
            "assert_cleanup",
            "write_ledger",
        ],
        "cleanup_contract": {
            "delete_after_observation": True,
            "assert_no_active_chaos_resource": True,
            "cleanup_failure_invalidates_run": True,
        },
        "adapter": validated_adapter,
        "execution_started": False,
        "kubectl_called": False,
        "chaos_mesh_called": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--method", required=True)
    parser.add_argument("--phase", choices=("pilot", "formal"), required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--adapters", type=Path, default=DEFAULT_ADAPTERS)
    parser.add_argument("--execute", action="store_true", help="reserved; execution remains blocked until pilot authorization")
    args = parser.parse_args()
    registry = load_registry(args.registry)
    adapters = load_adapters(args.adapters)
    plan = build_plan(registry, adapters, args.project.upper(), args.method, args.phase, args.seed, args.candidate_id)
    if args.execute:
        if not plan["adapter"]["execution_ready"]:
            raise SystemExit("EXECUTION_BLOCKED: adapter runtime validation and environment gates are not complete")
        raise SystemExit("EXECUTION_BLOCKED: execution mode remains disabled until explicit pilot authorization")
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{args.project.upper()}-{args.method}-{args.phase}-{args.seed}-{args.candidate_id}.json"
    output.write_text(json.dumps(plan, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": plan["status"], "output": str(output).replace("\\", "/")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
