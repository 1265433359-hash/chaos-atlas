"""Unified ChaosAtlas dry-run and live orchestration engine."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

from tools.chaosatlas_adapters import KnowledgeProvider, OfflineProjectAdapter
from tools.chaosatlas_contracts import (
    STAGES,
    RunContext,
    StageResult,
    load_checkpoint,
    write_checkpoint,
    write_stage_artifact,
)
from tools.chaosatlas_hypothesis import (
    build_deterministic_hypotheses,
    build_hypothesis_input,
    build_hypotheses_with_advisory,
    rank_candidates,
)
from tools.compile_scenario_node import compile_scenario
from tools.deployment_capability import build_deployment_node, build_scenario_node
from tools.run_deployment_scenario import run_scenario
from tools.kubernetes_lifecycle_executor import KubernetesLifecycleExecutor
from chaosatlas.oracles import DEFAULT_ORACLE_REGISTRY, OracleRegistry
from tools.kubernetes_fault_executor import KubernetesApiFaultExecutor, ControlPlaneDelayExecutor
from tools.minikube_control_plane_mutator import MinikubeControlPlaneMutator
from tools.native_resource_fault_executor import NativeResourceFaultExecutor
from tools.native_http_fault_executor import NativeHttpFaultExecutor
from tools.kubernetes_project_adapter import KubernetesProjectAdapter
from tools.kubernetes_evidence import KubernetesEvidenceCollector
from tools.evidence_collectors import collect_file_evidence, collect_unavailable_evidence
from tools.evidence_action_planner import build_evidence_plan
from tools.planned_evidence import collect_planned_evidence
from tools.chaosatlas_runtime_preflight import KubernetesPreflight
from tools.project_onboarding import validate_project_profile
from tools.run_chaos_experiment import run_kubectl
from tools.compile_rca_regression import compile_regression_intents, project_knowledge_draft
from tools.discovery_to_rca import build_case_from_hypothesis
from tools.rca_loop import make_evidence
from tools.rca_runtime_loop import ingest_action_result
from tools.defense_promotion_stage import promote_from_history
from tools.phase6_audit import build_execution_contract, write_phase6_audit
from tools.knowledge_migration_audit import build_consumption_report
from tools.hypothesis_registry import build_hypothesis_registry, build_project_portrait
from tools.registry_shadow import build_registry_shadow, evaluate_registry_quality
from tools.reproduction_policy import MIN_STABLE_REPRODUCTIONS


@dataclass(frozen=True)
class RunRequest:
    """Validated configuration for one unified ChaosAtlas engine invocation."""

    profile_path: Path
    output_root: Path
    mode: str = "dry-run"
    seed: int = 1001
    resume: bool = False
    knowledge_root: Path | None = None
    approve_live: bool = False
    candidate_id: str | None = None
    defense_history_root: Path | None = None
    knowledge_write_root: Path | None = None
    advisory_provider: Callable[[dict[str, Any]], Any] | None = None
    policy_hypothesis: dict[str, Any] | None = None
    registry_shadow: bool = False
    kube_context: str | None = None
    all_candidates: bool = False
    max_candidates: int | None = None
    policy_mode: str = "legacy"
    policy_state_path: Path | None = None
    policy_context: dict[str, Any] | None = None
    policy_budget: int = 20

    def __post_init__(self) -> None:
        object.__setattr__(self, "profile_path", Path(self.profile_path))
        object.__setattr__(self, "output_root", Path(self.output_root))
        for name in ("knowledge_root", "defense_history_root", "knowledge_write_root", "policy_state_path"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, Path(value))
        if self.mode not in {"dry-run", "live"}:
            raise ValueError(f"unsupported run mode: {self.mode}")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValueError("seed must be an integer")
        if isinstance(self.policy_budget, bool) or int(self.policy_budget) < 1:
            raise ValueError("policy_budget must be a positive integer")
        if self.max_candidates is not None and (
            isinstance(self.max_candidates, bool) or int(self.max_candidates) < 1
        ):
            raise ValueError("max_candidates must be a positive integer")
        if self.mode == "dry-run" and (self.all_candidates or self.max_candidates is not None):
            raise ValueError("dry-run candidate batching is not supported")


@dataclass(frozen=True)
class RunDependencies:
    """Replaceable capabilities owned by the unified composition root."""

    oracle_registry: OracleRegistry = field(default_factory=lambda: DEFAULT_ORACLE_REGISTRY)
    live_executor: Callable[..., dict[str, Any]] | None = None
    live_adapter: Any | None = None
    live_evidence_collector: Any | None = None
    live_preflight: Any | None = None


class PlanExecutor:
    """Describe an execution without fabricating runtime observations."""

    def run(self, plan: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "not_run",
            "execution_status": "not_run",
            "claim_scope": "planned",
            "plan": dict(plan),
            "observation": {
                "status": "not_run",
                "claim_scope": "planned",
                "reason": "dry-run does not execute runtime mutations",
            },
            "cleanup_confirmed": False,
        }


REQUIRED_ALIASES = {
    "inventory": "inventory.json",
    "server_deployment_detection": "server_deployment_detection.json",
    "mapping": "candidate_space.json",
    "retrieval": "retrieval.json",
    "hypotheses": "hypotheses.json",
    "classify": "finding_report.json",
    "rca": "rca_report.json",
    "learn": "knowledge_draft.json",
    "regression": "regression_intents.json",
    "cleanup_report": "cleanup_report.json",
}


def _find_candidate(
    candidates: list[dict[str, Any]], candidate_id: str | None, *, project_id: str = ""
) -> dict[str, Any] | None:
    """Resolve exact runtime IDs or stable project/target/fault aliases."""
    if not candidate_id:
        return None
    requested = str(candidate_id)
    for item in candidates:
        if isinstance(item, dict) and str(item.get("candidate_id") or "") == requested:
            return item
    project = str(project_id or "").strip()
    if not project:
        return None
    matches = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        target = str(item.get("target") or "").strip()
        family = str(item.get("fault_family") or "").strip()
        stable = f"server:deployment:{project}:{target}:{family}"
        if target and family and stable == requested:
            matches.append(item)
    return matches[0] if len(matches) == 1 else None


def _find_oracle_candidate(
    candidates: list[dict[str, Any]], oracle_service: str
) -> dict[str, Any] | None:
    """Prefer the pod-kill candidate that owns the declared business service."""
    service = str(oracle_service or "").strip()
    if not service:
        return None
    matches = [
        item
        for item in candidates
        if isinstance(item, dict)
        and (
            str(item.get("target") or "") == service
            or str(item.get("service_target") or "") == service
        )
    ]
    return next(
        (item for item in matches if str(item.get("fault_family") or "") == "pod_kill"),
        matches[0] if matches else None,
    )


def _read_json(path: Path) -> dict[str, Any]:
    # Windows PowerShell's `Set-Content -Encoding UTF8` emits a BOM.
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _payload_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _bounded_artifact_path(root: Path, directory: str, logical_name: str, suffix: str = ".json") -> Path:
    """Keep generated artifact paths below Windows' legacy MAX_PATH limit."""
    artifact_dir = Path(root).expanduser().resolve() / directory
    path = artifact_dir / f"{logical_name}{suffix}"
    if len(str(path)) < 240:
        return path
    digest = hashlib.sha256(str(logical_name).encode("utf-8")).hexdigest()[:12]
    return artifact_dir / f"artifact-{digest}{suffix}"


def _write_alias(output_root: Path, source: Path, name: str) -> None:
    destination = output_root / name
    if destination != source:
        shutil.copyfile(source, destination)


