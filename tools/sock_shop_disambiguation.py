"""Read-only evidence disambiguation for the Sock Shop front-end PodKill pilot."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from tools.evidence_collectors import collect_file_evidence, collect_unavailable_evidence
from tools.kubernetes_evidence import KubernetesEvidenceCollector
from tools.rca_loop import _contains_sensitive_value


Runner = Callable[..., tuple[int, str, str]]


def _safe_selector(selector: str) -> str:
    value = str(selector or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+=[A-Za-z0-9_.-]+(?:,[A-Za-z0-9_.-]+=[A-Za-z0-9_.-]+)*", value):
        raise ValueError("selector must be a bounded label selector")
    return value


def _capture_json(
    collector: KubernetesEvidenceCollector,
    *,
    evidence_id: str,
    relative_path: str,
    command: list[str],
    claim_scope: str,
    interpretation: str,
    satisfies: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    evidence = collector._capture(
        evidence_id=evidence_id,
        kind="config",
        claim_scope=claim_scope,
        relative_path=relative_path,
        command=command,
        interpretation=interpretation,
        satisfies=satisfies,
        window=None,
    )
    path = collector.root / relative_path
    if evidence.get("polarity") != "supports":
        return evidence, {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return collect_unavailable_evidence(
            root=collector.root,
            source_ref=relative_path,
            evidence_id=evidence_id,
            kind="config",
            claim_scope=claim_scope,
            reason="invalid_json",
        ), {}
    if not isinstance(value, dict):
        return collect_unavailable_evidence(
            root=collector.root,
            source_ref=relative_path,
            evidence_id=evidence_id,
            kind="config",
            claim_scope=claim_scope,
            reason="invalid_json_shape",
        ), {}
    return evidence, value


def _event_time(event: dict[str, Any]) -> datetime | None:
    for key in ("eventTime", "lastTimestamp", "firstTimestamp"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
            except ValueError:
                pass
    metadata = event.get("metadata") or {}
    value = metadata.get("creationTimestamp") if isinstance(metadata, dict) else None
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            pass
    return None


def _capture_bounded_events(
    collector: KubernetesEvidenceCollector,
    *,
    claim_scope: str,
    evidence_id: str,
    window: dict[str, str] | None,
) -> dict[str, Any]:
    relative_path = f"runtime/kubernetes/events/{evidence_id}.json"
    if not window:
        path = collector.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"items": []}, ensure_ascii=True) + "\n", encoding="utf-8")
        return collect_unavailable_evidence(
            root=collector.root,
            source_ref=relative_path,
            evidence_id=evidence_id,
            kind="kubernetes_event",
            claim_scope=claim_scope,
            reason="event_window_required",
        )
    code, stdout, stderr = collector.runner(["get", "events", "-n", "sock-shop-lab", "-o", "json"], timeout=collector.timeout)
    if code != 0:
        return collector.collect_events(namespace="sock-shop-lab", claim_scope=claim_scope, evidence_id=evidence_id, window=window)
    if _contains_sensitive_value(stdout) or _contains_sensitive_value(stderr):
        raise ValueError("Kubernetes output contains sensitive values")
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        path = collector.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(stdout, encoding="utf-8")
        return collect_unavailable_evidence(root=collector.root, source_ref=relative_path, evidence_id=evidence_id, kind="kubernetes_event", claim_scope=claim_scope, reason="invalid_json", window=window)
    start = datetime.fromisoformat(window["start"].replace("Z", "+00:00")).astimezone(timezone.utc)
    end = datetime.fromisoformat(window["end"].replace("Z", "+00:00")).astimezone(timezone.utc)
    items = payload.get("items", []) if isinstance(payload, dict) else []
    filtered = [item for item in items if isinstance(item, dict) and (stamp := _event_time(item)) is not None and start <= stamp <= end]
    path = collector.root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"apiVersion": "v1", "kind": "EventList", "items": filtered}, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return collect_file_evidence(root=collector.root, source_ref=relative_path, evidence_id=evidence_id, kind="kubernetes_event", claim_scope=claim_scope, interpretation="Kubernetes events filtered to the explicit RCA observation window", satisfies=["kubernetes_event_window"], window=window)


def collect_frontend_disambiguation(
    *,
    root: Path,
    namespace: str,
    service: str = "front-end",
    selector: str = "name=front-end",
    window: dict[str, str] | None = None,
    runner: Runner | None = None,
) -> dict[str, Any]:
    """Capture current Pod, Endpoint, Deployment and Event state without mutation."""

    if str(namespace or "").strip() != "sock-shop-lab":
        raise ValueError("Sock Shop disambiguation requires isolated namespace sock-shop-lab")
    service = str(service or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", service):
        raise ValueError("service must be a safe Kubernetes name")
    selector = _safe_selector(selector)
    collector = KubernetesEvidenceCollector(
        root=Path(root),
        allowed_namespaces={str(namespace)},
        runner=runner,
    )
    claim_scope = f"deployment:{service}"
    evidence: list[dict[str, Any]] = []
    observations: dict[str, dict[str, Any]] = {}

    pod_evidence, observations["pods"] = _capture_json(
        collector,
        evidence_id="EV-DISAMBIG-PODS-001",
        relative_path="runtime/disambiguation/pods.json",
        command=["get", "pods", "-n", namespace, "-l", selector, "-o", "json"],
        claim_scope=claim_scope,
        interpretation="Current front-end Pod snapshot for PodKill readiness disambiguation",
        satisfies=["pod_snapshot"],
    )
    evidence.append(pod_evidence)

    endpoint_evidence, observations["endpoints"] = _capture_json(
        collector,
        evidence_id="EV-DISAMBIG-ENDPOINTS-001",
        relative_path="runtime/disambiguation/endpoints.json",
        command=["get", "endpoints", service, "-n", namespace, "-o", "json"],
        claim_scope=claim_scope,
        interpretation="Service Endpoint addresses observed for the bounded PodKill analysis",
        satisfies=["service_endpoint_snapshot"],
    )
    evidence.append(endpoint_evidence)

    deployment_evidence, observations["deployment"] = _capture_json(
        collector,
        evidence_id="EV-DISAMBIG-DEPLOYMENT-001",
        relative_path="runtime/disambiguation/deployment.json",
        command=["get", "deployment", service, "-n", namespace, "-o", "json"],
        claim_scope=claim_scope,
        interpretation="Deployment strategy and readiness probe configuration",
        satisfies=["deployment_strategy", "readiness_probe_configuration"],
    )
    evidence.append(deployment_evidence)

    events = _capture_bounded_events(collector, claim_scope=claim_scope, evidence_id="EV-DISAMBIG-EVENTS-001", window=window)
    evidence.append(events)
    return {"observations": observations, "evidence": evidence}


def _items(snapshot: Any) -> list[dict[str, Any]]:
    if not isinstance(snapshot, dict):
        return [item for item in snapshot if isinstance(item, dict)] if isinstance(snapshot, list) else []
    items = snapshot.get("items")
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _pod_ip(pod: dict[str, Any]) -> str | None:
    value = (pod.get("status") or {}).get("podIP")
    return str(value) if value else None


def _pod_uid(pod: dict[str, Any]) -> str | None:
    value = (pod.get("metadata") or {}).get("uid")
    return str(value) if value else None


def _pod_ready(pod: dict[str, Any]) -> bool:
    for condition in (pod.get("status") or {}).get("conditions", []) or []:
        if isinstance(condition, dict) and condition.get("type") == "Ready":
            return condition.get("status") == "True"
    return False


def _endpoint_ips(endpoints: dict[str, Any]) -> tuple[set[str], set[str], bool]:
    addresses: set[str] = set()
    not_ready: set[str] = set()
    subsets = endpoints.get("subsets") if isinstance(endpoints, dict) else None
    if isinstance(endpoints, dict) and endpoints.get("kind") == "Endpoints" and "subsets" not in endpoints:
        return addresses, not_ready, True
    if not isinstance(subsets, list):
        return addresses, not_ready, False
    for subset in subsets:
        if not isinstance(subset, dict):
            continue
        for address in subset.get("addresses", []) or []:
            if isinstance(address, dict) and address.get("ip"):
                addresses.add(str(address["ip"]))
        for address in subset.get("notReadyAddresses", []) or []:
            if isinstance(address, dict) and address.get("ip"):
                not_ready.add(str(address["ip"]))
    return addresses, not_ready, True


def classify_business_readiness_contradiction(
    *,
    pod_before: dict[str, Any],
    pod_during: dict[str, Any],
    endpoints_during: dict[str, Any],
    business_samples: list[dict[str, Any]],
    observation_phase: str = "unknown",
) -> dict[str, Any]:
    """Classify HTTP-200 evidence without changing deterministic RCA state."""

    samples = [sample for sample in business_samples if isinstance(sample, dict)]
    if observation_phase != "during_injection":
        return {
            "classification": "observation_inconclusive",
            "deterministic": False,
            "business_success": False,
            "endpoint_observed": False,
            "endpoint_addresses": [],
            "endpoint_not_ready_addresses": [],
            "old_pod_serving": [],
            "replacement_ready_in_endpoints": False,
            "observation_window_artifact": False,
            "reason": "Pod and Endpoint snapshots are not from the injection window",
            "observation_phase": observation_phase,
        }
    all_success = bool(samples) and all(
        str(sample.get("status_code", sample.get("http_status"))) == "200" and sample.get("contract_ok", True) is not False
        for sample in samples
    )
    before = _items(pod_before)
    during = _items(pod_during)
    addresses, not_ready, endpoint_observed = _endpoint_ips(endpoints_during)
    before_uids = {_pod_uid(pod) for pod in before if _pod_uid(pod)}
    if any(not _pod_uid(pod) for pod in before + during):
        return {
            "classification": "observation_inconclusive",
            "deterministic": False,
            "business_success": bool(samples) and all(
                str(sample.get("status_code", sample.get("http_status"))) == "200" and sample.get("contract_ok", True) is not False
                for sample in samples
            ),
            "endpoint_observed": False,
            "endpoint_addresses": [],
            "endpoint_not_ready_addresses": [],
            "old_pod_serving": [],
            "replacement_ready_in_endpoints": False,
            "observation_window_artifact": False,
            "reason": "Pod identity is missing from the observation snapshot",
            "observation_phase": observation_phase,
        }
    old_serving: list[str] = []
    for pod in during:
        metadata = pod.get("metadata") or {}
        ip = _pod_ip(pod)
        uid = _pod_uid(pod)
        old_uid_still_present = uid in before_uids
        if ip and ip in addresses and (metadata.get("deletionTimestamp") or old_uid_still_present):
            old_serving.append(str(metadata.get("name") or ip))

    new_pods = [pod for pod in during if _pod_uid(pod) and _pod_uid(pod) not in before_uids and _pod_ready(pod)]
    new_ready_in_endpoints = any(_pod_ip(pod) in addresses for pod in new_pods if _pod_ip(pod))

    transport_unavailable = any(
        sample.get("error") or sample.get("status_code", sample.get("http_status")) is None
        for sample in samples
    )
    if not samples or not endpoint_observed:
        classification = "observation_inconclusive"
        deterministic = False
        reason = "business samples and Endpoint observation are both required"
    elif not all_success:
        classification = "platform_blocked" if transport_unavailable else "observation_inconclusive"
        deterministic = transport_unavailable
        reason = "business path was unavailable at the platform boundary" if transport_unavailable else "business HTTP 200 did not satisfy the business contract"
    elif old_serving:
        classification = "old_pod_still_serving"
        deterministic = True
        reason = "a terminating Pod IP remained in Service endpoints while HTTP 200 persisted"
    elif not new_ready_in_endpoints:
        classification = "observation_inconclusive"
        deterministic = False
        reason = "HTTP 200 lacks a Ready replacement Pod present in Service endpoints"
    else:
        classification = "defended"
        deterministic = True
        reason = "HTTP 200 persisted with a Ready replacement Pod serving through the Service"

    return {
        "classification": classification,
        "deterministic": deterministic,
        "business_success": all_success,
        "endpoint_observed": endpoint_observed,
        "endpoint_addresses": sorted(addresses),
        "endpoint_not_ready_addresses": sorted(not_ready),
        "old_pod_serving": old_serving,
        "replacement_ready_in_endpoints": new_ready_in_endpoints,
        "observation_window_artifact": bool(all_success and endpoint_observed and not addresses and not new_ready_in_endpoints),
        "reason": reason,
        "observation_phase": observation_phase,
    }


def summarize_disambiguation_timeline(
    *,
    pod_before: dict[str, Any],
    samples: list[dict[str, Any]],
) -> dict[str, Any]:
    """Reduce synchronized injection-window samples without changing RCA state."""

    normalized = [sample for sample in samples if isinstance(sample, dict)]
    per_sample: list[dict[str, Any]] = []
    for sample in normalized:
        per_sample.append(
            classify_business_readiness_contradiction(
                pod_before=pod_before,
                pod_during=sample.get("pods") if isinstance(sample.get("pods"), dict) else {},
                endpoints_during=sample.get("endpoints") if isinstance(sample.get("endpoints"), dict) else {},
                business_samples=[sample.get("business")] if isinstance(sample.get("business"), dict) else [],
                observation_phase="during_injection",
            )
        )
    labels = [item["classification"] for item in per_sample]
    if not labels:
        classification, deterministic, reason = "observation_inconclusive", False, "no synchronized injection-window samples were collected"
    elif "old_pod_still_serving" in labels:
        classification, deterministic, reason = "old_pod_still_serving", True, "at least one synchronized sample proves the old Pod remained in ready Service endpoints"
    elif all(label == "defended" for label in labels):
        classification, deterministic, reason = "defended", True, "every synchronized sample has a Ready replacement Pod in ready Service endpoints"
    elif "platform_blocked" in labels and all(label == "platform_blocked" for label in labels):
        classification, deterministic, reason = "platform_blocked", True, "every synchronized sample was unavailable at the platform boundary"
    else:
        classification, deterministic, reason = "observation_inconclusive", False, "synchronized samples do not consistently identify a serving Pod"
    return {
        "classification": classification,
        "deterministic": deterministic,
        "sample_count": len(normalized),
        "sample_classifications": labels,
        "per_sample": per_sample,
        "reason": reason,
    }
