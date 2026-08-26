"""Dispatch an already validated evidence plan to read-only collectors."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from tools.evidence_collectors import collect_unavailable_evidence


_COLLECTOR_KINDS = {
    "deployment_facts": "manifest",
    "service_facts": "config",
    "pod_state": "config",
    "pod_events": "kubernetes_event",
    "pod_logs": "runtime_log",
}


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "-" for char in str(value)).strip("-") or "evidence"


def _unavailable(
    *,
    output_root: Path,
    evidence_id: str,
    action_kind: str,
    claim_scope: str,
    reason: str,
) -> dict[str, Any]:
    return collect_unavailable_evidence(
        root=output_root,
        source_ref=f"runtime/kubernetes/unavailable/{_safe_name(evidence_id)}.json",
        evidence_id=evidence_id,
        kind=_COLLECTOR_KINDS[action_kind],
        claim_scope=claim_scope,
        reason=reason,
    )


def _dispatch(
    *,
    collector: Any,
    action_kind: str,
    namespace: str,
    target: str,
    deployment_target: str,
    selector: dict[str, str],
    claim_scope: str,
    evidence_id: str,
    mutation_name: str | None = None,
    scope_events_to_mutation: bool = False,
) -> dict[str, Any]:
    common = {
        "namespace": namespace,
        "claim_scope": claim_scope,
        "evidence_id": evidence_id,
    }
    if action_kind == "deployment_facts":
        return collector.collect_deployment_facts(deployment=deployment_target, **common)
    if action_kind == "service_facts":
        return collector.collect_service_facts(service=target, **common)
    if action_kind == "pod_state":
        return collector.collect_pod_state(selector=selector, **common)
    if action_kind == "pod_events":
        if scope_events_to_mutation and not mutation_name:
            return _unavailable(
                output_root=Path(getattr(collector, "root", ".")),
                evidence_id=evidence_id,
                action_kind=action_kind,
                claim_scope=claim_scope,
                reason="mutation_name_unavailable",
            )
        return collector.collect_events(involved_object_name=mutation_name, **common)
    if action_kind == "pod_logs":
        return collector.collect_logs(workload=f"deployment/{deployment_target}", **common)
    raise ValueError(f"unsupported planned action: {action_kind}")


def collect_planned_evidence(
    *,
    plan: dict[str, Any],
    collector: Any,
    output_root: Path,
    namespace: str,
    target: str,
    selector: dict[str, str] | None,
    evidence_prefix: str,
    claim_scope: str,
    mutation_name: str | None = None,
    scope_events_to_mutation: bool = False,
) -> list[dict[str, Any]]:
    """Dispatch only planned read-only Kubernetes evidence actions."""

    if plan.get("status") != "planned":
        return []
    selected = {str(item) for item in ((plan.get("selection") or {}).get("candidate_ids") or [])}
    records: list[dict[str, Any]] = []
    for action in plan.get("actions") or []:
        if not isinstance(action, dict) or action.get("candidate_id") not in selected:
            continue
        if action.get("read_only") is not True:
            continue
        action_kind = str(action.get("action_kind") or "")
        if action_kind not in _COLLECTOR_KINDS:
            continue
        evidence_id = f"{evidence_prefix}-{action_kind}"
        try:
            record = _dispatch(
                collector=collector,
                action_kind=action_kind,
                namespace=namespace,
                target=str(action.get("target") or target),
                deployment_target=str(action.get("deployment_target") or target),
                selector={str(key): str(value) for key, value in (selector or {}).items()},
                claim_scope=claim_scope,
                evidence_id=evidence_id,
                mutation_name=mutation_name,
                scope_events_to_mutation=scope_events_to_mutation,
            )
        except Exception as exc:
            record = _unavailable(
                output_root=Path(output_root),
                evidence_id=evidence_id,
                action_kind=action_kind,
                claim_scope=claim_scope,
                reason=f"collector_failed:{type(exc).__name__}",
            )
        if isinstance(record, dict):
            record["planned_action_id"] = str(action.get("action_id"))
        records.append(record)
    return records
