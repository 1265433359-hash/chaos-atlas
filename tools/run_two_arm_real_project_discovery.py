"""Convert one model output into an auditable runtime handoff.

This module never calls a model and never mutates Kubernetes.  A separate
authorized adapter may consume the handoff only after all runtime gates pass.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from tools.chaosatlas_two_arm_protocol import MAX_EXECUTED_HYPOTHESES, REPETITIONS, canonical_sha256, select_execution_hypotheses
    from tools.open_discovery_compiler import compile_output, contract_from_topology
except ModuleNotFoundError:
    from chaosatlas_two_arm_protocol import MAX_EXECUTED_HYPOTHESES, REPETITIONS, canonical_sha256, select_execution_hypotheses
    from open_discovery_compiler import compile_output, contract_from_topology


def build_discovery_handoff(bundle: dict[str, Any], model_output: dict[str, Any], runtime_profile: dict[str, Any]) -> dict[str, Any]:
    if runtime_profile.get("runtime_ready") is not True:
        raise ValueError("runtime profile is not ready")
    common = bundle.get("common_input") or {}
    topology = common.get("topology") or {}
    project_id = str(bundle.get("project_id") or common.get("project_id"))
    project_commit = str(common.get("project_commit", ""))
    namespace = str(common.get("namespace", ""))
    contract = contract_from_topology(
        project_id,
        project_commit,
        namespace,
        workload_id="topology-backed-workload",
        workload_contract="frozen-business-oracle",
        topology=topology,
    )
    compiled = compile_output(model_output, contract)
    if compiled.get("status") != "valid":
        return {
            "status": "method_invalid",
            "project_id": project_id,
            "method_id": bundle.get("method_id"),
            "seed": bundle.get("seed"),
            "prompt_input_sha256": canonical_sha256(bundle),
            "model_output_sha256": canonical_sha256(model_output),
            "compiled": compiled,
            "runtime_units": [],
        }
    candidates = [{**item, "compile_status": "accepted"} for item in compiled.get("accepted", [])]
    selection = select_execution_hypotheses(candidates)
    selected = selection["selected"]
    runtime_units = [
        {
            "hypothesis_id": item["hypothesis_id"],
            "canonical_signature": item["canonical_signature"],
            "replicate": replicate,
            "execution_started": False,
            "status": "pending_runtime_adapter",
        }
        for item in selected
        for replicate in range(1, REPETITIONS + 1)
    ]
    return {
        "schema_version": "chaosatlas-two-arm-discovery-handoff-v1",
        "status": "handoff_ready",
        "project_id": project_id,
        "method_id": bundle.get("method_id"),
        "seed": bundle.get("seed"),
        "prompt_input_sha256": canonical_sha256(bundle),
        "model_output_sha256": canonical_sha256(model_output),
        "model_call": {"performed": False, "credentials_logged": False},
        "compiled": compiled,
        "selected_hypotheses": selected,
        "budget_not_executed": selection["budget_not_executed"],
        "runtime_units": runtime_units,
        "max_executed_hypotheses": MAX_EXECUTED_HYPOTHESES,
        "repetitions": REPETITIONS,
        "human_review": "pending",
        "knowledge_base_updated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--model-output", type=Path, required=True)
    parser.add_argument("--runtime-profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_discovery_handoff(
        json.loads(args.bundle.read_text(encoding="utf-8")),
        json.loads(args.model_output.read_text(encoding="utf-8")),
        json.loads(args.runtime_profile.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "runtime_units": len(result["runtime_units"])}, ensure_ascii=True))
    return 0 if result["status"] in {"handoff_ready", "method_invalid"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
