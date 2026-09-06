"""Orchestrate a compiled deployment scenario without reimplementing primitives."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any, Callable

try:
    from tools.compile_scenario_node import compile_scenario
    from tools.deployment_capability import validate_scenario_node
    from tools.fault_executor import observation_verdict
except ModuleNotFoundError:
    from compile_scenario_node import compile_scenario
    from deployment_capability import validate_scenario_node
    from fault_executor import observation_verdict


Executor = Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], dict[str, Any]]


def run_scenario(
    scenario: dict[str, Any],
    *,
    compiled: dict[str, Any] | None = None,
    dry_run: bool = True,
    executor: Executor | None = None,
    execution_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors = validate_scenario_node(scenario)
    if errors:
        return {"status": "method_invalid", "errors": errors, "phases": [], "verdict": "method_invalid"}
    compiled = compiled or compile_scenario(scenario)
    if compiled.get("status") != "verified":
        return {"status": "method_invalid", "errors": compiled.get("errors", []), "phases": [], "verdict": "method_invalid"}
    if not dry_run and executor is None:
        return {"status": "environment_blocked", "errors": ["runtime executor is required"], "phases": [], "verdict": "platform_blocked"}
    output_phases: list[dict[str, Any]] = []
    for phase, compiled_phase in zip(scenario["phases"], compiled["phases"]):
        fault_results: list[dict[str, Any]] = []
        for fault, manifest in zip(phase["faults"], compiled_phase["manifests"]):
            record = {"target_node_id": fault["target_node_id"], "kind": fault["kind"], "injection_confirmed": False, "resource_uid": None, "injected_count": 0, "cleanup_confirmed": False, "errors": []}
            if not dry_run:
                try:
                    executor_manifest = copy.deepcopy(manifest)
                    if execution_context:
                        executor_manifest["chaosatlas_execution_context"] = copy.deepcopy(execution_context)
                    response = executor(executor_manifest, phase, fault) if executor else {}
                except Exception as exc:  # executor boundary is classified, never a verdict
                    error = f"{type(exc).__name__}: {exc}"
                    response = {"status": "environment_blocked", "error": error, "errors": [error]}
                if not isinstance(response, dict):
                    response = {"status": "method_invalid", "error": "executor returned non-object"}
                response_status = response.get("status", "ok")
                response_verdict = response.get("verdict") or response.get("oracle_verdict")
                if response_verdict in {None, "observation_pending"}:
                    response_verdict = observation_verdict(response.get("observation"), response_status, response.get("outcome_status"))
                injection = response.get("injection") if isinstance(response.get("injection"), dict) else {}
                record.update({"status": response_status, "error": response.get("error"), "errors": list(response.get("errors") or ([response.get("error")] if response.get("error") else [])), "action_id": response.get("action_id"), "mutation_ref": response.get("mutation_ref"), "resource_uid": response.get("resource_uid"), "injected_count": int(response.get("injected_count", 0) or 0), "injection_confirmed": bool(response.get("injection_confirmed") or int(response.get("injected_count", 0) or 0) >= 1), "injection_confirmation": injection.get("confirmation"), "cleanup_confirmed": bool(response.get("cleanup_confirmed")), "verdict": response_verdict, "raw_status": response.get("raw_status"), "outcome_status": response.get("outcome_status"), "observation_contract": response.get("observation_contract"), "baseline": response.get("baseline"), "observation": response.get("observation"), "recovery": response.get("recovery"), "cleanup": response.get("cleanup"), "attestation": response.get("attestation"), "mechanism_evidence": response.get("mechanism_evidence")})
            fault_results.append(record)
        if not dry_run and any(item.get("status") in {"environment_blocked", "apply_failed", "method_invalid"} for item in fault_results):
            status = next(item["status"] for item in fault_results if item.get("status") in {"environment_blocked", "apply_failed", "method_invalid"})
            output_phases.append({"phase_id": phase["phase_id"], "mode": phase["mode"], "faults": fault_results, "observation_started": False, "cleanup_confirmed": False})
            return {"status": status, "phases": output_phases, "verdict": "platform_blocked" if status == "environment_blocked" else status}
        if not dry_run and not all(item["injection_confirmed"] for item in fault_results):
            output_phases.append({"phase_id": phase["phase_id"], "mode": phase["mode"], "faults": fault_results, "observation_started": False, "cleanup_confirmed": False})
            return {"status": "injection_not_confirmed", "phases": output_phases, "verdict": "injection_not_confirmed"}
        phase_verdicts = [item.get("verdict") for item in fault_results if item.get("verdict")]
        phase_cleanup = bool(fault_results) and all(item.get("cleanup_confirmed") for item in fault_results)
        output_phases.append({"phase_id": phase["phase_id"], "mode": phase["mode"], "faults": fault_results, "observation_started": not dry_run, "cleanup_confirmed": False if dry_run else phase_cleanup, "observation_window": {"duration_s": phase["duration_s"]}, "recovery_window": {"deadline_s": (scenario.get("recovery") or {}).get("deadline_s")}, "verdict": phase_verdicts[0] if phase_verdicts else None})
    verdicts = [phase.get("verdict") for phase in output_phases if phase.get("verdict")]
    return {"schema_version": 1, "status": "dry_run" if dry_run else "executed", "scenario_id": scenario["scenario_id"], "scenario_hash": compiled.get("scenario_hash"), "seed": scenario.get("seed"), "oracle": scenario.get("oracle"), "recovery": scenario.get("recovery"), "cleanup": scenario.get("cleanup"), "phases": output_phases, "verdict": "not_run" if dry_run else (verdicts[0] if verdicts else "observation_pending")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = json.loads(args.scenario.read_text(encoding="utf-8"))
    result = run_scenario(value, dry_run=args.dry_run)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "run.json").write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(args.output)}, ensure_ascii=True))
    return 0 if result["status"] in {"dry_run", "executed"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
