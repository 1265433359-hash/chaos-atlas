"""Structured, reversible manifest improvement proposals and retest labels."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any

import yaml

_ALLOWED_PATCH_PREFIXES = (
    "/spec/replicas",
    "/spec/minAvailable",
    "/spec/maxUnavailable",
    "/spec/minReplicas",
    "/spec/maxReplicas",
    "/spec/targetCPUUtilizationPercentage",
    "/spec/template/spec/containers/0/readinessProbe",
    "/spec/template/spec/containers/0/livenessProbe",
    "/spec/template/spec/containers/0/resources/requests",
    "/spec/template/spec/containers/0/resources/limits",
)


def _proposal(
    source_ref: str,
    pointer: str,
    old: Any,
    new: Any,
    reason: str,
    expected: str,
    document_selector: dict[str, str] | None = None,
) -> dict[str, Any]:
    proposal = {
        "source_ref": source_ref,
        "json_pointer": pointer,
        "old_value": copy.deepcopy(old),
        "new_value": copy.deepcopy(new),
        "reason": reason,
        "expected_oracle_change": expected,
        "rollback": {"json_pointer": pointer, "value": copy.deepcopy(old)},
    }
    if document_selector:
        proposal["document_selector"] = copy.deepcopy(document_selector)
    return proposal


def propose_improvements(node: dict[str, Any], outcome: str) -> list[dict[str, Any]]:
    if outcome not in {"availability_degraded", "recovery_timeout"}:
        return []
    refs = node.get("source_refs") or []
    if not refs:
        return []
    deployment = node.get("deployment") or {}
    replicas = deployment.get("desired_replicas")
    deployment_name = str(deployment.get("name") or "")
    document_selector = {"kind": "Deployment", "name": deployment_name} if deployment_name else None
    proposals: list[dict[str, Any]] = []
    if isinstance(replicas, int) and replicas >= 1:
        proposals.append(_proposal(str(refs[0]), "/spec/replicas", replicas, replicas + 1, "add replacement capacity", "availableReplicas ratio and recovery identity should improve", document_selector))
    proposals.append(_proposal(str(refs[0]), "/spec/template/spec/containers/0/readinessProbe", None, {"httpGet": {"path": "/ready", "port": 8080}}, "declare readiness for business traffic", "exclude Running-but-not-ready false recovery", document_selector))
    proposals.append(_proposal(str(refs[0]), "/spec/template/spec/containers/0/resources/limits/cpu", None, "500m", "bound CPU contention", "reduce stress-induced recovery timeout", document_selector))
    return proposals


def _pointer_set(document: Any, pointer: str, value: Any, expected_old: Any) -> None:
    if not pointer.startswith("/"):
        raise ValueError("JSON Pointer must start with /")
    parts = [item.replace("~1", "/").replace("~0", "~") for item in pointer[1:].split("/")]
    current = document
    for part in parts[:-1]:
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise ValueError("JSON Pointer parent does not exist")
    leaf = parts[-1]
    if isinstance(current, list):
        index = int(leaf)
        old = current[index] if index < len(current) else None
        if expected_old is not None and old != expected_old: raise ValueError("old value mismatch")
        if index == len(current): current.append(copy.deepcopy(value))
        else: current[index] = copy.deepcopy(value)
    elif isinstance(current, dict):
        old = current.get(leaf)
        if expected_old is not None and old != expected_old: raise ValueError("old value mismatch")
        current[leaf] = copy.deepcopy(value)
    else:
        raise ValueError("JSON Pointer parent is not mutable")


def _select_manifest_document(docs: list[Any], selector: Any) -> tuple[dict[str, Any], int]:
    if selector is None:
        if not docs or not isinstance(docs[0], dict):
            raise ValueError("manifest document is not an object")
        return docs[0], 0
    if not isinstance(selector, dict):
        raise ValueError("document_selector must be an object")
    kind = str(selector.get("kind") or "")
    name = str(selector.get("name") or "")
    if not kind or not name:
        raise ValueError("document_selector requires kind and name")
    matches: list[tuple[int, dict[str, Any]]] = []
    for index, document in enumerate(docs):
        if not isinstance(document, dict):
            continue
        metadata = document.get("metadata")
        if document.get("kind") == kind and isinstance(metadata, dict) and metadata.get("name") == name:
            matches.append((index, document))
    if len(matches) != 1:
        raise ValueError(f"document_selector matched {len(matches)} documents")
    return matches[0][1], matches[0][0]


def apply_patch_copy(source_root: Path, proposal: dict[str, Any], output_root: Path) -> dict[str, Any]:
    source_root, output_root = Path(source_root), Path(output_root)
    ref = str(proposal.get("source_ref") or "").replace("\\", "/")
    if not ref or ref.startswith("/") or ":" in ref or ".." in ref.split("/"):
        return {"status": "method_invalid", "error": "unsafe source_ref"}
    pointer = str(proposal.get("json_pointer") or "")
    if not any(
        pointer == allowed or pointer.startswith(allowed + "/")
        for allowed in _ALLOWED_PATCH_PREFIXES
    ):
        return {"status": "method_invalid", "error": "patch pointer is outside structured improvement allow-list"}
    source_file = source_root / ref
    if not source_file.is_file():
        return {"status": "method_invalid", "error": "source_ref missing"}
    if output_root.exists() and any(output_root.iterdir()):
        return {"status": "method_invalid", "error": "output copy must be fresh"}
    shutil.copytree(source_root, output_root, dirs_exist_ok=True)
    target = output_root / ref
    try:
        docs = list(yaml.safe_load_all(target.read_text(encoding="utf-8")))
        document, _ = _select_manifest_document(docs, proposal.get("document_selector"))
        _pointer_set(document, str(proposal["json_pointer"]), proposal.get("new_value"), proposal.get("old_value"))
        target.write_text(yaml.safe_dump_all(docs, sort_keys=False), encoding="utf-8")
    except (OSError, ValueError, yaml.YAMLError, KeyError, IndexError) as exc:
        return {"status": "deployment_blocked", "error": str(exc)}
    return {
        "status": "applied",
        "source_ref": ref,
        "output_root": str(output_root),
        "document_selector": copy.deepcopy(proposal.get("document_selector")),
        "rollback": proposal.get("rollback"),
    }


def classify_retest(environment_status: str, *, baseline: str, after: str) -> str:
    if environment_status in {"environment_blocked", "platform_blocked", "deployment_blocked"}:
        return "deployment_blocked"
    if after in {"availability_degraded", "recovery_timeout", "probe_restart_escape", "no_readiness_false_recovery"}:
        return "regression"
    if baseline in {"availability_degraded", "recovery_timeout"} and after == "availability_defended":
        return "improvement_verified"
    return "not_run"


def build_improvement_evidence(result: dict[str, Any]) -> dict[str, Any]:
    """Project a retest into a bounded counterfactual evidence record."""

    status = str(result.get("status") or "not_run")
    allowed = status == "improvement_verified"
    comparison = result.get("comparison") if isinstance(result.get("comparison"), dict) else {}
    return {
        "schema_version": "chaosatlas-improvement-evidence-v1",
        "status": status if status in {"improvement_verified", "regression", "deployment_blocked", "not_run"} else "not_run",
        "baseline_verdict": (result.get("baseline") or {}).get("verdict"),
        "after_verdict": (result.get("after") or {}).get("verdict"),
        "same_scenario_contract": comparison.get("same_scenario_contract") is True,
        "cleanup_verified": comparison.get("cleanup_verified") is True,
        "knowledge_update_allowed": allowed and comparison.get("same_scenario_contract") is True and comparison.get("cleanup_verified") is True,
        "defense_claim": "improvement_verified" if allowed and comparison.get("same_scenario_contract") is True and comparison.get("cleanup_verified") is True else None,
        "counterfactual_scope": "same scenario, seed, oracle, recovery and cleanup contract",
    }


def _scenario_contract(scenario: dict[str, Any], compiled: dict[str, Any]) -> dict[str, Any]:
    return {
        "scenario_id": scenario.get("scenario_id"),
        "scenario_hash": compiled.get("scenario_hash"),
        "seed": scenario.get("seed"),
        "oracle": copy.deepcopy(scenario.get("oracle")),
        "recovery": copy.deepcopy(scenario.get("recovery")),
        "cleanup": copy.deepcopy(scenario.get("cleanup")),
    }


def run_improvement_retest(
    *,
    scenario: dict[str, Any],
    source_root: Path,
    output_root: Path,
    proposal: dict[str, Any],
    baseline_result: dict[str, Any],
    executor: Any = None,
    dry_run: bool = True,
    server_side_dry_run: Any = None,
) -> dict[str, Any]:
    """Apply one structured proposal to an immutable copy and rerun the same scenario."""

    from tools.compile_scenario_node import compile_scenario
    from tools.run_deployment_scenario import run_scenario

    compiled = compile_scenario(scenario)
    if compiled.get("status") != "verified":
        return {
            "status": "not_run",
            "reason": "scenario_compile_failed",
            "defense_conclusion_allowed": False,
        }
    contract = _scenario_contract(scenario, compiled)
    baseline_contract = {
        key: baseline_result.get(key)
        for key in ("scenario_id", "scenario_hash", "seed", "oracle", "recovery", "cleanup")
    }
    same_contract = baseline_contract == contract
    comparison = {
        "same_scenario_contract": same_contract,
        "scenario_id": contract["scenario_id"],
        "scenario_hash": contract["scenario_hash"],
        "seed": contract["seed"],
        "oracle": contract["oracle"],
        "recovery": contract["recovery"],
        "cleanup": contract["cleanup"],
    }
    if not same_contract:
        return {
            "status": "not_run",
            "reason": "baseline_contract_mismatch",
            "comparison": comparison,
            "defense_conclusion_allowed": False,
        }

    patched = apply_patch_copy(source_root, proposal, output_root)
    if patched.get("status") != "applied":
        return {
            "status": "not_run",
            "reason": patched.get("error", "patch_not_applied"),
            "patch": patched,
            "comparison": comparison,
            "defense_conclusion_allowed": False,
        }

    if server_side_dry_run is not None:
        try:
            validation = server_side_dry_run(
                proposal=copy.deepcopy(proposal),
                source_root=Path(output_root),
                scenario=copy.deepcopy(scenario),
                compiled=copy.deepcopy(compiled),
            )
        except Exception as exc:
            return {
                "status": "deployment_blocked",
                "reason": f"server_side_dry_run_failed: {type(exc).__name__}",
                "error": str(exc),
                "patch": patched,
                "comparison": comparison,
                "defense_conclusion_allowed": False,
            }
        if not isinstance(validation, dict) or str(validation.get("status")) not in {
            "ready",
            "verified",
            "dry_run_passed",
            "dry_run_ready",
            "ready_for_deploy",
        }:
            return {
                "status": "deployment_blocked",
                "reason": (validation or {}).get("reason", "server_side_dry_run_not_ready") if isinstance(validation, dict) else "server_side_dry_run_not_ready",
                "server_side_dry_run": validation,
                "patch": patched,
                "comparison": comparison,
                "defense_conclusion_allowed": False,
            }

    after = run_scenario(
        scenario,
        compiled=compiled,
        dry_run=dry_run,
        executor=executor,
        execution_context={
            "source_root": str(Path(source_root)),
            "patched_root": str(Path(output_root)),
            "proposal": copy.deepcopy(proposal),
        },
    )
    cleanup_ok = all(
        phase.get("cleanup_confirmed") is True
        for phase in after.get("phases", [])
    ) if after.get("phases") else False
    status = classify_retest(
        str(after.get("status") or "not_run"),
        baseline=str(baseline_result.get("verdict") or "not_run"),
        after=str(after.get("verdict") or "not_run"),
    )
    if status == "improvement_verified" and not cleanup_ok:
        status = "deployment_blocked"
    result = {
        "status": status,
        "patch": patched,
        "baseline": baseline_result,
        "after": after,
        "comparison": {**comparison, "cleanup_verified": cleanup_ok},
        "defense_conclusion_allowed": status == "improvement_verified" and same_contract and cleanup_ok,
    }
    result["improvement_evidence"] = build_improvement_evidence(result)
    return result