def _write_evidence_plan(output_root: Path, payload: dict[str, Any]) -> None:
    """Write the advisory plan as a non-stage artifact for audit/checkpoint reuse."""
    envelope = {
        "schema_version": "chaosatlas-evidence-plan-artifact-v1",
        "stage": "evidence_plan",
        "status": "completed" if payload.get("status") == "planned" else "blocked",
        "claim_scope": "advisory",
        "payload": payload,
        "output_sha256": hashlib.sha256(
            json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }
    _write_text(output_root / "evidence_plan.json", json.dumps(envelope, indent=2, ensure_ascii=False) + "\n")


def _write_advisory_artifact(output_root: Path, name: str, payload: dict[str, Any]) -> None:
    """Persist a non-stage portrait/registry without granting runtime claims."""
    envelope = {
        "schema_version": "chaosatlas-advisory-artifact-v1",
        "artifact": name,
        "status": "completed",
        "claim_scope": "advisory",
        "payload": payload,
        "output_sha256": hashlib.sha256(
            json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }
    _write_text(output_root / f"{name}.json", json.dumps(envelope, indent=2, ensure_ascii=False) + "\n")


def _write_support_artifact(
    output_root: Path,
    name: str,
    payload: dict[str, Any],
    *,
    claim_scope: str = "advisory",
) -> None:
    """Persist an auditable non-stage decision without promoting it to evidence."""
    envelope = {
        "schema_version": "chaosatlas-support-artifact-v1",
        "artifact": name,
        "status": "completed",
        "claim_scope": claim_scope,
        "payload": payload,
        "output_sha256": _payload_sha256(payload),
    }
    _write_text(output_root / f"{name}.json", json.dumps(envelope, indent=2, ensure_ascii=False) + "\n")


def _read_advisory_artifact(output_root: Path, name: str) -> dict[str, Any]:
    value = _read_json(output_root / f"{name}.json")
    payload = value.get("payload") if isinstance(value.get("payload"), dict) else value
    if not isinstance(payload, dict):
        raise ValueError(f"invalid advisory artifact: {name}")
    return payload


def _facts_path(project_id: str) -> Path:
    module_path = Path(__file__).resolve()
    repository_root = _REPOSITORY_ROOT
    roots = (
        repository_root / "tests" / "fixtures" / "chaosatlas_offline" / project_id,
        module_path.parent / "tests" / "fixtures" / "chaosatlas_offline" / project_id,
    )
    for root in roots:
        runtime_variant = root / "project_facts_runtime.json"
        facts = runtime_variant if project_id != project_id.lower() and runtime_variant.is_file() else root / "project_facts.json"
        if facts.is_file():
            return facts
    return roots[0] / "project_facts.json"


def _stage(
    output_root: Path,
    completed: list[str],
    stage: str,
    payload: dict[str, Any],
    *,
    claim_scope: str = "static",
    aliases: tuple[str, ...] = (),
) -> dict[str, Any]:
    next_stage = STAGES[STAGES.index(stage) + 1] if stage != STAGES[-1] else None
    result = StageResult.completed(stage, payload, claim_scope=claim_scope, next_stage=next_stage)
    path = write_stage_artifact(output_root, result)
    for alias in aliases:
        _write_alias(output_root, path, alias)
    completed.append(stage)
    write_checkpoint(output_root, next_stage=next_stage, completed_stages=completed)
    return payload


def _summary(
    output_root: Path,
    *,
    status: str,
    context: RunContext,
    completed: list[str],
    error: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    claim_scope = "runtime" if context.mode == "live" else "planned"
    payload = {
        "schema_version": "chaosatlas-run-summary-v1",
        "status": status,
        "run_id": context.run_id,
        "input_snapshot_sha256": context.input_snapshot_sha256,
        "completed_stages": list(completed),
        "runtime_claims": [],
        "claim_scope": claim_scope,
        "error": error,
    }
    payload.update(extra)
    _write_text(
        output_root / "summary.md",
        "# ChaosAtlas Offline Run\n\n"
        f"- status: `{status}`\n"
        f"- run_id: `{context.run_id}`\n"
        f"- completed_stages: `{', '.join(completed)}`\n"
        f"- claim_scope: `{claim_scope}`; runtime weakness or defense claims require valid attestation and RCA evidence\n"
        + (f"- error: `{error}`\n" if error else ""),
    )
    (output_root / "summary.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def _finalize_phase6(
    output_root: Path,
    *,
    status: str,
    execution_contract: dict[str, Any],
    completed: list[str],
    cleanup: dict[str, Any] | None = None,
    knowledge_base_updated: bool = False,
) -> dict[str, Any]:
    return write_phase6_audit(
        output_root,
        status=status,
        execution_contract=execution_contract,
        completed_stages=completed,
        knowledge_base_updated=knowledge_base_updated,
        cleanup=cleanup or {"status": "not_run", "errors": []},
    )


def _load_or_create_context(profile_path: Path, output_root: Path, mode: str, seed: int, resume: bool) -> tuple[RunContext, bool]:
    if mode not in {"dry-run", "live"}:
        raise ValueError("mode must be dry-run or live")
    if resume:
        if mode == "live":
            raise ValueError("live runs are append-only; start a new output directory instead of resuming")
        if not output_root.is_dir():
            raise FileNotFoundError(f"cannot resume missing output directory: {output_root}")
        manifest_path = output_root / "run_manifest.json"
        if not manifest_path.is_file():
            raise ValueError("cannot resume without run_manifest.json")
        manifest = _read_json(manifest_path)
        context = RunContext.create(profile_path=profile_path, mode=mode, seed=seed, output_root=output_root)
        if manifest.get("input_snapshot_sha256") != context.input_snapshot_sha256:
            raise ValueError("input snapshot changed; refusing resume")
        return context, True
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"refusing non-empty output: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    return RunContext.create(profile_path=profile_path, mode=mode, seed=seed, output_root=output_root), False


def _validate_resume_artifacts(output_root: Path, context: RunContext) -> list[str]:
    checkpoint = load_checkpoint(output_root)
    completed = list(checkpoint.get("completed_stages") or [])
    unknown = [stage for stage in completed if stage not in STAGES]
    if unknown:
        raise ValueError(f"checkpoint contains unknown stages: {', '.join(unknown)}")
    expected_prefix = list(STAGES[: len(completed)])
    if completed != expected_prefix:
        raise ValueError("checkpoint completed stages are not a valid stage prefix")
    manifest = _read_json(output_root / "run_manifest.json")
    if (
        manifest.get("run_id") != context.run_id
        or manifest.get("input_snapshot_sha256") != context.input_snapshot_sha256
    ):
        raise ValueError("run context input hash mismatch")
    for stage_name in completed:
        artifact = _read_json(output_root / f"{stage_name}.json")
        if artifact.get("stage") != stage_name:
            raise ValueError(f"artifact stage mismatch: {stage_name}")
        if artifact.get("output_sha256") != _payload_sha256(artifact.get("payload", {})):
            raise ValueError(f"artifact hash mismatch: {stage_name}")
    return completed


def _runtime_oracle(
    profile: dict[str, Any],
    *,
    oracle_registry: OracleRegistry = DEFAULT_ORACLE_REGISTRY,
) -> dict[str, Any]:
    oracle = next((item for item in profile.get("business_oracles") or [] if isinstance(item, dict)), {})
    kind = str(oracle.get("kind") or "http").strip().lower()
    if not oracle_registry.supports(kind):
        raise ValueError(f"live business oracle does not support {kind or 'unknown'}")
    service = str(oracle.get("service") or "").strip()
    remote_port = oracle.get("remote_port")
    if not service:
        raise ValueError("live business oracle requires service")
    if isinstance(remote_port, bool) or not isinstance(remote_port, int) or not 1 <= remote_port <= 65535:
        raise ValueError("live business oracle requires remote_port in [1, 65535]")
    contract = str(oracle.get("success_contract") or "")
    expected_status = int(oracle.get("expected_status") or 200)
    if kind == "http" and contract.startswith("http_"):
        status_token = contract.removeprefix("http_").split("_", 1)[0]
        try:
            expected_status = int(status_token)
        except ValueError:
            raise ValueError("live business oracle success_contract must start with http_<status>")
    if kind == "grpc":
        client = str(oracle.get("client") or "").strip()
        if not client:
            raise ValueError("grpc business oracle requires client")
        supporting_services = oracle.get("supporting_services") or []
        if not isinstance(supporting_services, list) or not supporting_services:
            raise ValueError("grpc business oracle requires supporting_services")
        for supporting in supporting_services:
            if not isinstance(supporting, dict) or not str(supporting.get("service") or "").strip():
                raise ValueError("grpc supporting service requires service")
            port = supporting.get("remote_port")
            if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
                raise ValueError("grpc supporting service requires remote_port in [1, 65535]")
    result = {
        **oracle,
        "kind": kind,
        "service": service,
        "remote_port": remote_port,
        "entrypoint": str(oracle.get("entrypoint") or "/"),
        "expected_status": expected_status,
        "timeout_s": float(oracle.get("timeout_s") or 5),
        "count": int(oracle.get("count") or 3),
        "baseline_retry_window_s": max(0.0, float(oracle.get("baseline_retry_window_s") or 15)),
        "observation_window_s": max(0.0, float(oracle.get("observation_window_s") or 0)),
        "probe_retry_interval_s": max(0.0, float(oracle.get("probe_retry_interval_s") or 1)),
    }
    if kind in {"http", "dify_chatflow"}:
        request_headers = oracle.get("request_headers")
        if isinstance(request_headers, dict):
            result["request_headers"] = {
                str(key): str(value) for key, value in request_headers.items()
            }
        if oracle.get("expected_body") is not None:
            result["expected_body"] = str(oracle["expected_body"])
        if kind == "dify_chatflow":
            result["api_key_file"] = str(oracle.get("api_key_file") or r"C:\APP\project\Dify_APIkey.txt")
            result["candidate_scope"] = str(oracle.get("candidate_scope") or "business_path")
    if kind == "grpc":
        result["client"] = str(oracle["client"]).strip()
        result["supporting_services"] = [
            {
                "service": str(item["service"]).strip(),
                "remote_port": int(item["remote_port"]),
            }
            for item in oracle["supporting_services"]
        ]
    return result


def _live_scenario(
    *,
    profile: dict[str, Any],
    inventory: dict[str, Any],
    candidate: dict[str, Any],
    scenario_id: str,
    oracle_registry: OracleRegistry = DEFAULT_ORACLE_REGISTRY,
) -> dict[str, Any]:
    target = str(candidate.get("target") or "")
    deployment_fact = next(
        (
            item for item in inventory.get("deployments") or []
            if str(item.get("name") or (item.get("metadata") or {}).get("name") or "") == target
        ),
        None,
    )
    if not isinstance(deployment_fact, dict):
        raise ValueError(f"live candidate target deployment not found: {target}")
    oracle = _runtime_oracle(profile, oracle_registry=oracle_registry)
    deployment_spec = deployment_fact.get("spec") if isinstance(deployment_fact.get("spec"), dict) else {}
    selector_source = deployment_fact.get("selector") or (deployment_spec.get("selector") or {}).get("matchLabels") or {}
    selector = {str(key): str(value) for key, value in selector_source.items()}
    if not selector:
        raise ValueError("live candidate deployment selector is required")
    namespace = str(inventory.get("namespace") or "")
    deployment = {
        "metadata": {"name": target},
        "spec": {
            "replicas": int(deployment_fact.get("desired_replicas") or deployment_spec.get("replicas") or 0),
            "selector": {"matchLabels": selector},
            "template": {"metadata": {"labels": selector}, "spec": {"containers": [{"name": target}]}},
        },
    }
    extension_facts = candidate.get("extension_facts") or deployment_fact.get("extensions")
    if isinstance(extension_facts, dict):
        deployment["extensions"] = deepcopy(extension_facts)
    service_name = str(candidate.get("service_target") or oracle["service"])
    service_port = int(oracle["remote_port"])
    for item in inventory.get("services") or []:
        metadata = item.get("metadata") if isinstance(item, dict) else {}
        if str(metadata.get("name") or "") != service_name:
            continue
        spec = item.get("spec") if isinstance(item.get("spec"), dict) else {}
        ports = spec.get("ports") or []
        if ports and isinstance(ports[0], dict) and isinstance(ports[0].get("port"), int):
            service_port = int(ports[0]["port"])
        break
    target_port = service_port
    for item in inventory.get("services") or []:
        metadata = item.get("metadata") if isinstance(item, dict) else {}
        if str(metadata.get("name") or "") != service_name:
            continue
        spec = item.get("spec") if isinstance(item.get("spec"), dict) else {}
        ports = spec.get("ports") or []
        if ports and isinstance(ports[0], dict) and isinstance(ports[0].get("targetPort"), int):
            target_port = int(ports[0]["targetPort"])
        break
    service = {
        "metadata": {"name": service_name},
        "spec": {"ports": [{"port": service_port, "targetPort": service_port}], "selector": selector},
    }
    commit = str(inventory.get("project_commit") or "")
    if len(commit) != 40:
        import hashlib
        commit = hashlib.sha256(commit.encode("utf-8")).hexdigest()[:40]
    node = build_deployment_node(
        project_id=str(inventory.get("project_id") or ""), project_commit=commit,
        namespace=namespace, deployment=deployment, service=service,
        source_refs=["profile/runtime"], manifest_sha256="0" * 64,
    )
    family = str(candidate.get("fault_family") or "pod_kill")
    candidate_parameters = candidate.get("parameters")
    parameters = dict(candidate_parameters) if isinstance(candidate_parameters, dict) else {}
    if family in {"pod_kill", "backend_pod_kill"}:
        parameters = {"mode": "one"}
        action = "pod-kill"
    elif family == "container_kill":
        containers = ((deployment_spec.get("template") or {}).get("spec") or {}).get("containers") or []
        container_name = str((containers[0] or {}).get("name") or target) if containers else target
        parameters = {"container": str(parameters.get("container") or container_name)}
        action = "container-kill"
    elif family == "stress_cpu":
        parameters = {"workers": int(parameters.get("workers") or 1), "load_percent": int(parameters.get("load_percent") or 80)}
        action = "stress-cpu"
    elif family == "stress_memory":
        parameters = {"size_mb": int(parameters.get("size_mb") or 64)}
        action = "stress-memory"
    elif family == "network_loss":
        parameters = {"loss_percent": int(parameters.get("loss_percent") or 100)}
        action = "network-loss"
    elif family == "network_delay":
        parameters = {
            "latency_ms": int(parameters.get("latency_ms") or 500),
            "jitter_ms": int(parameters.get("jitter_ms") or 0),
            "correlation": int(parameters.get("correlation") or 100),
        }
        action = "network-delay"
    elif family == "network_bandwidth":
        parameters = {
            "rate": str(parameters["rate"]) if "rate" in parameters else "1mbps",
            "limit": int(parameters["limit"]) if "limit" in parameters else 1000,
            "buffer": int(parameters["buffer"]) if "buffer" in parameters else 1000,
        }
        action = "bandwidth"
    elif family in {"network_duplicate", "network_corrupt"}:
        value_key = "duplicate_percent" if family == "network_duplicate" else "corrupt_percent"
        parameters = {
            value_key: int(parameters[value_key]) if value_key in parameters else 20,
            "correlation": int(parameters["correlation"]) if "correlation" in parameters else 100,
        }
        action = "duplicate" if family == "network_duplicate" else "corrupt"
    elif family == "network_partition":
        parameters = {}
        action = "network-partition"
    elif family in {"dns_failure", "dns_delay"}:
        configured = (profile.get("fault_defaults") or {}).get(family)
        configured = configured if isinstance(configured, dict) else {}
        parameters = {**configured, **parameters}
        parameters["hostname"] = str(parameters.get("hostname") or service_name or target)
        if family == "dns_failure":
            action = "dns-error"
        else:
            parameters["latency_ms"] = int(parameters.get("latency_ms") or 500)
            action = "dns-delay"
    elif family in {"http_delay", "http_abort", "http_status_error", "http_response_corrupt", "dependency_error", "connection_reset", "http_rate_limit", "business_dependency_unreachable"}:
        configured = (profile.get("fault_defaults") or {}).get(family)
        configured = configured if isinstance(configured, dict) else {}
        parameters = {**configured, **parameters}
        if "port" not in parameters:
            parameters["port"] = target_port
        if "path" not in parameters:
            parameters["path"] = str(oracle.get("entrypoint") or "/")
        if family == "http_delay":
            if "latency_ms" not in parameters:
                parameters["latency_ms"] = 500
            action = "http-delay"
        elif family == "http_abort":
            action = "http-abort"
        elif family == "http_status_error":
            if "status_code" not in parameters:
                parameters["status_code"] = 503
            action = "http-status-error"
        elif family == "http_response_corrupt":
            if "body" not in parameters:
                parameters["body"] = "chaosatlas-response-corrupted"
            action = "http-response-corrupt"
        elif family == "dependency_error":
            if "status_code" not in parameters:
                parameters["status_code"] = 503
            action = "dependency-error"
        elif family == "http_rate_limit":
            parameters.setdefault("requests_per_window", 2)
            parameters.setdefault("window_s", 10)
            parameters.setdefault("status_code", 429)
            action = "http-rate-limit"
        elif family == "business_dependency_unreachable":
            action = "business-dependency-unreachable"
        else:
            action = "connection-reset"
    elif family == "replica_reduction":
        original_replicas = int(deployment.get("spec", {}).get("replicas") or 1)
        parameters = {"replicas": int(parameters.get("replicas", max(0, original_replicas - 1)))}
        action = "replica-reduction"
    elif family == "config_reload":
        configured = (profile.get("fault_defaults") or {}).get(family)
        configured = configured if isinstance(configured, dict) else {}
        parameters = {**configured, **parameters}
        parameters = {"reload_token": str(parameters.get("reload_token") or f"chaosatlas-{scenario_id}")}
        action = "config-reload"
    elif family == "config_drift":
        configured = (profile.get("fault_defaults") or {}).get(family)
        configured = configured if isinstance(configured, dict) else {}
        parameters = {**configured, **parameters}
        parameters = {"value": str(parameters.get("value") or "chaosatlas-config-drift")}
        action = "config-drift"
    elif family == "env_misconfiguration":
        configured = (profile.get("fault_defaults") or {}).get(family)
        configured = configured if isinstance(configured, dict) else {}
        parameters = {**configured, **parameters}
        parameters = {
            "name": str(parameters.get("name") or "CHAOSATLAS_MODE"),
            "value": str(parameters.get("value") or "chaosatlas-test-misconfigured"),
        }
        action = "env-misconfiguration"
    elif family == "secret_rotation":
        configured = (profile.get("fault_defaults") or {}).get(family)
        configured = configured if isinstance(configured, dict) else {}
        parameters = {**configured, **parameters}
        parameters = {
            "secret_name": str(parameters.get("secret_name") or f"{target}-secret"),
            "key": str(parameters.get("key") or "token"),
            "value": str(parameters.get("value") or "chaosatlas-test-placeholder"),
        }
        action = "secret-rotation"
    elif family == "rollout_pause":
        parameters = {"paused": True}
        action = "rollout-pause"
    elif family == "image_pull_failure":
        configured = (profile.get("fault_defaults") or {}).get(family)
        configured = configured if isinstance(configured, dict) else {}
        parameters = {**configured, **parameters}
        parameters = {"image": str(parameters.get("image") or "chaosatlas.invalid/not-found:test")}
        action = "image-pull-failure"
    elif family == "pod_unschedulable":
        configured = (profile.get("fault_defaults") or {}).get(family)
        configured = configured if isinstance(configured, dict) else {}
        parameters = {**configured, **parameters}
        parameters = {
            "node_selector_key": str(parameters.get("node_selector_key") or "chaosatlas.invalid/never"),
            "node_selector_value": str(parameters.get("node_selector_value") or "true"),
        }
        action = "pod-unschedulable"
    elif family == "api_server_delay":
        configured = (profile.get("fault_defaults") or {}).get(family)
        configured = configured if isinstance(configured, dict) else {}
        parameters = {**configured, **parameters}
        parameters = {"latency_ms": int(parameters.get("latency_ms") or 100)}
        action = "api-server-delay"
    elif family == "disk_pressure":
        configured = (profile.get("fault_defaults") or {}).get(family)
        configured = configured if isinstance(configured, dict) else {}
        parameters = {**configured, **parameters}
        parameters = {
            "path": str(parameters.get("path") or "/tmp/chaosatlas-pressure"),
            "size_mb": int(parameters.get("size_mb") or 16),
        }
        action = "disk-pressure"
    elif family == "file_descriptor_exhaustion":
        configured = (profile.get("fault_defaults") or {}).get(family)
        configured = configured if isinstance(configured, dict) else {}
        parameters = {**configured, **parameters}
        parameters = {"count": int(parameters.get("count") or 32)}
        action = "file-descriptor-exhaustion"
    elif family == "process_exhaustion":
        configured = (profile.get("fault_defaults") or {}).get(family)
        configured = configured if isinstance(configured, dict) else {}
        parameters = {**configured, **parameters}
        parameters = {"count": int(parameters.get("count") or 8)}
        action = "process-exhaustion"
    elif family.startswith("extension."):
        configured = (profile.get("extension_fault_defaults") or {}).get(family)
        configured = configured if isinstance(configured, dict) else {}
        parameters = {**configured, **parameters}
        action = family
    else:
        raise ValueError(f"unsupported live fault family: {family}")
    scenario = build_scenario_node(
        scenario_id=scenario_id,
        deployment_nodes=[node],
        phases=[{
            "phase_id": "live-verify",
            "mode": "ordered",
            "faults": [{"kind": family, "action": action, "selector": selector, "parameters": parameters, "target_node_id": node["node_id"]}],
            "duration_s": 30,
            "target_node_ids": [node["node_id"]],
            "inject_confirmation": "status.injectedCount >= 1",
            "cleanup_owner": "chaosatlas",
        }],
        oracle={"business": oracle},
        recovery={"deadline_s": int((profile.get("recovery") or {}).get("deadline_s") or 180), "stable_samples": MIN_STABLE_REPRODUCTIONS},
        cleanup={"required": True, "owner": str((profile.get("cleanup") or {}).get("owner") or "chaosatlas")},
    )
    return scenario


def _live_cleanup_report(result: dict[str, Any]) -> dict[str, Any]:
    faults = [fault for phase in result.get("phases") or [] for fault in phase.get("faults") or []]
    verified = sum(1 for fault in faults if fault.get("cleanup_confirmed") is True)
    fault_reports = []
    errors = []
    for fault in faults:
        cleanup = fault.get("cleanup") if isinstance(fault.get("cleanup"), dict) else {}
        mesh_cleanup = cleanup.get("chaos_mesh") if isinstance(cleanup.get("chaos_mesh"), dict) else None
        if mesh_cleanup is not None:
            errors.extend(str(error) for error in mesh_cleanup.get("errors") or [])
            fault_reports.append({
                "action_id": fault.get("action_id"),
                "confirmed": fault.get("cleanup_confirmed") is True,
                "chaos_mesh": mesh_cleanup,
            })
    return {
        "schema_version": "chaosatlas-live-cleanup-v1",
        "mode": "live",
        "status": "verified" if faults and verified == len(faults) else "blocked",
        "action_count": len(faults),
        "verified_action_count": verified,
        "faults": fault_reports,
        "residual_count": sum(int((report.get("chaos_mesh") or {}).get("residual_count", 0) or 0) for report in fault_reports),
        "errors": errors or ([] if faults and verified == len(faults) else ["cleanup attestation missing"]),
    }


def _live_defense_evidence(fault: dict[str, Any], *, observation_window_s: float | None = None) -> dict[str, Any] | None:
    """Derive only a deployment-boundary redundancy claim from complete evidence."""
    attestation = fault.get("attestation") if isinstance(fault.get("attestation"), dict) else {}
    observation = fault.get("observation") if isinstance(fault.get("observation"), dict) else {}
    recovery = fault.get("recovery") if isinstance(fault.get("recovery"), dict) else {}
    cleanup = fault.get("cleanup") if isinstance(fault.get("cleanup"), dict) else {}
    state = recovery.get("state") if isinstance(recovery.get("state"), dict) else {}
    pre_kill_uids = state.get("pre_kill_uids") or []
    ready_uids = state.get("ready_uids") or state.get("new_ready_uids") or []
    lifecycle_complete = all(attestation.get(field) is True for field in ("baseline", "injection", "observation", "recovery", "cleanup"))
    window_complete = isinstance(observation_window_s, (int, float)) and observation_window_s > 0 and bool(observation.get("samples"))
    if not (
        fault.get("kind") == "pod_kill"
        and lifecycle_complete
        and observation.get("status") == "pass"
        and recovery.get("confirmed") is True
        and cleanup.get("confirmed") is True
        and attestation.get("independent_oracle") is True
        and len(pre_kill_uids) >= 2
        and len(ready_uids) >= 2
        and window_complete
    ):
        return None
    return {
        "claim_type": "redundancy",
        "mechanism_evidence": True,
        "independent_oracle": True,
        "observation_window": True,
        "observation_window_s": float(observation_window_s),
        "pre_kill_pod_count": len(pre_kill_uids),
        "recovered_ready_pod_count": len(ready_uids),
        "claim_scope": "deployment_boundary",
        "interpretation": "At least one remaining Ready replica preserved the business Oracle while one Pod was killed and the deployment recovered; this is a deployment-boundary redundancy claim, not an application-internal mechanism claim.",
    }


def _classify_live_outcome(execution_status: str, injection_confirmed: bool, outcome_status: str, defense_evidence: dict[str, Any] | None = None) -> str:
    """Map executor state to a bounded runtime classification."""
    if execution_status == "environment_blocked":
        return "environment_blocked"
    if execution_status in {"business_not_reachable", "business_unreachable"}:
        return "business_not_reachable"
    if not injection_confirmed:
        return "injection_not_confirmed"
    if outcome_status in {"rate_limit_observed", "dependency_unreachable_observed"}:
        return outcome_status
    if outcome_status == "business_unreachable":
        return "business_not_reachable"
    if outcome_status == "degraded":
        return "availability_degraded"
    if outcome_status == "observed" and isinstance(defense_evidence, dict) and defense_evidence.get("claim_type") == "redundancy":
        return "availability_defended"
    return "response_observed"


def _observation_summary(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    samples = []
    for item in value.get("samples") or []:
        if isinstance(item, dict):
            samples.append({key: item.get(key) for key in ("sample", "status_code", "latency_ms", "error", "observation_status") if key in item})
    return {"status": value.get("status"), "phase": value.get("phase"), "samples": samples, "reason": value.get("reason")}


def _collect_live_evidence(*, collector: Any, output_root: Path, namespace: str, target: str, selector: dict[str, str] | None = None, evidence_prefix: str, claim_scope: str, fault: dict[str, Any], evidence_plan: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    mutation_name = str(fault.get("action_id") or "").strip() or None
    if evidence_plan is not None:
        records.extend(
            collect_planned_evidence(
                plan=evidence_plan,
                collector=collector,
                output_root=output_root,
                namespace=namespace,
                target=target,
                selector=selector,
                evidence_prefix=evidence_prefix,
                claim_scope=claim_scope,
                mutation_name=mutation_name,
                scope_events_to_mutation=True,
            )
        )
    else:
        requests = [
            ("events", "kubernetes_event", lambda: collector.collect_events(namespace=namespace, claim_scope=claim_scope, evidence_id=f"{evidence_prefix}-events", involved_object_name=mutation_name)),
            ("logs", "runtime_log", lambda: collector.collect_logs(namespace=namespace, workload=f"deployment/{target}", claim_scope=claim_scope, evidence_id=f"{evidence_prefix}-logs")),
        ]
        for suffix, kind, action in requests:
            try:
                record = action()
            except Exception as exc:
                record = collect_unavailable_evidence(
                    root=output_root,
                    source_ref=f"runtime/kubernetes/unavailable/{evidence_prefix}-{suffix}.json",
                    evidence_id=f"{evidence_prefix}-{suffix}",
                    kind=kind,
                    claim_scope=claim_scope,
                    reason=f"collector_failed:{type(exc).__name__}",
                )
            records.append(record)
    observation_path = output_root / "runtime" / "business" / f"{evidence_prefix}.json"
    observation_payload = {
        "baseline": _observation_summary(fault.get("baseline")),
        "observation": _observation_summary(fault.get("observation")),
        "recovery": fault.get("recovery"),
        "cleanup": fault.get("cleanup"),
        "attestation": fault.get("attestation"),
    }
    observation_path.parent.mkdir(parents=True, exist_ok=True)
    observation_path.write_text(json.dumps(observation_payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    records.append(collect_file_evidence(
        root=output_root,
        source_ref=f"runtime/business/{evidence_prefix}.json",
        evidence_id=f"{evidence_prefix}-business",
        kind="business_path_replay",
        claim_scope=claim_scope,
        interpretation="business oracle and lifecycle observation summary for the bounded run",
        satisfies=["business_oracle_window"],
    ))

    # A complete lifecycle can support a service-boundary mechanism claim, but
    # it cannot by itself prove a source-level implementation cause.  Keep this
    # summary deliberately narrow and tied to the immutable run artifacts.
    attestation = fault.get("attestation") if isinstance(fault.get("attestation"), dict) else {}
    observation = fault.get("observation") if isinstance(fault.get("observation"), dict) else {}
    recovery = fault.get("recovery") if isinstance(fault.get("recovery"), dict) else {}
    cleanup = fault.get("cleanup") if isinstance(fault.get("cleanup"), dict) else {}
    lifecycle_complete = all(attestation.get(field) is True for field in ("baseline", "injection", "observation", "recovery", "cleanup"))
    observation_valid = observation.get("status") in {"pass", "degraded"}
    recovery_confirmed = attestation.get("recovery") is True and recovery.get("confirmed") is True
    cleanup_confirmed = attestation.get("cleanup") is True and cleanup.get("confirmed") is True
    if lifecycle_complete and observation_valid and recovery_confirmed and cleanup_confirmed:
        recovery_state = recovery.get("state") if isinstance(recovery.get("state"), dict) else {}
        event_record = next((item for item in records if item.get("kind") == "kubernetes_event"), {})
        # Windows can reject otherwise valid evidence paths once the external
        # run root and candidate identity are combined.  Keep the source ref
        # deterministic but bounded; the full run id remains in the payload.
        mechanism_source_ref = f"runtime/kubernetes/mechanism/{evidence_prefix}-service-boundary.json"
        if len(str(output_root / mechanism_source_ref)) >= 240:
            suffix = hashlib.sha256(evidence_prefix.encode("utf-8")).hexdigest()[:12]
            mechanism_source_ref = f"runtime/kubernetes/mechanism/m-{suffix}.json"
        recovery_mode = str(recovery_state.get("recovery_mode") or "pod_replacement")
        if recovery_mode == "container_restart":
            mechanism_interpretation = (
                "Kubernetes/Chaos Mesh lifecycle evidence connects confirmed injection, "
                "target container restart within the existing Pod, business observation "
                "and recovery at the service boundary; it does not claim a source-level root cause."
            )
        else:
            mechanism_interpretation = (
                "Kubernetes/Chaos Mesh lifecycle evidence connects confirmed injection, "
                "target Pod identity change, business observation and recovery at the service boundary; "
                "it does not claim a source-level root cause."
            )
        mechanism_payload = {
            "schema_version": "chaosatlas-service-boundary-mechanism-v1",
            "claim_scope": claim_scope,
            "namespace": namespace,
            "target": target,
            "target_node_id": fault.get("target_node_id") or claim_scope,
            "fault_kind": fault.get("kind") or "unknown",
            "event_source_ref": event_record.get("source_ref"),
            "injection_confirmed": True,
            "observation_status": observation.get("status"),
            "recovery_confirmed": True,
            "cleanup_confirmed": True,
            "pre_kill_pod_uids": recovery_state.get("pre_kill_uids") or [],
            "recovered_pod_uids": recovery_state.get("ready_uids") or recovery_state.get("new_ready_uids") or [],
            "recovery_mode": recovery_mode,
            "pre_restart_counts": recovery_state.get("pre_restart_counts") or {},
            "restart_counts": recovery_state.get("restart_counts") or {},
            "restarted_pods": recovery_state.get("restarted_pods") or [],
            "interpretation": mechanism_interpretation,
        }
        mechanism_path = output_root / mechanism_source_ref
        mechanism_path.parent.mkdir(parents=True, exist_ok=True)
        mechanism_path.write_text(json.dumps(mechanism_payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        mechanism_satisfies = (
            ["mechanism_evidence"]
            if observation.get("status") == "degraded"
            else ["defense_mechanism_evidence"]
        )
        records.append(collect_file_evidence(
            root=output_root,
            source_ref=mechanism_source_ref,
            evidence_id=f"{evidence_prefix}-service-boundary-mechanism",
            kind="recovery",
            claim_scope=claim_scope,
            interpretation=mechanism_payload["interpretation"],
            satisfies=mechanism_satisfies,
        ))
    return records


def _live_lifecycle_evidence(*, output_root: Path, evidence_prefix: str, claim_scope: str, fault: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn executor lifecycle attestations into narrow RCA evidence claims."""
    attestation = fault.get("attestation") if isinstance(fault.get("attestation"), dict) else {}
    checks = (
        ("baseline", "baseline_oracle", "business_path_replay", "baseline oracle completed"),
        ("injection", "injection_confirmation", "kubernetes_event", "fault injection was confirmed"),
        ("observation", "observation", "business_path_replay", "business observation completed"),
        ("recovery", "recovery", "recovery", "target recovered after fault removal"),
        ("cleanup", "cleanup", "recovery", "fault resource cleanup was confirmed"),
    )
    source_ref = f"runtime/business/{evidence_prefix}.json"
    records: list[dict[str, Any]] = []
    for field, satisfies, kind, interpretation in checks:
        value = attestation.get(field)
        if value is None:
            section = fault.get(field)
            value = section.get("confirmed") if isinstance(section, dict) else None
            if field == "baseline" and isinstance(section, dict):
                value = section.get("status") == "pass"
            if field == "observation" and isinstance(section, dict):
                value = section.get("status") in {"pass", "degraded"}
        if value is True:
            evidence = make_evidence(
                evidence_id=f"{evidence_prefix}-{field}",
                kind=kind,
                polarity="supports",
                claim_scope=claim_scope,
                source_ref=source_ref,
                interpretation=interpretation,
            )
            evidence["satisfies"] = [satisfies]
            records.append(evidence)
    for index, item in enumerate(fault.get("mechanism_evidence") or []):
        if not isinstance(item, dict):
            continue
        # Executors may report a planned mechanism reference without being
        # able to materialize it (for example, a control-plane mutator can
        # return lifecycle evidence but no workload log).  Missing optional
        # mechanism evidence must not abort an otherwise valid run; it is
        # retained as unavailable evidence by the caller's evidence plan.
        source_ref = str(item.get("source_ref") or "")
        if not source_ref or not (output_root / source_ref.replace("\\", "/")).is_file():
            continue
        try:
            evidence = collect_file_evidence(
                root=output_root,
                evidence_id=str(item.get("evidence_id") or f"{evidence_prefix}-mechanism-{index + 1}"),
                kind=str(item.get("kind") or "runtime_log"),
                claim_scope=claim_scope,
                source_ref=source_ref,
                interpretation=str(item.get("interpretation") or "mechanism evidence captured by the live executor"),
                satisfies=["mechanism_evidence"],
            )
        except (TypeError, ValueError):
            continue
        if evidence.get("polarity") == "supports":
            evidence["satisfies"] = ["mechanism_evidence"]
        records.append(evidence)
    # Native HTTP canaries expose a deterministic boundary contract rather
    # than a Kubernetes object event. Persist that contract as mechanism
    # evidence so RCA can distinguish an injected 429/503 from a broken
    # baseline and retain the observed threshold/status semantics.
    contract = fault.get("observation_contract")
    if isinstance(contract, dict) and contract.get("kind") in {
        "http_rate_limit",
        "business_dependency_unreachable",
    }:
        source_ref = f"runtime/business/{evidence_prefix}-http-contract.json"
        payload = {
            "schema_version": "chaosatlas-http-boundary-observation-v1",
            "claim_scope": claim_scope,
            "fault_family": contract.get("kind"),
            "observation_contract": contract,
            "samples": [
                {
                    key: item.get(key)
                    for key in ("sample", "status_code", "latency_ms", "error")
                    if key in item
                }
                for item in ((fault.get("observation") or {}).get("samples") or [])
                if isinstance(item, dict)
            ],
        }
        path = output_root / source_ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        records.append(
            collect_file_evidence(
                root=output_root,
                source_ref=source_ref,
                evidence_id=f"{evidence_prefix}-http-boundary-mechanism",
                kind="runtime_log",
                claim_scope=claim_scope,
                interpretation=(
                    "The workload boundary reported the fault-specific HTTP contract "
                    "after confirmed injection; this is service-boundary mechanism evidence, "
                    "not a source-level root-cause claim."
                ),
                satisfies=["mechanism_evidence"],
            )
        )
    return records


def _live_rca_projection(
    *,
    profile: dict[str, Any],
    inventory: dict[str, Any],
    candidate: dict[str, Any],
    fault: dict[str, Any],
    evidence_records: list[dict[str, Any]],
    run_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Project one bounded live action through the shared RCA state machine."""
    target = str(candidate.get("target") or "target")
    claim_scope = f"deployment:{target}"
    hypothesis = {
        "hypothesis_id": str(candidate.get("candidate_id") or run_id),
        "target": target,
        "target_kind": "deployment",
        "fault_family": str(candidate.get("fault_family") or "pod_kill"),
        "hypothesis": f"{candidate.get('fault_family') or 'fault'} may affect {target} availability or business behavior",
        "expected_invariant": "business oracle success",
        "expected_steady_state": "deployment returns to its baseline state",
        "validation_plan": "compare baseline, injection, business observation, recovery and cleanup",
        "recovery_expectation": "target recovers after fault removal",
        "parameters": candidate.get("parameters") or {},
    }
    oracle = _runtime_oracle(profile)
    case = build_case_from_hypothesis(
        hypothesis,
        project_id=str(inventory.get("project_id") or "unknown"),
        project_commit=str(inventory.get("project_commit") or "runtime-inventory"),
        round_id=run_id,
        business_oracle={
            "workflow": (
                f"gRPC {oracle['entrypoint']} on {oracle['service']}"
                if oracle.get("kind") == "grpc"
                else f"HTTP {oracle['entrypoint']} on {oracle['service']}"
            ),
            "success": (
                str((profile.get("business_oracles") or [{}])[0].get("success_contract") or "grpc_success")
                if oracle.get("kind") == "grpc"
                else f"http_{oracle['expected_status']}"
            ),
        },
        namespace=str(inventory.get("namespace") or ""),
        source_ref=f"runtime/hypotheses/{run_id}.json",
    )
    case["hypotheses"][0]["scope"]["edge"] = claim_scope
    action_result = {
        "status": str(fault.get("status") or "environment_blocked"),
        "outcome_status": str(fault.get("outcome_status") or ""),
        "action_id": str(candidate.get("candidate_id") or run_id),
        "action_ref": f"runtime/actions/{run_id}.json",
        "target_scope": claim_scope,
        "discriminating_action": any("mechanism_evidence" in (item.get("satisfies") or []) for item in evidence_records),
        "valid_reproductions": 1 if fault.get("outcome_status") in {"observed", "rate_limit_observed", "dependency_unreachable_observed"} else 0,
        "valid_counterfactuals": 0,
        "lifecycle_complete": bool((fault.get("attestation") or {}).get("valid")),
        "direct_evidence": False,
        "applicability_complete": True,
        "regression_complete": False,
        "attestation": fault.get("attestation"),
        "evidence": evidence_records,
    }
    ingested = ingest_action_result(case=case, action_result=action_result)
    updated = ingested["case"]
    if updated.get("knowledge_status") != "none":
        draft = project_knowledge_draft(updated, updated.get("hypotheses", []), updated.get("next_actions", []))
        draft["promotion_allowed"] = bool(ingested.get("promotion", {}).get("allowed"))
    else:
        draft = {
            "schema_version": "chaosatlas-rca-knowledge-draft-v1",
            "id": "KB-RCA-" + str(updated.get("weakness_id", "unknown")).removeprefix("WS-"),
            "status": "none",
            "knowledge_status": "none",
            "rca_status": updated.get("rca_status"),
            "weakness_status": updated.get("weakness_status"),
            "evidence_refs": [],
            "promotion_allowed": False,
            "reason": "non_evident_runtime_outcome",
        }
    return updated, ingested, draft


def run_closed_loop(
    *,
    profile_path: Path,
    output_root: Path,
    mode: str = "dry-run",
    seed: int = 1001,
    resume: bool = False,
    knowledge_root: Path | None = None,
    live_executor: Callable[..., dict[str, Any]] | None = None,
    live_adapter: Any | None = None,
    live_evidence_collector: Any | None = None,
    live_preflight: Any | None = None,
    approve_live: bool = False,
    candidate_id: str | None = None,
    defense_history_root: Path | None = None,
    knowledge_write_root: Path | None = None,
    advisory_provider: Callable[[dict[str, Any]], Any] | None = None,
    policy_hypothesis: dict[str, Any] | None = None,
    registry_shadow: bool = False,
    kube_context: str | None = None,
    oracle_registry: OracleRegistry = DEFAULT_ORACLE_REGISTRY,
) -> dict[str, Any]:
    profile_path = Path(profile_path)
    output_root = Path(output_root)
    try:
        context, resumed = _load_or_create_context(profile_path, output_root, mode, seed, resume)
    except (FileNotFoundError, OSError, ValueError) as exc:
        output_root.mkdir(parents=True, exist_ok=True)
        context = RunContext.create(
            profile_path=profile_path,
            mode=mode,
            seed=seed,
            output_root=output_root,
        )
        return _summary(
            output_root,
            status="method_invalid",
            context=context,
            completed=[],
            error=str(exc),
        )
    completed: list[str] = []
    if resumed:
        try:
            completed = _validate_resume_artifacts(output_root, context)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
            return _summary(
                output_root,
                status="method_invalid",
                context=context,
                completed=[],
                error=f"invalid resume state: {exc}",
            )
    manifest = {
        "schema_version": "chaosatlas-run-manifest-v1",
        "run_id": context.run_id,
        "profile_path": context.profile_path,
        "mode": context.mode,
        "seed": context.seed,
        "input_snapshot_sha256": context.input_snapshot_sha256,
        "claim_scope": "runtime" if mode == "live" else "planned",
        "kube_context": kube_context,
    }
    (output_root / "run_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        contract_profile = _read_json(profile_path)
    except Exception:
        contract_profile = {}
    execution_contract = build_execution_contract(
        contract_profile,
        mode=mode,
        approve_live=approve_live,
        candidate_id=candidate_id,
        seed=seed,
    )
    _write_text(output_root / "execution_contract.json", json.dumps(execution_contract, indent=2, ensure_ascii=False) + "\n")

    profile: dict[str, Any] | None = None
    inventory: dict[str, Any] | None = None
    detection: dict[str, Any] | None = None
    candidate_space: dict[str, Any] | None = None
    retrieval: dict[str, Any] | None = None
    ranked: dict[str, Any] | None = None
    execution: dict[str, Any] | None = None

    try:
        if "onboard" not in completed:
            profile = _read_json(profile_path)
            if mode == "live":
                checked = validate_project_profile(profile)
                onboard = {
                    "status": "ready_for_runtime" if checked["valid"] else "method_invalid",
                    "profile": checked.get("profile", {}),
                    "errors": checked.get("errors", []),
                    "warnings": checked.get("warnings", []),
                    "claim_scope": "static",
                }
                adapter = None
            else:
                facts_hint = _read_json(profile_path)
                project_id = str(facts_hint.get("project_id") or "")
                facts_path = _facts_path(project_id)
                adapter = OfflineProjectAdapter(facts_path, workspace_root=_REPOSITORY_ROOT)
                onboard = adapter.onboard(profile_path, _REPOSITORY_ROOT)
            _stage(output_root, completed, "onboard", onboard)
            valid_onboard_status = {"ready_for_static_analysis", "ready_for_runtime"}
            if onboard.get("status") not in valid_onboard_status:
                result = _summary(output_root, status="method_invalid", context=context, completed=completed, error="profile onboarding failed")
                _finalize_phase6(output_root, status=result["status"], execution_contract=execution_contract, completed=completed)
                return {**result, "input_snapshot_sha256": context.input_snapshot_sha256, "resumed": resumed}
        else:
            profile = _read_json(profile_path)
            project_id = str(profile.get("project_id") or "")
            adapter = None if mode == "live" else OfflineProjectAdapter(_facts_path(project_id), workspace_root=_REPOSITORY_ROOT)

        if mode == "live":
            assert profile is not None
            try:
                _runtime_oracle(profile, oracle_registry=oracle_registry)
            except ValueError as exc:
                summary = _summary(output_root, status="environment_blocked", context=context, completed=completed, error=str(exc))
                _finalize_phase6(output_root, status=summary["status"], execution_contract=execution_contract, completed=completed)
                return {**summary, "input_snapshot_sha256": context.input_snapshot_sha256, "resumed": resumed}
            runtime_adapter = live_adapter or KubernetesProjectAdapter(profile=profile, kube_context=kube_context)
        else:
            runtime_adapter = None

        if "inventory" not in completed:
            assert profile is not None
            inventory = runtime_adapter.inventory() if runtime_adapter is not None else adapter.inventory(profile)
            _stage(output_root, completed, "inventory", inventory, aliases=(REQUIRED_ALIASES["inventory"],))
        else:
            inventory = _read_json(output_root / "inventory.json").get("payload", _read_json(output_root / "inventory.json"))

        if mode == "live" and (inventory or {}).get("status") != "verified":
            summary = _summary(
                output_root,
                status="environment_blocked",
                context=context,
                completed=completed,
                error="; ".join(str(item) for item in (inventory or {}).get("errors") or ["live inventory unavailable"]),
            )
            _finalize_phase6(output_root, status=summary["status"], execution_contract=execution_contract, completed=completed)
            return {**summary, "input_snapshot_sha256": context.input_snapshot_sha256, "resumed": resumed}

        if "server_deployment_detection" not in completed:
            assert inventory is not None
            detection = runtime_adapter.detect_server_deployment(inventory) if runtime_adapter is not None else adapter.detect_server_deployment(inventory)
            _stage(output_root, completed, "server_deployment_detection", detection, aliases=(REQUIRED_ALIASES["server_deployment_detection"],))
        else:
            detection = _read_json(output_root / "server_deployment_detection.json").get("payload", _read_json(output_root / "server_deployment_detection.json"))

        if mode == "live" and (detection or {}).get("status") != "verified":
            summary = _summary(
                output_root,
                status="environment_blocked",
                context=context,
                completed=completed,
                error="; ".join(str(item) for item in (detection or {}).get("errors") or ["live deployment detection unavailable"]),
            )
            _finalize_phase6(output_root, status=summary["status"], execution_contract=execution_contract, completed=completed)
            return {**summary, "input_snapshot_sha256": context.input_snapshot_sha256, "resumed": resumed}

        if "mapping" not in completed:
            assert detection is not None
            candidate_space = runtime_adapter.map_test_nodes(detection) if runtime_adapter is not None else adapter.map_test_nodes(detection)
            _stage(output_root, completed, "mapping", candidate_space, aliases=(REQUIRED_ALIASES["mapping"],))
        else:
            candidate_space = _read_json(output_root / "candidate_space.json").get("payload", _read_json(output_root / "candidate_space.json"))

        if "retrieval" not in completed:
            assert inventory is not None and candidate_space is not None
            provider = KnowledgeProvider()
            retrieval = provider.retrieve(
                project_id=str(inventory["project_id"]),
                project_commit=str(inventory.get("project_commit") or "") or None,
                candidate_space=candidate_space,
                root=knowledge_root,
            )
            _stage(output_root, completed, "retrieval", retrieval, aliases=(REQUIRED_ALIASES["retrieval"],))
            consumption = build_consumption_report(
                retrieval,
                project_id=str(inventory["project_id"]),
                project_commit=str(inventory.get("project_commit") or "") or None,
            )
            _write_text(output_root / "knowledge_consumption.json", json.dumps(consumption, indent=2, ensure_ascii=False) + "\n")
        else:
            retrieval = _read_json(output_root / "retrieval.json").get("payload", _read_json(output_root / "retrieval.json"))
            if inventory is not None and not (output_root / "knowledge_consumption.json").is_file():
                consumption = build_consumption_report(
                    retrieval,
                    project_id=str(inventory["project_id"]),
                    project_commit=str(inventory.get("project_commit") or "") or None,
                )
                _write_text(output_root / "knowledge_consumption.json", json.dumps(consumption, indent=2, ensure_ascii=False) + "\n")

        # These are advisory side artifacts, deliberately outside STAGES. They
        # preserve the broad project view and all evidence-bounded hypotheses
        # while the existing policy still selects only runtime candidates.
        if not (output_root / "project_portrait.json").is_file():
            assert inventory is not None and detection is not None and candidate_space is not None and retrieval is not None
            portrait = build_project_portrait(
                inventory,
                detection,
                candidate_space,
                cards=retrieval.get("cards", []),
            )
            _write_advisory_artifact(output_root, "project_portrait", portrait)
        else:
            portrait = _read_advisory_artifact(output_root, "project_portrait")

        if not (output_root / "hypothesis_registry.json").is_file():
            assert inventory is not None and detection is not None and candidate_space is not None
            registry = build_hypothesis_registry(
                inventory,
                detection,
                candidate_space,
                cards=(retrieval or {}).get("cards", []),
            )
            _write_advisory_artifact(output_root, "hypothesis_registry", registry)
        else:
            registry = _read_advisory_artifact(output_root, "hypothesis_registry")

        if "hypotheses" not in completed:
            assert inventory is not None and detection is not None and candidate_space is not None and retrieval is not None
            hypothesis_input = build_hypothesis_input(inventory, detection, candidate_space, retrieval.get("cards", []))
            rca_snapshot = {"schema_version": 1, "cards": retrieval.get("cards", [])}
            ranked = rank_candidates(candidate_space, retrieval.get("cards", []), rca_snapshot=rca_snapshot)
            hypotheses = build_hypotheses_with_advisory(
                ranked,
                hypothesis_input,
                provider=advisory_provider,
            )
            if isinstance(policy_hypothesis, dict):
                hypotheses["policy_hypothesis"] = policy_hypothesis
            hypotheses["input"] = hypothesis_input
            _stage(output_root, completed, "hypotheses", hypotheses, claim_scope="advisory", aliases=(REQUIRED_ALIASES["hypotheses"],))
        else:
            hypotheses = _read_json(output_root / "hypotheses.json").get("payload", _read_json(output_root / "hypotheses.json"))
            ranked = {"candidates": [item for item in (candidate_space or {}).get("candidates", [])], "candidate_count": len((candidate_space or {}).get("candidates", []))}

        if registry_shadow:
            assert candidate_space is not None
            budget = int((execution_contract.get("budget") or {}).get("max_candidates") or 1)
            legacy_order = [
                str(item)
                for item in (hypotheses or {}).get("candidate_ids") or (candidate_space.get("candidate_ids") or [])
                if item
            ]
            if not legacy_order:
                legacy_order = [
                    str(item.get("candidate_id"))
                    for item in candidate_space.get("candidates") or []
                    if isinstance(item, dict) and item.get("candidate_id")
                ]
            quality_report = evaluate_registry_quality(
                registry,
                candidate_space,
                execution_budget=budget,
            )
            shadow_report = build_registry_shadow(
                registry,
                candidate_space,
                legacy_order=legacy_order,
                top_k=budget,
                execution_budget=budget,
            )
            _write_advisory_artifact(output_root, "registry_quality_report", quality_report)
            _write_advisory_artifact(output_root, "registry_policy_shadow", shadow_report)

        if (output_root / "evidence_plan.json").is_file():
            evidence_plan = _read_json(output_root / "evidence_plan.json").get("payload", _read_json(output_root / "evidence_plan.json"))
        else:
            first_planned_candidate = ((ranked or {}).get("candidates") or (candidate_space or {}).get("candidates") or [None])[0]
            if candidate_id:
                first_planned_candidate = _find_candidate(
                    (candidate_space or {}).get("candidates", []),
                    candidate_id,
                    project_id=str((inventory or {}).get("project_id") or ""),
                ) or first_planned_candidate
            elif profile is not None:
                try:
                    oracle_service = _runtime_oracle(profile, oracle_registry=oracle_registry)["service"]
                except ValueError:
                    oracle_service = ""
                first_planned_candidate = _find_oracle_candidate(
                    (ranked or {}).get("candidates", []),
                    oracle_service,
                ) or first_planned_candidate
            evidence_plan = build_evidence_plan(
                inventory or {},
                candidate_space or {},
                hypotheses,
                candidate_budget=int((execution_contract.get("budget") or {}).get("max_candidates") or 1),
                preferred_candidate_id=str(first_planned_candidate.get("candidate_id")) if isinstance(first_planned_candidate, dict) else None,
            )
            _write_evidence_plan(output_root, evidence_plan)
        if evidence_plan.get("status") == "blocked":
            blocked_status = "environment_blocked" if mode == "live" else "method_invalid"
            summary = _summary(output_root, status=blocked_status, context=context, completed=completed, error="evidence action plan blocked execution")
            _finalize_phase6(output_root, status=summary["status"], execution_contract=execution_contract, completed=completed)
            return {**summary, "input_snapshot_sha256": context.input_snapshot_sha256, "resumed": resumed}

        if "gate" not in completed:
            assert candidate_space is not None
            gate = {"status": "verified", "accepted_candidate_ids": [item.get("candidate_id") for item in candidate_space.get("candidates", [])], "claim_scope": "static"}
            _stage(output_root, completed, "gate", gate)
        else:
            gate = _read_json(output_root / "gate.json").get("payload", _read_json(output_root / "gate.json"))

        first_candidate = ((ranked or {}).get("candidates") or (candidate_space or {}).get("candidates") or [None])[0]
        if candidate_id:
            first_candidate = _find_candidate(
                (candidate_space or {}).get("candidates", []),
                candidate_id,
                project_id=str((inventory or {}).get("project_id") or ""),
            )
        elif profile is not None:
            try:
                oracle_service = _runtime_oracle(profile, oracle_registry=oracle_registry)["service"]
            except ValueError:
                oracle_service = ""
            first_candidate = _find_oracle_candidate(
                (ranked or {}).get("candidates", []),
                oracle_service,
            ) or first_candidate
        if first_candidate is None:
            raise ValueError("no candidate survived server deployment detection")
        plan = {"candidate_id": first_candidate.get("candidate_id"), "expected_invariant": "business_oracle_success"}
        _write_support_artifact(
            output_root,
            "candidate_selection",
            {
                "candidate_count": int((ranked or {}).get("candidate_count") or len((candidate_space or {}).get("candidates", []))),
                "candidate_ids": [
                    str(item.get("candidate_id"))
                    for item in (ranked or {}).get("candidates", [])
                    if isinstance(item, dict) and item.get("candidate_id")
                ],
                "selected_candidate_ids": [str(first_candidate.get("candidate_id"))],
                "selection_mode": "explicit" if candidate_id else "deterministic_ranked_prefix",
                "knowledge_card_ids": list((ranked or {}).get("knowledge_card_ids") or []),
                "knowledge_view_sha256": (ranked or {}).get("knowledge_view_sha256"),
            },
        )
        _write_support_artifact(
            output_root,
            "stop_decision",
            {
                "stop_reason": "budget_pending",
                "budget": 1,
                "next_candidate_id": str(first_candidate.get("candidate_id")),
                "evaluated_candidate_ids": [],
            },
        )

        if mode == "live":
            assert profile is not None and inventory is not None
            try:
                runtime_oracle = _runtime_oracle(profile, oracle_registry=oracle_registry)
            except ValueError as exc:
                summary = _summary(output_root, status="environment_blocked", context=context, completed=completed, error=str(exc))
                _finalize_phase6(output_root, status=summary["status"], execution_contract=execution_contract, completed=completed)
                return {**summary, "input_snapshot_sha256": context.input_snapshot_sha256, "resumed": resumed}
            oracle_candidate = _find_oracle_candidate(
                (candidate_space or {}).get("candidates", []),
                runtime_oracle["service"],
            )
            if oracle_candidate is None and runtime_oracle.get("candidate_scope") != "business_path":
                summary = _summary(output_root, status="environment_blocked", context=context, completed=completed, error="live business oracle service has no matching candidate")
                _finalize_phase6(output_root, status=summary["status"], execution_contract=execution_contract, completed=completed)
                return {**summary, "input_snapshot_sha256": context.input_snapshot_sha256, "resumed": resumed}
            if candidate_id:
                target_matches_oracle = (
                    first_candidate.get("target") == runtime_oracle["service"]
                    or first_candidate.get("service_target") == runtime_oracle["service"]
                    or runtime_oracle.get("candidate_scope") == "business_path"
                )
                backend_route_match = False
                if first_candidate.get("fault_family") == "backend_pod_kill":
                    target_service = str(first_candidate.get("service_target") or "")
                    ingress_services = {
                        str(edge.get("target"))
                        for edge in (inventory.get("dependencies") or [])
                        if edge.get("relation") == "routes_to"
                    }
                    backend_route_match = bool(target_service and target_service in ingress_services)
                if not target_matches_oracle and not backend_route_match:
                    summary = _summary(output_root, status="environment_blocked", context=context, completed=completed, error="selected live candidate does not match the business oracle service")
                    _finalize_phase6(output_root, status=summary["status"], execution_contract=execution_contract, completed=completed)
                    return {**summary, "input_snapshot_sha256": context.input_snapshot_sha256, "resumed": resumed}
            else:
                first_candidate = oracle_candidate or ((ranked or {}).get("candidates") or [None])[0]
            planned_candidate_ids = {
                str(item) for item in ((evidence_plan.get("selection") or {}).get("candidate_ids") or [])
            }
            if str(first_candidate.get("candidate_id")) not in planned_candidate_ids:
                summary = _summary(output_root, status="environment_blocked", context=context, completed=completed, error="selected live candidate is outside the evidence plan")
                _finalize_phase6(output_root, status=summary["status"], execution_contract=execution_contract, completed=completed)
                return {**summary, "input_snapshot_sha256": context.input_snapshot_sha256, "resumed": resumed}
            preflight_runner = live_preflight or KubernetesPreflight(
                profile=profile, runner=run_kubectl, kube_context=kube_context
            )
            preflight = preflight_runner.run()
            _write_text(output_root / "preflight.json", json.dumps(preflight, indent=2, ensure_ascii=False) + "\n")
            if preflight.get("status") != "ready_for_injection":
                summary = _summary(output_root, status="environment_blocked", context=context, completed=completed, error="live runtime preflight blocked execution")
                _finalize_phase6(output_root, status=summary["status"], execution_contract=execution_contract, completed=completed)
                return {**summary, "input_snapshot_sha256": context.input_snapshot_sha256, "resumed": resumed}
            scenario = _live_scenario(
                profile=profile,
                inventory=inventory,
                candidate=first_candidate,
                scenario_id=context.run_id,
                oracle_registry=oracle_registry,
            )
            compiled = compile_scenario(scenario)
            if compiled.get("status") != "verified":
                raise ValueError("live scenario compilation failed: " + "; ".join(compiled.get("errors", [])))
            if live_executor is None:
                if not approve_live:
                    summary = _summary(output_root, status="environment_blocked", context=context, completed=completed, error="live execution requires explicit approve_live")
                    _finalize_phase6(output_root, status=summary["status"], execution_contract=execution_contract, completed=completed)
                    return {**summary, "input_snapshot_sha256": context.input_snapshot_sha256, "resumed": resumed}
                namespace = str((profile.get("namespace_policy") or {}).get("allowed_namespaces", [""])[0])
                lifecycle_executor = KubernetesLifecycleExecutor(
                    root=output_root, namespace=namespace,
                    allowed_namespaces={str(item) for item in (profile.get("namespace_policy") or {}).get("allowed_namespaces", [])},
                    allow_live=True, oracle=runtime_oracle,
                    kube_context=kube_context,
                )
                business_oracle = oracle_registry.create(
                    runtime_oracle,
                    namespace=namespace,
                    kube_context=kube_context,
                    default_probe=lifecycle_executor._default_probe,
                )
                lifecycle_executor.hooks["probe"] = business_oracle.probe
                # All live candidates use the same WorkflowOracle lifecycle;
                # probe-only Oracles retain no-op fixture methods.
                lifecycle_executor.hooks["prepare_fixture"] = business_oracle.prepare_fixture
                lifecycle_executor.hooks["collect_evidence"] = business_oracle.collect_evidence
                lifecycle_executor.hooks["cleanup_fixture"] = business_oracle.cleanup_fixture
                namespace_policy = profile.get("namespace_policy") or {}
                isolated_api = bool(namespace_policy.get("disposable") or (namespace_policy.get("isolation_required") and namespace.startswith("chaosatlas-run-")))
                api_executor = KubernetesApiFaultExecutor(
                    namespace=namespace,
                    allowed_namespaces={str(item) for item in (profile.get("namespace_policy") or {}).get("allowed_namespaces", [])},
                    allow_live=True,
                    isolated=isolated_api,
                    kube_context=kube_context,
                )
                namespace_policy = profile.get("namespace_policy") or {}
                disposable_cluster = bool(namespace_policy.get("disposable_cluster"))
                control_plane_mutator = None
                if disposable_cluster:
                    cluster_profile = str(namespace_policy.get("cluster_profile") or kube_context or "").strip()
                    control_plane_mutator = MinikubeControlPlaneMutator(
                        profile=cluster_profile,
                        context=str(kube_context or cluster_profile),
                        disposable=True,
                    )
                control_plane_executor = ControlPlaneDelayExecutor(
                    allow_live=True,
                    disposable_cluster=disposable_cluster,
                    mutator=control_plane_mutator,
                )
                native_executor = NativeResourceFaultExecutor(
                    namespace=namespace,
                    allowed_namespaces={str(item) for item in (profile.get("namespace_policy") or {}).get("allowed_namespaces", [])},
                    allow_live=True,
                    isolated=bool((profile.get("namespace_policy") or {}).get("native_resource_isolated")),
                    runner=lambda args, timeout=30: run_kubectl(args, timeout=timeout, kube_context=kube_context),
                )
                native_http_executor = NativeHttpFaultExecutor(
                    namespace=namespace,
                    allowed_namespaces={str(item) for item in (profile.get("namespace_policy") or {}).get("allowed_namespaces", [])},
                    allow_live=True,
                    isolated=bool((profile.get("namespace_policy") or {}).get("native_http_isolated")),
                    runner=lambda args, timeout=30: run_kubectl(args, timeout=timeout, kube_context=kube_context),
                )

                def live_executor(manifest: dict[str, Any], phase: dict[str, Any] | None = None, fault: dict[str, Any] | None = None) -> dict[str, Any]:
                    def probe_for_manifest(probe_phase: str) -> dict[str, Any]:
                        return business_oracle.probe(probe_phase, manifest)

                    if manifest.get("kind") == "ChaosAtlasKubernetesFault":
                        api_executor.probe = probe_for_manifest
                        return api_executor(manifest, phase, fault)
                    if manifest.get("kind") == "ChaosAtlasNativeFault":
                        native_executor.probe = probe_for_manifest
                        return native_executor(manifest, phase, fault)
                    if manifest.get("kind") == "ChaosAtlasNativeHttpFault":
                        native_http_executor.probe = probe_for_manifest
                        return native_http_executor(manifest, phase, fault)
                    if manifest.get("kind") == "ChaosAtlasControlPlaneFault":
                        control_plane_executor.probe = probe_for_manifest
                        return control_plane_executor(manifest, phase=phase, fault=fault)
                    return lifecycle_executor(manifest, phase, fault)
            execution = run_scenario(scenario, compiled=compiled, dry_run=False, executor=live_executor)
            phase_fault = ((execution.get("phases") or [{}])[0].get("faults") or [{}])[0]
            namespace = str((profile.get("namespace_policy") or {}).get("allowed_namespaces", [""])[0])
            evidence_collector = live_evidence_collector or KubernetesEvidenceCollector(
                root=output_root,
                allowed_namespaces={namespace},
                kube_context=kube_context,
            )
            evidence_records = _collect_live_evidence(
                collector=evidence_collector,
                output_root=output_root,
                namespace=namespace,
                target=str(first_candidate.get("target") or "target"),
                selector={str(key): str(value) for key, value in (first_candidate.get("selector") or {}).items()},
                evidence_prefix=context.run_id,
                claim_scope=f"deployment:{first_candidate.get('target')}",
                fault=phase_fault,
                evidence_plan=evidence_plan,
            )
            evidence_records.extend(
                _live_lifecycle_evidence(
                    output_root=output_root,
                    evidence_prefix=context.run_id,
                    claim_scope=f"deployment:{first_candidate.get('target')}",
                    fault=phase_fault,
                )
            )
            evidence_payload = {
                "schema_version": "chaosatlas-evidence-refs-v1",
                "claim_scope": f"deployment:{first_candidate.get('target')}",
                "records": evidence_records,
                "planned_action_ids": [
                    str(item.get("action_id"))
                    for item in (evidence_plan.get("actions") or [])
                    if isinstance(item, dict) and item.get("candidate_id") == first_candidate.get("candidate_id")
                ],
                "evidence_plan_ref": "evidence_plan.json",
                "available_count": sum(1 for item in evidence_records if item.get("polarity") == "supports"),
                "unavailable_count": sum(1 for item in evidence_records if item.get("polarity") == "unavailable"),
                "promotion_allowed": False,
            }
            _write_text(output_root / "evidence_refs.json", json.dumps(evidence_payload, indent=2, ensure_ascii=False) + "\n")
            evidence_refs = [str(item.get("source_ref")) for item in evidence_records if item.get("source_ref")]
            _stage(output_root, completed, "baseline", {"status": "observed", "candidate_id": first_candidate.get("candidate_id"), "evidence": phase_fault.get("baseline"), "claim_scope": "runtime"}, claim_scope="runtime")
            _stage(output_root, completed, "execute", execution, claim_scope="runtime")
            _stage(output_root, completed, "observe", {"observation": phase_fault.get("observation") or {"status": phase_fault.get("outcome_status")}, "evidence_refs": evidence_refs, "claim_scope": "runtime"}, claim_scope="runtime")
            status = str(execution.get("status") or "environment_blocked")
            phase_status = str(phase_fault.get("status") or status)
            if status == "injection_not_confirmed" and phase_status == "business_not_reachable":
                status = "business_not_reachable"
            defense_evidence = _live_defense_evidence(
                phase_fault,
                observation_window_s=runtime_oracle.get("observation_window_s"),
            )
            if defense_evidence is not None:
                phase_fault["defense_evidence"] = defense_evidence
            outcome = str(phase_fault.get("outcome_status") or "")
            if not outcome:
                observed_status = str((phase_fault.get("observation") or {}).get("status") or "")
                if observed_status == "business_unreachable":
                    outcome = "business_not_reachable"
                elif observed_status:
                    outcome = "observed" if observed_status == "pass" else observed_status
                phase_fault["outcome_status"] = outcome
            if outcome == "business_unreachable":
                baseline_status = str((phase_fault.get("baseline") or {}).get("status") or "")
                phase_fault["outcome_status"] = "degraded" if baseline_status == "pass" else "business_not_reachable"
            classification = _classify_live_outcome(
                phase_status,
                bool(phase_fault.get("injection_confirmed")),
                str(phase_fault.get("outcome_status") or ""),
                defense_evidence,
            )
            valid_reproductions = 1 if str(phase_fault.get("outcome_status") or "") in {
                "observed", "rate_limit_observed", "dependency_unreachable_observed"
            } else 0
            _stage(
                output_root,
                completed,
                "classify",
                {
                    "result": classification,
                    "claim_scope": "runtime",
                    "attestation": phase_fault.get("attestation"),
                    "defense_evidence": defense_evidence,
                    "evidence_refs": evidence_refs,
                    "valid_reproductions": valid_reproductions,
                    "promotion_allowed": False,
                },
                claim_scope="runtime",
                aliases=(REQUIRED_ALIASES["classify"],),
            )
            updated_case, ingested, draft = _live_rca_projection(
                profile=profile,
                inventory=inventory,
                candidate=first_candidate,
                fault=phase_fault,
                evidence_records=evidence_records,
                run_id=context.run_id,
            )
            draft["claim_scope"] = "runtime"
            draft["evidence_refs"] = evidence_refs
            promotion_allowed = bool(ingested.get("promotion", {}).get("allowed"))
            evidence_payload["promotion_allowed"] = promotion_allowed
            _write_text(output_root / "evidence_refs.json", json.dumps(evidence_payload, indent=2, ensure_ascii=False) + "\n")
            rca_payload = {
                **updated_case,
                "claim_scope": "runtime",
                "transition": ingested.get("transition"),
                "promotion": ingested.get("promotion"),
                "valid_reproductions": valid_reproductions,
            }
            _stage(output_root, completed, "rca", rca_payload, claim_scope="runtime", aliases=(REQUIRED_ALIASES["rca"],))
            _stage(output_root, completed, "learn", draft, claim_scope="runtime", aliases=(REQUIRED_ALIASES["learn"],))
            if draft.get("knowledge_status") in {"provisional", "local_reusable"}:
                _write_text(
                    _bounded_artifact_path(output_root, "knowledge_drafts", str(draft["id"])),
                    json.dumps(draft, indent=2, ensure_ascii=True) + "\n",
                )
            if draft.get("knowledge_status") in {"provisional", "local_reusable"}:
                regression = compile_regression_intents([draft], snapshot={"inventory": inventory, "case": updated_case})
            else:
                regression = {"schema_version": "chaosatlas-rca-regression-intents-v1", "intents": [], "rejected_cards": [], "reason": "knowledge_not_promotable"}
            regression["claim_scope"] = "runtime"
            if draft.get("knowledge_status") in {"provisional", "local_reusable"}:
                _write_text(
                    output_root / "knowledge_drafts" / "regression_intents.json",
                    json.dumps(regression, indent=2, ensure_ascii=True) + "\n",
                )
            if "promote_defense" not in completed:
                if defense_history_root is None:
                    promotion = {
                        "schema_version": "chaosatlas-defense-promotion-stage-v1",
                        "status": "not_run",
                        "reason": "defense_history_root_not_supplied",
                        "selected_runs": [],
                        "rejected_inputs": [],
                    }
                else:
                    promotion = promote_from_history(
                        history_root=defense_history_root,
                        output_root=output_root,
                        knowledge_write_root=knowledge_write_root,
                    )
                _stage(output_root, completed, "promote_defense", promotion, claim_scope="runtime")
            _stage(output_root, completed, "regression", regression, claim_scope="runtime", aliases=(REQUIRED_ALIASES["regression"],))
            cleanup = _live_cleanup_report(execution)
            _write_text(output_root / "cleanup_report.json", json.dumps(cleanup, indent=2, ensure_ascii=False) + "\n")
            final_status = "live_completed" if status == "executed" else status
        else:
            if "baseline" not in completed:
                _stage(output_root, completed, "baseline", {"status": "planned", "plan": plan, "claim_scope": "planned"}, claim_scope="planned")
            if "execute" not in completed or "observe" not in completed:
                execution = PlanExecutor().run(plan)
            if "execute" not in completed:
                _stage(output_root, completed, "execute", execution, claim_scope="planned")
            if "observe" not in completed:
                _stage(output_root, completed, "observe", execution.get("observation", {}), claim_scope="planned")
            if "classify" not in completed:
                _stage(output_root, completed, "classify", {"result": "not_run", "claim_scope": "planned", "evidence_status": "not_run", "reason": "dry-run plan executor"}, claim_scope="planned", aliases=(REQUIRED_ALIASES["classify"],))
            if "rca" not in completed:
                _stage(output_root, completed, "rca", {"rca_status": "not_run", "claim_scope": "planned", "reason": "runtime evidence unavailable"}, claim_scope="planned", aliases=(REQUIRED_ALIASES["rca"],))
            if "learn" not in completed:
                _stage(output_root, completed, "learn", {"knowledge_status": "none", "claim_scope": "planned", "promotion_allowed": False, "reason": "planned evidence cannot promote knowledge"}, claim_scope="planned", aliases=(REQUIRED_ALIASES["learn"],))
            if "promote_defense" not in completed:
                if defense_history_root is None:
                    promotion = {
                        "schema_version": "chaosatlas-defense-promotion-stage-v1",
                        "status": "not_run",
                        "reason": "defense_history_root_not_supplied",
                        "selected_runs": [],
                        "rejected_inputs": [],
                    }
                else:
                    promotion = promote_from_history(
                        history_root=defense_history_root,
                        output_root=output_root,
                        knowledge_write_root=knowledge_write_root,
                    )
                _stage(output_root, completed, "promote_defense", promotion, claim_scope="planned")
            if "regression" not in completed:
                intents = [{"candidate_id": item.get("candidate_id"), "status": "draft", "executable": False, "reason": "requires runtime validation"} for item in (candidate_space or {}).get("candidates", [])]
                _stage(output_root, completed, "regression", {"intents": intents, "claim_scope": "planned"}, claim_scope="planned", aliases=(REQUIRED_ALIASES["regression"],))
            cleanup = {"status": "not_run", "cleanup_confirmed": False, "evidence_status": "not_run", "claim_scope": "planned"}
            _write_text(output_root / "cleanup_report.json", json.dumps(cleanup, indent=2, ensure_ascii=False) + "\n")
            final_status = "dry_run_ready"
        _write_support_artifact(
            output_root,
            "stop_decision",
            {
                "stop_reason": "single_candidate_complete" if mode == "live" else "planning_complete",
                "budget": 1,
                "next_candidate_id": None,
                "evaluated_candidate_ids": [str(first_candidate.get("candidate_id"))] if mode == "live" else [],
            },
        )
        summary = _summary(
            output_root,
            status=final_status,
            context=context,
            completed=completed,
            candidate_count=int((candidate_space or {}).get("candidate_count") or len((candidate_space or {}).get("candidates", []))),
            selected_candidate_ids=[str(first_candidate.get("candidate_id"))],
            advisory_status=(hypotheses or {}).get("advisory_status", "deterministic_fallback"),
        )
        _finalize_phase6(
            output_root,
            status=summary["status"],
            execution_contract=execution_contract,
            completed=completed,
            cleanup=cleanup,
            knowledge_base_updated=bool((locals().get("promotion") or {}).get("status") == "promoted"),
        )
        return {**summary, "input_snapshot_sha256": context.input_snapshot_sha256, "resumed": resumed}
    except Exception as exc:
        # Preserve a bounded diagnostic outside the user-facing error string;
        # it is essential for repairing evidence-pipeline defects while the
        # run remains method-invalid and must never be treated as runtime proof.
        detail = traceback.format_exc(limit=12)
        _write_text(output_root / "method_error_trace.txt", detail)
        summary = _summary(output_root, status="method_invalid", context=context, completed=completed, error=str(exc))
        if not (output_root / "checkpoint.json").exists():
            write_checkpoint(output_root, next_stage=STAGES[len(completed)] if len(completed) < len(STAGES) else None, completed_stages=completed)
        _finalize_phase6(
            output_root,
            status=summary["status"],
            execution_contract=execution_contract,
            completed=completed,
            cleanup={"status": "not_run", "errors": [str(exc)]},
        )
        return {**summary, "input_snapshot_sha256": context.input_snapshot_sha256, "resumed": resumed}


class RunEngine:
    """Single composition boundary for dry-run, live, and live-batch runs."""

    def __init__(self, dependencies: RunDependencies | None = None) -> None:
        self.dependencies = dependencies or RunDependencies()

    def _run_candidate(self, **kwargs: Any) -> dict[str, Any]:
        """Execute one candidate through the same stage machine in every mode."""
        return run_closed_loop(
            **kwargs,
            live_executor=self.dependencies.live_executor,
            live_adapter=self.dependencies.live_adapter,
            live_evidence_collector=self.dependencies.live_evidence_collector,
            live_preflight=self.dependencies.live_preflight,
            oracle_registry=self.dependencies.oracle_registry,
        )

    def run_candidate(self, request: RunRequest) -> dict[str, Any]:
        """Run one planned candidate for internal reproduction controllers."""
        return self._run_candidate(
            profile_path=request.profile_path,
            output_root=request.output_root,
            mode=request.mode,
            seed=request.seed,
            resume=request.resume,
            knowledge_root=request.knowledge_root,
            approve_live=request.approve_live,
            candidate_id=request.candidate_id,
            defense_history_root=request.defense_history_root,
            knowledge_write_root=request.knowledge_write_root,
            advisory_provider=request.advisory_provider,
            policy_hypothesis=request.policy_hypothesis,
            registry_shadow=request.registry_shadow,
            kube_context=request.kube_context,
        )

    def run(self, request: RunRequest) -> dict[str, Any]:
        if request.mode == "live":
            from chaosatlas.orchestration.batch import run_live_batch

            candidate_ids = [request.candidate_id] if request.candidate_id else None
            max_candidates = request.max_candidates
            if not request.all_candidates and max_candidates is None:
                max_candidates = 1
            return run_live_batch(
                profile_path=request.profile_path,
                output_root=request.output_root,
                candidate_ids=candidate_ids,
                max_candidates=max_candidates,
                approve_live=request.approve_live,
                kube_context=request.kube_context,
                resume=request.resume,
                policy_mode=request.policy_mode,
                policy_state_path=request.policy_state_path,
                policy_context=request.policy_context,
                policy_budget=request.policy_budget,
                knowledge_root=request.knowledge_root,
                knowledge_write_root=request.knowledge_write_root,
                seed=request.seed,
                oracle_registry=self.dependencies.oracle_registry,
                live_executor=self.dependencies.live_executor,
                live_adapter=self.dependencies.live_adapter,
                live_evidence_collector=self.dependencies.live_evidence_collector,
                live_preflight=self.dependencies.live_preflight,
                candidate_runner=self._run_candidate,
                advisory_provider=request.advisory_provider,
                defense_history_root=request.defense_history_root,
                registry_shadow=request.registry_shadow,
            )
        return self.run_candidate(request)


def main(argv: list[str] | None = None) -> int:
    """Compatibility entry point; the packaged CLI owns all argument routing."""
    from chaosatlas.cli import main as cli_main

    return cli_main(argv)

    # Retained below temporarily as unreachable parser source for downstream
    # patch compatibility; all supported invocations return through cli_main.
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--profile", type=Path, required=True)
    run.add_argument("--mode", choices=("dry-run", "live"), default="dry-run")
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--seed", type=int, default=1001)
    run.add_argument("--resume", action="store_true")
    run.add_argument("--knowledge-root", type=Path)
    run.add_argument("--defense-history-root", type=Path)
    run.add_argument("--knowledge-write-root", type=Path)
    run.add_argument("--advisory-provider", choices=("deterministic", "deepseek"), default="deterministic")
    run.add_argument("--api-key-file", type=Path, help="explicit DeepSeek key file; used only with --advisory-provider deepseek")
    run.add_argument("--base-url", default="https://api.deepseek.com/v1", help="OpenAI-compatible advisory endpoint")
    run.add_argument("--model", default="deepseek-v4-flash", help="advisory model identifier")
    run.add_argument("--registry-shadow", action="store_true", help="write read-only registry quality and policy shadow reports")
    run.add_argument("--approve-live", action="store_true", help="approve one namespace-scoped live mutation")
    run.add_argument("--candidate-id", help="candidate to execute in live mode")
    run.add_argument("--all-candidates", action="store_true", help="run the bounded live candidate batch for the Oracle service")
    run.add_argument("--max-candidates", type=int, help="limit the live candidate batch size")
    run.add_argument("--kube-context", help="explicit kubectl context for live detection and execution")
    run.add_argument("--policy-mode", choices=("legacy", "observe", "shadow", "guarded", "default"), default="legacy")
    run.add_argument("--policy-state", type=Path, help="policy state JSON for bounded batch selection")
    run.add_argument("--policy-context", type=Path, help="read-only policy context JSON for bounded batch selection")
    run.add_argument("--policy-budget", type=int, default=20, help="number of policy-selected candidates")
    improve = subparsers.add_parser("improve", help="run a guarded deployment improvement retest")
    improve.add_argument("--profile", type=Path, required=True)
    improve.add_argument("--source-root", type=Path, required=True)
    improve.add_argument("--baseline-root", type=Path, required=True)
    improve.add_argument("--proposal", type=Path, required=True)
    improve.add_argument("--output", type=Path, required=True)
    improve.add_argument("--namespace", required=True)
    improve.add_argument("--allowed-namespace", action="append")
    improve.add_argument("--mode", choices=("dry-run", "live"), default="dry-run")
    improve.add_argument("--seed", type=int, default=1001)
    improve.add_argument("--approve-live", action="store_true")
    improve.add_argument("--prior-improvement-root", type=Path)
    improve.add_argument("--knowledge-write-root", type=Path)
    args = parser.parse_args(argv)
    if args.command == "run":
        advisory_provider = None
        if args.advisory_provider == "deepseek":
            if args.mode == "live" and (args.all_candidates or args.max_candidates is not None):
                print(json.dumps({"status": "blocked_advisory_batch_unsupported", "reason": "DeepSeek advisory is supported by the single-candidate closed loop only"}, ensure_ascii=True))
                return 2
            try:
                from tools.deepseek_advisory import create_deepseek_advisory_provider

                advisory_provider = create_deepseek_advisory_provider(
                    api_key_file=args.api_key_file,
                    base_url=args.base_url,
                    model=args.model,
                )
            except (OSError, ValueError, ImportError) as exc:
                print(json.dumps({"status": "blocked_missing_advisory_provider", "reason": str(exc)}, ensure_ascii=True))
                return 2
        if args.mode == "live" and (args.all_candidates or args.max_candidates is not None):
            from chaosatlas.orchestration.batch import run_live_batch
            policy_context = None
            if args.policy_context:
                try:
                    policy_context = json.loads(args.policy_context.read_text(encoding="utf-8-sig"))
                    if not isinstance(policy_context, dict):
                        raise ValueError("policy context must be a JSON object")
                except (OSError, json.JSONDecodeError, ValueError) as exc:
                    print(json.dumps({"status": "blocked_invalid_policy_context", "reason": str(exc)}, ensure_ascii=True))
                    return 2
            result = run_live_batch(
                profile_path=args.profile,
                output_root=args.output,
                max_candidates=args.max_candidates,
                approve_live=args.approve_live,
                kube_context=args.kube_context,
                resume=args.resume,
                policy_mode=args.policy_mode,
                policy_state_path=args.policy_state,
                policy_context=policy_context,
                policy_budget=args.policy_budget,
                knowledge_root=args.knowledge_root,
                knowledge_write_root=args.knowledge_write_root,
                seed=args.seed,
            )
            print(json.dumps({"status": result["status"], "planned_count": result.get("planned_count"), "output": str(args.output)}, ensure_ascii=True))
            return 0 if result["status"] == "completed" else 2
        if args.policy_mode != "legacy" or args.policy_state or args.policy_context:
            print(json.dumps({"status": "blocked_policy_mode_requires_batch", "reason": "use --all-candidates or --max-candidates for policy selection"}, ensure_ascii=True))
            return 2
        result = run_closed_loop(profile_path=args.profile, output_root=args.output, mode=args.mode, seed=args.seed, resume=args.resume, knowledge_root=args.knowledge_root, approve_live=args.approve_live, candidate_id=args.candidate_id, defense_history_root=args.defense_history_root, knowledge_write_root=args.knowledge_write_root, advisory_provider=advisory_provider, registry_shadow=args.registry_shadow, kube_context=args.kube_context)
        print(json.dumps({"status": result["status"], "run_id": result.get("run_id"), "output": str(args.output)}, ensure_ascii=True))
        return 0 if result["status"] in {"dry_run_ready", "live_completed"} else 2
    if args.command == "improve":
        from tools.run_live_improvement import run_live_improvement

        proposal = json.loads(args.proposal.read_text(encoding="utf-8"))
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
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
