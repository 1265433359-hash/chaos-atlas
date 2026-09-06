"""Run a bounded batch of namespace-scoped live ChaosAtlas candidates."""

from __future__ import annotations

import json
import inspect
import hashlib
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from chaosatlas.orchestration.engine import _find_candidate, _runtime_oracle
from chaosatlas.oracles import DEFAULT_ORACLE_REGISTRY, OracleRegistry
from tools.experiment_policy import new_policy_state
from tools.experiment_policy_feedback import ingest_runtime_result, write_policy_state
from tools.kubernetes_project_adapter import KubernetesProjectAdapter
from tools.policy_controller import PolicyController, normalize_runtime_feedback
from tools.policy_selection_gate import MODES as POLICY_MODES, select_candidates_with_policy
from tools.weakness_promotion_stage import promote_from_history
from tools.hypothesis_registry import build_hypothesis_registry, build_project_portrait
from tools.registry_shadow import evaluate_registry_quality
from tools.registry_policy_signal import build_registry_policy_signal
from tools.reproduction_policy import MIN_STABLE_REPRODUCTIONS


def _safe_name(value: Any) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip("-")
    if not name or name in {".", ".."}:
        raise ValueError("candidate id must produce a safe directory name")
    return name[:160]


def _candidate_output_root(output_root: Path, candidate_id: str) -> Path:
    """Keep enough Windows path budget for atomic stage and evidence files."""
    base = Path(output_root) / "runs"
    path = base / _safe_name(candidate_id)
    if len(str(path)) < 180:
        return path
    digest = hashlib.sha256(str(candidate_id).encode("utf-8")).hexdigest()[:16]
    return base / f"c-{digest}"


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_batch_manifest(
    *,
    profile_sha256: str,
    kube_context: str | None,
    namespace: str,
    candidate_space_sha256: str | None,
    selected_candidate_ids: list[str],
    approve_live: bool,
    policy_mode: str = "legacy",
    policy_budget: int = 20,
    policy_state_sha256: str | None = None,
    policy_context_sha256: str | None = None,
    seed: int = 1001,
) -> dict[str, Any]:
    """Build the immutable input contract for a batch run."""
    return {
        "schema_version": "chaosatlas-live-batch-manifest-v1",
        "immutable": {
            "profile_sha256": str(profile_sha256),
            "kube_context": kube_context,
            "namespace": str(namespace),
            "candidate_space_sha256": candidate_space_sha256,
            "policy_mode": policy_mode,
            "policy_budget": int(policy_budget),
            "policy_state_sha256": policy_state_sha256,
            "policy_context_sha256": policy_context_sha256,
            "seed": int(seed),
        },
        "selected_candidate_ids": [str(item) for item in selected_candidate_ids],
        "approval_contract": {"approve_live": bool(approve_live)},
    }


def append_batch_state(
    path: Path,
    *,
    candidate_id: str,
    state: str,
    reason: str | None = None,
) -> None:
    """Append one deterministic child transition to the batch journal."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {
        "schema_version": "chaosatlas-live-batch-state-v1",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "candidate_id": str(candidate_id),
        "state": str(state),
    }
    if reason:
        record["reason"] = str(reason)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")


def append_policy_record(path: Path, record: dict[str, Any]) -> None:
    """Append one immutable policy decision or feedback record."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")


def validate_batch_resume(
    original_manifest: dict[str, Any],
    current_manifest: dict[str, Any],
    *,
    latest_states: dict[str, str],
) -> None:
    """Reject resume when immutable inputs changed or live mutation occurred."""
    if original_manifest.get("immutable") != current_manifest.get("immutable"):
        raise ValueError("immutable input changed; refusing batch resume")
    if original_manifest.get("selected_candidate_ids") != current_manifest.get("selected_candidate_ids"):
        raise ValueError("immutable input changed; refusing batch resume")
    if original_manifest.get("approval_contract") != current_manifest.get("approval_contract"):
        raise ValueError("immutable input changed; refusing batch resume")
    crossed = {"live_completed"}
    unsafe = sorted(candidate_id for candidate_id, state in latest_states.items() if state in crossed)
    if unsafe:
        raise ValueError("live mutation boundary crossed; refusing batch resume: " + ",".join(unsafe))


