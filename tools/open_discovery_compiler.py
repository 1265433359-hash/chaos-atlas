"""Fail-closed compiler for open-discovery fault hypotheses.

The compiler validates model output against a project runtime contract. It does
not execute kubectl, create Chaos Mesh objects, or repair malformed output.
Candidate-pool matching is performed only after validation and is reported as a
known/novel annotation rather than being used as an input constraint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


FAULT_FAMILIES = {"pod_kill", "network_delay", "network_loss", "container_cpu_stress"}
FORBIDDEN_KEYS = {"candidate_id", "candidate_pool", "oracle_label", "prior_selection", "runtime_observation", "post_run_rca", "mutation_path", "shell_command", "kubectl_command"}
NONEMPTY_FIELDS = ("hypothesis", "weakness_surface", "expected_invariant", "validation_plan", "recovery_expectation")


@dataclass(frozen=True)
class RuntimeContract:
    project_id: str
    project_commit: str
    namespace: str
    targets: frozenset[str]
    workload_id: str
    workload_contract: str
    max_hypotheses: int = 8
    target_kinds: dict[str, str] | None = None
    target_resolvers: dict[str, str] | None = None
    target_roles: dict[str, str] | None = None
    target_fault_families: dict[str, frozenset[str]] | None = None


def contract_from_topology(
    project_id: str,
    project_commit: str,
    namespace: str,
    workload_id: str,
    workload_contract: str,
    topology: dict[str, Any],
    max_hypotheses: int = 8,
) -> RuntimeContract:
    """Build a fail-closed contract from the deterministic topology IR.

    Resolver values are static namespace-local intents.  They are not kubectl
    commands and still require a runtime adapter before execution.
    """
    targets: set[str] = set()
    kinds: dict[str, str] = {}
    resolvers: dict[str, str] = {}
    roles: dict[str, str] = {}
    fault_families: dict[str, frozenset[str]] = {}
    for node in topology.get("nodes", []):
        target = str(node.get("id", ""))
        if not target:
            continue
        role = str(node.get("role", ""))
        if role not in {"workload", "routing", "entrypoint"}:
            continue
        targets.add(target)
        kinds[target] = "service"
        roles[target] = role
        resource_kind = str(node.get("kind", "resource")).lower()
        name = str(node.get("name") or target.rsplit('/', 1)[-1])
        resolvers[target] = f"{namespace}/{resource_kind}/{name}"
        fault_families[target] = frozenset(FAULT_FAMILIES if role == "workload" else {"network_delay", "network_loss"})
    for edge in topology.get("edges", []):
        source, target = str(edge.get("source", "")), str(edge.get("target", ""))
        if not source or not target:
            continue
        if source not in targets or target not in targets:
            continue
        edge_id = f"{source}->{target}"
        targets.add(edge_id)
        kinds[edge_id] = "dependency_edge"
        resolvers[edge_id] = f"{namespace}/edge/{source.rsplit('/', 1)[-1]}->{target.rsplit('/', 1)[-1]}"
        fault_families[edge_id] = frozenset({"network_delay", "network_loss"})
    return RuntimeContract(project_id, project_commit, namespace, frozenset(targets), workload_id, workload_contract, max_hypotheses, kinds, resolvers, roles, fault_families)


def _walk_forbidden(value: Any, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in FORBIDDEN_KEYS:
                hits.append(f"{path}.{key}")
            hits.extend(_walk_forbidden(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            hits.extend(_walk_forbidden(item, f"{path}[{index}]"))
    return hits


def _signature(item: dict[str, Any]) -> str:
    data = {"target": item["target"], "target_kind": item["target_kind"], "fault_family": item["fault_family"], "parameters": item["parameters"]}
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _validate_parameters(family: str, params: Any) -> str | None:
    if not isinstance(params, dict):
        return "parameters must be an object"
    if family == "pod_kill":
        if params != {"mode": "one"}:
            return "pod_kill parameters must be exactly {'mode': 'one'}"
        return None
    bounds: dict[str, tuple[int, int]] = {
        "network_delay": {"latency_ms": (1, 500), "duration_s": (1, 60)},
        "network_loss": {"loss_percent": (1, 100), "duration_s": (1, 60)},
        "container_cpu_stress": {"workers": (1, 2), "load_percent": (1, 80), "duration_s": (1, 60)},
    }[family]
    if set(params) != set(bounds):
        return f"parameters must contain exactly {sorted(bounds)}"
    for name, (low, high) in bounds.items():
        value = params.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            return f"{name} must be an integer in [{low}, {high}]"
    return None


def compile_output(payload: dict[str, Any], contract: RuntimeContract, known_signatures: set[str] | None = None) -> dict[str, Any]:
    known_signatures = known_signatures or set()
    errors: list[dict[str, Any]] = []
    if _walk_forbidden(payload):
        return {"status": "method_invalid", "accepted": [], "rejected": [{"reason": "forbidden_field", "paths": _walk_forbidden(payload)}]}
    if payload.get("project_id") != contract.project_id or payload.get("project_commit") != contract.project_commit:
        return {"status": "method_invalid", "accepted": [], "rejected": [{"reason": "project_identity_mismatch"}]}
    hypotheses = payload.get("hypotheses")
    if not isinstance(hypotheses, list) or len(hypotheses) > contract.max_hypotheses:
        return {"status": "method_invalid", "accepted": [], "rejected": [{"reason": "hypotheses must be a list of at most 8"}]}
    if not hypotheses and not str(payload.get("no_safe_hypothesis_reason", "")).strip():
        return {"status": "method_invalid", "accepted": [], "rejected": [{"reason": "empty output requires no_safe_hypothesis_reason"}]}
    seen: set[str] = set()
    accepted: list[dict[str, Any]] = []
    for index, item in enumerate(hypotheses):
        if not isinstance(item, dict):
            errors.append({"index": index, "reason": "hypothesis must be an object"})
            continue
        missing = [field for field in ("hypothesis_id", "target", "target_kind", "fault_family", "parameters", *NONEMPTY_FIELDS) if not str(item.get(field, "")).strip()]
        if missing:
            errors.append({"index": index, "reason": "missing_required_fields", "fields": missing})
            continue
        if item["target_kind"] not in {"service", "dependency_edge"}:
            errors.append({"index": index, "reason": "unsupported_target_kind"})
            continue
        if item["target"] not in contract.targets:
            errors.append({"index": index, "reason": "target_not_in_deployment", "target": item["target"]})
            continue
        if contract.target_kinds and contract.target_kinds.get(item["target"]) not in (None, item["target_kind"]):
            errors.append({"index": index, "reason": "target_kind_mismatch", "target": item["target"], "expected": contract.target_kinds.get(item["target"])})
            continue
        family = item["fault_family"]
        if family not in FAULT_FAMILIES:
            errors.append({"index": index, "reason": "unsupported_fault_family", "fault_family": family})
            continue
        if contract.target_fault_families and family not in contract.target_fault_families.get(item["target"], frozenset()):
            errors.append({"index": index, "reason": "fault_family_not_supported_for_target", "target": item["target"], "fault_family": family})
            continue
        call_chain = item.get("call_chain")
        if not isinstance(call_chain, list) or not call_chain:
            errors.append({"index": index, "reason": "call_chain_required"})
            continue
        bad_chain = []
        for chain_index, link in enumerate(call_chain):
            if not isinstance(link, dict) or not all(str(link.get(field, "")).strip() for field in ("source", "target", "relation", "evidence_ref")):
                bad_chain.append(chain_index)
                continue
            if link["source"] not in contract.targets or link["target"] not in contract.targets:
                bad_chain.append(chain_index)
        if bad_chain:
            errors.append({"index": index, "reason": "call_chain_not_backed_by_topology", "links": bad_chain})
            continue
        parameter_error = _validate_parameters(family, item["parameters"])
        if parameter_error:
            errors.append({"index": index, "reason": parameter_error})
            continue
        signature = _signature(item)
        if signature in seen:
            errors.append({"index": index, "reason": "duplicate_hypothesis"})
            continue
        seen.add(signature)
        accepted.append({
            "hypothesis_id": str(item["hypothesis_id"]),
            "canonical_signature": signature,
            "novelty": "known_candidate" if signature in known_signatures else "novel_candidate",
            "status": "accepted_known_candidate" if signature in known_signatures else "accepted_novel_candidate",
            "project_id": contract.project_id,
            "namespace": contract.namespace,
            "workload_id": contract.workload_id,
            "workload_contract": contract.workload_contract,
            "target": item["target"],
            "resolved_target": (contract.target_resolvers or {}).get(item["target"]),
            "resolver_status": "static_only" if contract.target_resolvers and item["target"] in contract.target_resolvers else "pending_runtime_resolver",
            "target_kind": item["target_kind"],
            "fault_family": family,
            "parameters": item["parameters"],
            "hypothesis": item["hypothesis"],
            "expected_invariant": item["expected_invariant"],
            "validation_plan": item["validation_plan"],
            "recovery_expectation": item["recovery_expectation"],
            "call_chain": item.get("call_chain", []),
            "weakness_surface": item["weakness_surface"],
            "execution_ready": False,
        })
    status = "valid" if accepted or not hypotheses else "method_invalid"
    return {"status": status, "accepted": accepted, "rejected": errors, "accepted_count": len(accepted), "rejected_count": len(errors), "compiler": "open_discovery_compiler_v1"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--targets", default="", help="comma-separated deployment targets when --topology is not supplied")
    parser.add_argument("--topology", type=Path, help="topology IR JSON; builds target and fault-family contract")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--project-commit", required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--workload-id", required=True)
    parser.add_argument("--workload-contract", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if args.topology:
        contract = contract_from_topology(args.project_id, args.project_commit, args.namespace, args.workload_id, args.workload_contract, json.loads(args.topology.read_text(encoding="utf-8")))
    else:
        if not args.targets:
            parser.error("one of --topology or --targets is required")
        contract = RuntimeContract(args.project_id, args.project_commit, args.namespace, frozenset(filter(None, args.targets.split(","))), args.workload_id, args.workload_contract)
    result = compile_output(payload, contract)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "accepted": result.get("accepted_count", 0), "rejected": result.get("rejected_count", 0)}, indent=2))
    return 0 if result["status"] in {"valid"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