def _load_latest_batch_states(path: Path) -> dict[str, str]:
    latest: dict[str, str] = {}
    if not path.is_file():
        return latest
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("candidate_id"):
            latest[str(row["candidate_id"])] = str(row.get("state") or "")
    return latest


def _child_value(item: dict[str, Any], key: str, default: Any = None) -> Any:
    if key in item:
        return item[key]
    output = item.get("output")
    if isinstance(output, dict) and key in output:
        return output[key]
    return default


def enrich_batch_result_from_artifacts(result: dict[str, Any], child_root: Path) -> dict[str, Any]:
    """Project deterministic child-stage outcomes into the batch result row."""
    enriched = dict(result)
    child_root = Path(child_root)
    for filename, key in (
        ("finding_report.json", "classification"),
        ("rca_report.json", "rca_status"),
        ("knowledge_draft.json", "knowledge_status"),
    ):
        path = child_root / filename
        if not path.is_file() or key in enriched:
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        payload = document.get("payload") if isinstance(document, dict) else None
        if not isinstance(payload, dict):
            payload = document if isinstance(document, dict) else {}
        if key in payload:
            enriched[key] = payload[key]
        elif key == "classification" and "result" in payload:
            enriched[key] = payload["result"]
    cleanup_path = child_root / "cleanup_report.json"
    if cleanup_path.is_file() and "cleanup_status" not in enriched:
        try:
            cleanup = json.loads(cleanup_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cleanup = {}
        if isinstance(cleanup, dict) and cleanup.get("status"):
            enriched["cleanup_status"] = cleanup["status"]
    return enriched


def summarize_batch_results(results: list[dict[str, Any]], *, planned_count: int) -> dict[str, Any]:
    """Aggregate child outcomes without upgrading blocked or unstable runs.

    A child directory is one live trial.  Its raw classification and RCA
    status are not enough to establish a stable finding: the same outcome
    must have at least ``MIN_STABLE_REPRODUCTIONS`` valid, independent
    reproductions before it is counted as confirmed.
    """
    completed = 0
    blocked = 0
    failed = 0
    cleanup_failed = 0
    confirmed_findings = 0
    rca_confirmed = 0
    stable_reproduction_verified = 0
    reproduction_gate_incomplete = 0
    knowledge_promoted = 0
    for item in results:
        status = str(_child_value(item, "status", "failed"))
        cleanup_status = str(_child_value(item, "cleanup_status", ""))
        if cleanup_status == "failed":
            cleanup_failed += 1
        if status in {"environment_blocked", "business_not_reachable"}:
            blocked += 1
        elif status in {"method_invalid", "failed"}:
            failed += 1
        if status == "live_completed" and cleanup_status != "failed":
            completed += 1
        valid_reproductions = _child_value(item, "valid_reproductions", 0)
        try:
            valid_reproductions = int(valid_reproductions or 0)
        except (TypeError, ValueError):
            valid_reproductions = 0
        if valid_reproductions >= MIN_STABLE_REPRODUCTIONS:
            stable_reproduction_verified += 1
        output_root = _child_value(item, "output")
        child_root = Path(output_root) if isinstance(output_root, str) and output_root else None
        feedback = normalize_runtime_feedback(item, child_root)
        normalized_classification = str(feedback.get("classification") or "")
        stable_finding = (
            feedback.get("eligible") is True
            and normalized_classification == "confirmed_weakness"
        )
        if stable_finding:
            confirmed_findings += 1
        elif (
            status == "live_completed"
            and cleanup_status != "failed"
            and str(_child_value(item, "classification", "")) in {"availability_degraded", "functional_degraded", "data_integrity_risk", "confirmed_weakness"}
            and valid_reproductions < MIN_STABLE_REPRODUCTIONS
        ):
            reproduction_gate_incomplete += 1
        if stable_finding and str(feedback.get("rca_status") or "") == "confirmed":
            rca_confirmed += 1
        if str(_child_value(item, "knowledge_status", "")) == "promoted":
            knowledge_promoted += 1
    if not results:
        status = "environment_blocked"
    elif completed == len(results) and failed == 0 and blocked == 0 and cleanup_failed == 0:
        status = "completed"
    elif completed:
        status = "partial"
    elif blocked == len(results) and failed == 0:
        status = "environment_blocked"
    else:
        status = "failed"
    return {
        "schema_version": "chaosatlas-live-batch-summary-v1",
        "status": status,
        "planned_count": int(planned_count),
        "executed_count": len(results),
        "completed_count": completed,
        "blocked_count": blocked,
        "failed_count": failed,
        "cleanup_failed_count": cleanup_failed,
        "confirmed_finding_count": confirmed_findings,
        "rca_confirmed_count": rca_confirmed,
        "stable_reproduction_required": MIN_STABLE_REPRODUCTIONS,
        "stable_reproduction_verified_count": stable_reproduction_verified,
        "reproduction_gate_incomplete_count": reproduction_gate_incomplete,
        "knowledge_promoted_count": knowledge_promoted,
        "results": results,
    }


def attach_batch_knowledge_promotion(
    *,
    output_root: Path,
    knowledge_write_root: Path | None,
    summary: dict[str, Any],
) -> dict[str, Any]:
    """Run the existing weakness promotion stage without changing batch status.

    Promotion is deliberately opt-in for formal knowledge writes.  The batch
    still emits an audit artifact when no write root is supplied so callers can
    distinguish "not requested" from "attempted and rejected".
    """

    output_root = Path(output_root)
    audit_path = output_root / "knowledge_promotion.json"
    if knowledge_write_root is None:
        audit = {
            "schema_version": "chaosatlas-batch-knowledge-promotion-v1",
            "status": "not_requested",
            "reason": "knowledge_write_root_not_provided",
            "formal_knowledge_base_updated": False,
        }
    else:
        history_root = output_root / "runs"
        promotion_root = output_root / "knowledge-promotion"
        try:
            result = promote_from_history(
                history_root=history_root,
                output_root=promotion_root,
                knowledge_write_root=Path(knowledge_write_root),
            )
            audit = {
                "schema_version": "chaosatlas-batch-knowledge-promotion-v1",
                "status": str(result.get("status") or "failed"),
                "knowledge_status": result.get("knowledge_status"),
                "card_id": result.get("card_id") or result.get("id"),
                "weakness_id": result.get("weakness_id"),
                "valid_reproductions": result.get("valid_reproductions"),
                "reason": result.get("reason"),
                "selected_runs": result.get("stage", {}).get("selected_runs", []),
                "rejected_inputs": result.get("stage", {}).get("rejected_inputs", []),
                "formal_knowledge_base_updated": str(result.get("status")) == "promoted",
                "promotion_output": str(promotion_root),
            }
        except Exception as exc:  # promotion must not hide the batch result
            audit = {
                "schema_version": "chaosatlas-batch-knowledge-promotion-v1",
                "status": "method_invalid",
                "reason": f"promotion_stage_error:{type(exc).__name__}",
                "error": str(exc),
                "formal_knowledge_base_updated": False,
            }
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary["formal_knowledge_base_updated"] = bool(audit.get("formal_knowledge_base_updated"))
    summary["knowledge_promotion_status"] = audit.get("status")
    summary["knowledge_promotion_artifact"] = "knowledge_promotion.json"
    return audit


def _adapter_inventory(adapter: Any, profile: dict[str, Any]) -> dict[str, Any]:
    """Call both historical ``inventory()`` and profile-aware adapters."""
    method = adapter.inventory
    try:
        parameters = inspect.signature(method).parameters.values()
    except (TypeError, ValueError):
        parameters = ()
    required = [
        parameter
        for parameter in parameters
        if parameter.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        and parameter.default is inspect.Parameter.empty
    ]
    return method(profile) if required else method()


def resolve_requested_candidate_ids(
    candidates: list[dict[str, Any]],
    requested_ids: list[str],
    *,
    project_id: str,
) -> tuple[list[str], list[str]]:
    """Resolve exact runtime IDs and stable CLI aliases for the batch loop."""
    by_id = {
        str(item.get("candidate_id")): item
        for item in candidates
        if isinstance(item, dict) and item.get("candidate_id")
    }
    resolved: list[str] = []
    unknown: list[str] = []
    for requested in requested_ids:
        requested = str(requested)
        candidate = by_id.get(requested) or _find_candidate(
            candidates,
            requested,
            project_id=project_id,
        )
        if candidate is None:
            unknown.append(requested)
            continue
        candidate_id = str(candidate["candidate_id"])
        if candidate_id not in resolved:
            resolved.append(candidate_id)
    return resolved, unknown


def build_live_batch_plan(
    *,
    profile: dict[str, Any],
    adapter: Any,
    oracle_registry: OracleRegistry = DEFAULT_ORACLE_REGISTRY,
) -> dict[str, Any]:
    """Discover candidates covered by the configured business Oracle.

    A service oracle covers its matching deployment.  A business-path oracle,
    such as Dify Chatflow through the proxy, covers all discovered workloads;
    the business result then tells policy whether the disrupted workload was
    actually on the path.
    """
    oracle = _runtime_oracle(profile, oracle_registry=oracle_registry)
    inventory = _adapter_inventory(adapter, profile)
    detection = adapter.detect_server_deployment(inventory)
    candidate_space = adapter.map_test_nodes(detection)
    candidate_scope = str(oracle.get("candidate_scope") or "service")
    candidates = [
        dict(item)
        for item in candidate_space.get("candidates") or []
        if isinstance(item, dict)
        and (
            candidate_scope == "business_path"
            or str(item.get("target")) == oracle["service"]
            or str(item.get("service_target")) == oracle["service"]
        )
    ]
    portrait = build_project_portrait(inventory, detection, candidate_space, cards=[])
    registry = build_hypothesis_registry(inventory, detection, candidate_space, cards=[])
    registry_quality = evaluate_registry_quality(registry, candidate_space, execution_budget=len(candidates) or 1)
    return {
        "schema_version": "chaosatlas-live-batch-plan-v1",
        "status": "ready" if candidates and candidate_space.get("status") == "verified" else "environment_blocked",
        "project_id": inventory.get("project_id"),
        "namespace": inventory.get("namespace"),
        "oracle": {
            "kind": oracle["kind"],
            "service": oracle["service"],
            "remote_port": oracle["remote_port"],
            "entrypoint": oracle["entrypoint"],
            "candidate_scope": candidate_scope,
        },
        "inventory_sha256": inventory.get("inventory_sha256"),
        "project_commit": inventory.get("project_commit"),
        "candidate_ids": [str(item.get("candidate_id")) for item in candidates],
        "candidates": candidates,
        "errors": list(candidate_space.get("errors") or []) if isinstance(candidate_space, dict) else ["candidate space unavailable"],
        "registry_inputs": {
            "portrait": portrait,
            "registry": registry,
            "quality": registry_quality,
            "candidate_space": candidate_space,
        },
    }


def _build_registry_signal(plan: dict[str, Any], candidate_pool: list[dict[str, Any]], *, bonus_cap: float = 0.25) -> dict[str, Any]:
    """Build a signal against the frozen Oracle-scoped pool only."""
    inputs = plan.get("registry_inputs") if isinstance(plan.get("registry_inputs"), dict) else {}
    registry = deepcopy(inputs.get("registry") if isinstance(inputs.get("registry"), dict) else {})
    quality = deepcopy(inputs.get("quality") if isinstance(inputs.get("quality"), dict) else {})
    pool_ids = {str(item.get("candidate_id")) for item in candidate_pool if isinstance(item, dict) and item.get("candidate_id")}
    all_hypotheses = registry.get("hypotheses") if isinstance(registry.get("hypotheses"), list) else []
    registry["hypotheses"] = [
        item for item in all_hypotheses
        if not isinstance(item, dict) or item.get("kind") != "runtime" or str(item.get("candidate_id") or "") in pool_ids
    ]
    registry["hypothesis_count"] = len(registry["hypotheses"])
    registry["execution_eligible_count"] = sum(1 for item in registry["hypotheses"] if isinstance(item, dict) and item.get("execution_eligible") is True)
    scoped_space = {"candidates": deepcopy(candidate_pool)}
    scoped_quality = evaluate_registry_quality(registry, scoped_space, execution_budget=len(candidate_pool) or 1)
    return build_registry_policy_signal(registry, scoped_quality, scoped_space, bonus_cap=bonus_cap)


def run_live_batch(
    *,
    profile_path: Path,
    output_root: Path,
    candidate_ids: list[str] | None = None,
    max_candidates: int | None = None,
    approve_live: bool = False,
    live_executor: Callable[..., dict[str, Any]] | None = None,
    live_adapter: Any | None = None,
    live_evidence_collector: Any | None = None,
    live_preflight: Any | None = None,
    kube_context: str | None = None,
    resume: bool = False,
    policy_mode: str = "legacy",
    policy_state_path: Path | None = None,
    policy_context: dict[str, Any] | None = None,
    policy_budget: int = 20,
    knowledge_root: Path | None = None,
    knowledge_write_root: Path | None = None,
    seed: int = 1001,
    oracle_registry: OracleRegistry = DEFAULT_ORACLE_REGISTRY,
    candidate_runner: Callable[..., dict[str, Any]] | None = None,
    advisory_provider: Callable[[dict[str, Any]], Any] | None = None,
    defense_history_root: Path | None = None,
    registry_shadow: bool = False,
) -> dict[str, Any]:
    """Run each selected candidate in its own immutable child output directory."""
    profile_path = Path(profile_path)
    output_root = Path(output_root)
    if policy_mode not in POLICY_MODES:
        raise ValueError(f"unsupported policy mode: {policy_mode}")
    if isinstance(policy_budget, bool) or int(policy_budget) < 1:
        raise ValueError("policy_budget must be a positive integer")
    policy_budget = int(policy_budget)
    existing_output = output_root.exists() and any(output_root.iterdir())
    if existing_output and not resume:
        raise FileExistsError(f"refusing non-empty batch output: {output_root}")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    adapter = live_adapter or KubernetesProjectAdapter(profile=profile, kube_context=kube_context)
    if candidate_runner is None:
        from chaosatlas.orchestration.engine import RunDependencies, RunEngine

        candidate_engine = RunEngine(
            RunDependencies(
                oracle_registry=oracle_registry,
                live_executor=live_executor,
                live_adapter=adapter,
                live_evidence_collector=live_evidence_collector,
                live_preflight=live_preflight,
            )
        )
        candidate_runner = candidate_engine._run_candidate
    plan = build_live_batch_plan(profile=profile, adapter=adapter, oracle_registry=oracle_registry)
    candidates = list(plan.get("candidates") or [])
    by_id = {str(item.get("candidate_id")): item for item in candidates}
    requested = [str(item) for item in candidate_ids] if candidate_ids else [str(item.get("candidate_id")) for item in candidates]
    requested_ids, unknown = resolve_requested_candidate_ids(
        candidates,
        requested,
        project_id=str(plan.get("project_id") or profile.get("project_id") or ""),
    )
    if unknown:
        plan["status"] = "environment_blocked"
        plan.setdefault("errors", []).append("unknown candidate ids: " + ",".join(unknown))
        requested_ids = []
    if isinstance(max_candidates, bool) or (max_candidates is not None and max_candidates < 1):
        raise ValueError("max_candidates must be a positive integer")
    candidate_pool = [by_id[item] for item in requested_ids]
    legacy_budget = max_candidates if max_candidates is not None else len(candidate_pool)
    if legacy_budget < 1 and candidate_pool:
        raise ValueError("legacy candidate budget must be positive")
    effective_policy_budget = min(policy_budget, len(candidate_pool)) if candidate_pool else policy_budget

    policy_state_file = Path(policy_state_path) if policy_state_path else output_root / "policy-state.json"
    if policy_state_file.suffix.lower() != ".json":
        policy_state_file = policy_state_file / "policy-state.json"
    if policy_state_file.is_file():
        policy_state = json.loads(policy_state_file.read_text(encoding="utf-8"))
    else:
        policy_state = new_policy_state(
            str(plan.get("project_id") or profile.get("project_id") or ""),
            str(plan.get("project_commit") or "0" * 40),
            int(seed),
            candidate_pool,
        )
    output_root.mkdir(parents=True, exist_ok=True)
    effective_policy_context = dict(policy_context or {})
    registry_signal: dict[str, Any] | None = None
    if policy_mode in {"shadow", "guarded", "default"}:
        registry_signal = _build_registry_signal(plan, candidate_pool)
        if registry_signal.get("status") == "ready":
            effective_policy_context.update({
                "registry_priority_bonus": dict(registry_signal.get("priority_bonus") or {}),
                "registry_priority_bonus_cap": float(registry_signal.get("bonus_cap") or 0.25),
                "registry_signal_hash": registry_signal.get("input_sha256"),
            })
        else:
            effective_policy_context["registry_signal_fallback"] = registry_signal.get("fallback_reason")
        (output_root / "registry-policy-input.json").write_text(
            json.dumps(registry_signal, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )

    selection = select_candidates_with_policy(
        candidate_pool,
        policy_state,
        mode=policy_mode,
        budget=effective_policy_budget,
        legacy_budget=legacy_budget,
        context=effective_policy_context,
    )
    selected_ids = list(selection["execution_candidate_ids"])
    profile_sha256 = hashlib.sha256(profile_path.read_bytes()).hexdigest()
    # The candidate pool and policy input hash are immutable.  Posterior
    # values in policy-state.json are intentionally mutable across rounds and
    # must not invalidate resume.
    manifest_candidate_ids = (
        [str(item.get("candidate_id")) for item in candidate_pool]
        if policy_mode != "legacy"
        else selected_ids
    )
    manifest = build_batch_manifest(
        profile_sha256=profile_sha256,
        kube_context=kube_context,
        namespace=str(plan.get("namespace") or profile.get("namespace") or ""),
        candidate_space_sha256=_sha256_json(plan.get("candidates") or []),
        selected_candidate_ids=manifest_candidate_ids,
        approve_live=approve_live,
        policy_mode=policy_mode,
        policy_budget=effective_policy_budget,
        policy_state_sha256=str(policy_state.get("input_sha256") or _sha256_json(policy_state)),
        policy_context_sha256=_sha256_json(effective_policy_context),
        seed=int(seed),
    )
    batch_state_path = output_root / "batch_state.jsonl"
    prior_results: dict[str, dict[str, Any]] = {}
    latest_states: dict[str, str] = {}
    if existing_output and resume:
        manifest_path = output_root / "batch_manifest.json"
        if not manifest_path.is_file():
            raise ValueError("cannot resume without batch_manifest.json")
        original_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        validate_batch_resume(original_manifest, manifest, latest_states=_load_latest_batch_states(batch_state_path))
        latest_states = _load_latest_batch_states(batch_state_path)
        summary_path = output_root / "batch_summary.json"
        if summary_path.is_file():
            try:
                prior = json.loads(summary_path.read_text(encoding="utf-8"))
                prior_results = {
                    str(item.get("candidate_id")): dict(item)
                    for item in prior.get("results") or []
                    if isinstance(item, dict) and item.get("candidate_id")
                }
            except (OSError, json.JSONDecodeError):
                prior_results = {}
    else:
        (output_root / "batch_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    write_policy_state(policy_state, policy_state_file)
    (output_root / "policy-selection.json").write_text(
        json.dumps(selection, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    terminal_states = {"cleanup_verified", "preflight_blocked"}
    if policy_mode == "legacy":
        for candidate_id in selected_ids:
            if latest_states.get(candidate_id) not in terminal_states:
                append_batch_state(batch_state_path, candidate_id=candidate_id, state="planned")
    if not existing_output:
        prior_results = {}
    (output_root / "batch_plan.json").write_text(json.dumps({**plan, "selected_candidate_ids": selected_ids, "policy_mode": policy_mode}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    results_by_id = dict(prior_results)

    if policy_mode != "legacy":
        controller = PolicyController(
            candidate_pool,
            policy_state,
            mode=policy_mode,
            budget=effective_policy_budget,
            context=effective_policy_context,
        )
        decision_path = output_root / "policy-decisions.jsonl"
        feedback_path = output_root / "policy-feedback.jsonl"
        registry_decision_path = output_root / "registry-policy-decisions.jsonl"
        attempted = {
            candidate_id
            for candidate_id, state in latest_states.items()
            if state in {"cleanup_verified", "preflight_blocked"}
        }
        # ``policy_budget`` remains the batch-level safety bound when the
        # caller does not provide an explicit max-candidates override.
        round_limit = max_candidates if max_candidates is not None else policy_budget
        round_count = 0
        feedback_count = 0
        stop_reason: str | None = None
        while True:
            decision = {"round": round_count + 1, **controller.next_decision(attempted_candidate_ids=attempted)}
            append_policy_record(decision_path, decision)
            if registry_signal is not None:
                append_policy_record(
                    registry_decision_path,
                    {
                        "round": round_count + 1,
                        "registry_signal_status": registry_signal.get("status"),
                        "registry_signal_hash": registry_signal.get("input_sha256"),
                        "registry_signal_fallback": registry_signal.get("fallback_reason"),
                        "legacy_candidate_ids": list((decision.get("selection") or {}).get("legacy_candidate_ids") or []),
                        "registry_selected_candidate_ids": list((decision.get("selection") or {}).get("policy_selected_candidate_ids") or []),
                        "execution_candidate_ids": list(decision.get("execution_candidate_ids") or []),
                        "stop_reason": decision.get("stop_reason"),
                        "policy_mode": policy_mode,
                    },
                )
            if round_count == 0:
                first_selection = decision.get("selection") or decision
                (output_root / "policy-selection.json").write_text(
                    json.dumps(first_selection, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
                )
            candidate_id = decision.get("candidate_id")
            if not candidate_id:
                stop_reason = str(decision.get("stop_reason") or "blocked")
                break
            if round_count >= round_limit:
                stop_reason = "budget_exhausted"
                break
            candidate_id = str(candidate_id)
            child = _candidate_output_root(output_root, candidate_id)
            if candidate_id not in results_by_id:
                append_batch_state(batch_state_path, candidate_id=candidate_id, state="planned")
                try:
                    result = candidate_runner(
                        profile_path=profile_path,
                        output_root=child,
                        mode="live",
                        approve_live=approve_live,
                        candidate_id=candidate_id,
                        seed=int(seed),
                        knowledge_root=knowledge_root,
                        defense_history_root=defense_history_root,
                        knowledge_write_root=knowledge_write_root,
                        advisory_provider=advisory_provider,
                        registry_shadow=registry_shadow,
                        kube_context=kube_context,
                    )
                except Exception as exc:
                    result = {"status": "method_invalid", "error": str(exc)}
                result = enrich_batch_result_from_artifacts(
                    {"candidate_id": candidate_id, "output": str(child), **result}, child
                )
                results_by_id[candidate_id] = result
                child_status = str(result.get("status") or "failed")
                if child_status == "environment_blocked":
                    append_batch_state(batch_state_path, candidate_id=candidate_id, state="preflight_blocked", reason=str(result.get("error") or child_status))
                elif child_status == "live_completed":
                    append_batch_state(batch_state_path, candidate_id=candidate_id, state="live_completed")
                    cleanup_status = str(result.get("cleanup_status") or "")
                    if not cleanup_status:
                        cleanup_report = child / "cleanup_report.json"
                        if cleanup_report.is_file():
                            try:
                                cleanup_status = str(json.loads(cleanup_report.read_text(encoding="utf-8")).get("status") or "")
                            except (OSError, json.JSONDecodeError):
                                cleanup_status = "failed"
                    result["cleanup_status"] = cleanup_status or "unknown"
                    if cleanup_status == "verified":
                        append_batch_state(batch_state_path, candidate_id=candidate_id, state="cleanup_verified")
                    else:
                        append_batch_state(batch_state_path, candidate_id=candidate_id, state="failed", reason="cleanup_not_verified")
                else:
                    append_batch_state(batch_state_path, candidate_id=candidate_id, state="failed", reason=str(result.get("error") or child_status))
            attempted.add(candidate_id)
            feedback = normalize_runtime_feedback(results_by_id[candidate_id], child)
            append_policy_record(feedback_path, {"round": round_count + 1, **feedback})
            feedback_count += 1
            if feedback.get("eligible") is True:
                try:
                    policy_state = ingest_runtime_result(
                        policy_state,
                        feedback,
                        decision=decision.get("selection") if isinstance(decision.get("selection"), dict) else decision,
                    )
                    write_policy_state(policy_state, policy_state_file)
                except (ValueError, TypeError) as exc:
                    append_policy_record(
                        feedback_path,
                        {"round": round_count + 1, "candidate_id": candidate_id, "eligible": False, "eligibility_reason": f"feedback_rejected:{type(exc).__name__}"},
                    )
            round_count += 1

        results = [results_by_id[candidate_id] for candidate_id in attempted if candidate_id in results_by_id]
        summary = summarize_batch_results(results, planned_count=round_count)
        summary.update({
            "approval_required": not approve_live,
            "policy_mode": policy_mode,
            "policy_selection_artifact": "policy-selection.json",
            "policy_stop_reason": stop_reason,
            "policy_fallback_used": False,
            "policy_round_count": round_count + (1 if stop_reason else 0),
            "policy_feedback_count": feedback_count,
        })
        attach_batch_knowledge_promotion(
            output_root=output_root,
            knowledge_write_root=knowledge_write_root,
            summary=summary,
        )
        (output_root / "batch_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return summary

    for candidate_id in selected_ids:
        if latest_states.get(candidate_id) in terminal_states:
            continue
        child = _candidate_output_root(output_root, candidate_id)
        try:
            result = candidate_runner(
                profile_path=profile_path,
                output_root=child,
                mode="live",
                approve_live=approve_live,
                candidate_id=candidate_id,
                seed=int(seed),
                knowledge_root=knowledge_root,
                defense_history_root=defense_history_root,
                knowledge_write_root=knowledge_write_root,
                advisory_provider=advisory_provider,
                registry_shadow=registry_shadow,
                kube_context=kube_context,
            )
        except Exception as exc:
            result = {"status": "failed", "error": str(exc)}
        result = enrich_batch_result_from_artifacts(
            {"candidate_id": candidate_id, "output": str(child), **result}, child
        )
        results_by_id[candidate_id] = result
        child_status = str(result.get("status") or "failed")
        if child_status == "environment_blocked":
            append_batch_state(batch_state_path, candidate_id=candidate_id, state="preflight_blocked", reason=str(result.get("error") or "environment_blocked"))
        elif child_status == "live_completed":
            append_batch_state(batch_state_path, candidate_id=candidate_id, state="live_completed")
            cleanup_report = child / "cleanup_report.json"
            cleanup_status = ""
            if cleanup_report.is_file():
                try:
                    cleanup_status = str(json.loads(cleanup_report.read_text(encoding="utf-8")).get("status") or "")
                except (OSError, json.JSONDecodeError):
                    cleanup_status = "failed"
            result["cleanup_status"] = cleanup_status or "unknown"
            if cleanup_status == "verified":
                append_batch_state(batch_state_path, candidate_id=candidate_id, state="cleanup_verified")
            else:
                append_batch_state(batch_state_path, candidate_id=candidate_id, state="failed", reason="cleanup_not_verified")
        else:
            append_batch_state(batch_state_path, candidate_id=candidate_id, state="failed", reason=str(result.get("error") or child_status))
    results = [results_by_id[candidate_id] for candidate_id in selected_ids if candidate_id in results_by_id]
    summary = summarize_batch_results(results, planned_count=len(selected_ids))
    summary.update({
        "approval_required": not approve_live,
        "policy_mode": policy_mode,
        "policy_selection_artifact": "policy-selection.json",
        "policy_stop_reason": selection.get("stop_reason"),
        "policy_fallback_used": bool(selection.get("fallback_used")),
    })
    attach_batch_knowledge_promotion(
        output_root=output_root,
        knowledge_write_root=knowledge_write_root,
        summary=summary,
    )
    (output_root / "batch_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary
